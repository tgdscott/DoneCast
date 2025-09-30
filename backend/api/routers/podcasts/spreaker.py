from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Session, select

from ...routers.auth import get_current_user
from ...core.database import get_session
from ...models.podcast import Episode, EpisodeStatus, Podcast, PodcastImportState
from ...models.user import User
from ...services.episodes import publisher as episode_publisher
from ...services.publisher import SpreakerClient
from ...services.episodes.sync import sync_spreaker_episodes

router = APIRouter()

log = logging.getLogger(__name__)


@router.post("/{podcast_id}/link-spreaker-episodes", status_code=200)
async def link_imported_to_spreaker(
    podcast_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    pod = session.exec(
        select(Podcast).where(Podcast.id == podcast_id, Podcast.user_id == current_user.id)
    ).first()
    if not pod:
        raise HTTPException(status_code=404, detail="Podcast not found.")
    if not pod.spreaker_show_id or not getattr(current_user, "spreaker_access_token", None):
        raise HTTPException(status_code=400, detail="Podcast not linked to Spreaker or user not connected.")

    token_str = str(current_user.spreaker_access_token)
    client = SpreakerClient(api_token=token_str)
    ok, spk_data = client.get_all_episodes_for_show(str(pod.spreaker_show_id))
    if not ok or not isinstance(spk_data, dict):
        raise HTTPException(status_code=502, detail="Failed to fetch episodes from Spreaker.")
    spk_items = spk_data.get("items", []) or []

    local_eps = session.exec(
        select(Episode).where(Episode.podcast_id == pod.id, Episode.user_id == current_user.id)
    ).all()

    def norm_title(title: Optional[str]) -> str:
        try:
            return (title or "").strip().lower()
        except Exception:
            return ""

    def date_key(dt: Optional[datetime]) -> str:
        try:
            return dt.date().isoformat() if dt else ""
        except Exception:
            return ""

    local_index: dict[tuple[str, str], Episode] = {}
    for local_episode in local_eps:
        if getattr(local_episode, "spreaker_episode_id", None):
            continue
        key = (
            norm_title(local_episode.title),
            date_key(getattr(local_episode, "publish_at", None)),
        )
        local_index[key] = local_episode

    mapped = 0
    total_candidates = len(local_index)
    for item in spk_items:
        if not isinstance(item, dict):
            continue
        spk_title = item.get("title") or ""
        spk_id = str(item.get("episode_id")) if item.get("episode_id") is not None else None
        publish_at = None
        publish_str = item.get("published_at")
        if publish_str:
            try:
                publish_at = datetime.strptime(publish_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                publish_at = None
        key = (norm_title(spk_title), date_key(publish_at))
        candidate = local_index.get(key)
        if candidate and not getattr(candidate, "spreaker_episode_id", None) and spk_id:
            candidate.spreaker_episode_id = spk_id
            if not getattr(candidate, "final_audio_path", None):
                candidate.final_audio_path = item.get("stream_url") or item.get("download_url")
            if publish_at:
                try:
                    candidate.publish_at = candidate.publish_at or publish_at
                    if publish_at <= datetime.now(timezone.utc):
                        candidate.status = EpisodeStatus.published
                except Exception:
                    pass
            session.add(candidate)
            mapped += 1

    if mapped:
        session.commit()
    return {"mapped": mapped, "total_candidates": total_candidates}


@router.post("/{podcast_id}/publish-all", status_code=200)
async def publish_all_to_spreaker(
    podcast_id: UUID,
    publish_state: Optional[str] = Body("public", embed=True),
    include_already_linked: bool = Body(
        False,
        embed=True,
        description="If true, will also republish episodes that already have a spreaker_episode_id",
    ),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    pod = session.exec(
        select(Podcast).where(Podcast.id == podcast_id, Podcast.user_id == current_user.id)
    ).first()
    if not pod:
        raise HTTPException(status_code=404, detail="Podcast not found.")
    if not getattr(current_user, "spreaker_access_token", None):
        raise HTTPException(status_code=401, detail="User is not connected to Spreaker.")
    sid = getattr(pod, "spreaker_show_id", None)
    if not sid or not str(sid).isdigit():
        raise HTTPException(status_code=400, detail="Podcast must have a numeric spreaker_show_id.")

    episodes = session.exec(
        select(Episode).where(Episode.podcast_id == pod.id, Episode.user_id == current_user.id)
    ).all()
    started = 0
    skipped_no_audio = 0
    skipped_already_linked = 0
    errors = 0

    for episode in episodes:
        if not getattr(episode, "final_audio_path", None):
            skipped_no_audio += 1
            continue
        if getattr(episode, "spreaker_episode_id", None) and not include_already_linked:
            skipped_already_linked += 1
            continue
        try:
            episode_publisher.publish(
                session=session,
                current_user=current_user,
                episode_id=episode.id,
                derived_show_id=str(sid),
                publish_state=publish_state,
                auto_publish_iso=None,
            )
            started += 1
        except Exception:
            errors += 1

    return {
        "message": "Batch publish enqueued",
        "show_id": str(sid),
        "started": started,
        "skipped_no_audio": skipped_no_audio,
        "skipped_already_linked": skipped_already_linked,
        "errors": errors,
        "total": len(episodes),
    }


@router.post("/{podcast_id}/recover-from-spreaker", status_code=200)
async def recover_spreaker_episodes(
    podcast_id: UUID,
    prefer_remote: bool = Body(False, embed=True, description="If true, prefer remote values for common fields like description and tags."),
    overwrite: list[str] | None = Body(None, embed=True, description="Explicit list of fields to overwrite from Spreaker (e.g., ['show_notes','tags'])."),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    log.info("Starting Spreaker recovery for podcast %s for user %s", podcast_id, current_user.id)

    podcast = session.get(Podcast, podcast_id)
    if not podcast or podcast.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Podcast not found.")

    if not podcast.spreaker_show_id or not current_user.spreaker_access_token:
        raise HTTPException(status_code=400, detail="Podcast is not linked to Spreaker or user is not connected.")

    client = SpreakerClient(api_token=current_user.spreaker_access_token)
    try:
        overwrite_fields = set(overwrite or [])
        if prefer_remote and not overwrite_fields:
            # By default, favour remote description & tags if requested
            overwrite_fields = {"show_notes", "tags"}
        summary = sync_spreaker_episodes(
            session,
            podcast,
            current_user,
            client=client,
            overwrite_fields=overwrite_fields if overwrite_fields else None,
        )
        session.commit()
    except RuntimeError as exc:
        log.error("Failed to sync Spreaker episodes for show %s: %s", podcast.spreaker_show_id, exc)
        raise HTTPException(status_code=502, detail="Could not fetch episodes from Spreaker.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    created = summary.get("created", 0)
    updated = summary.get("updated", 0)
    fetched = summary.get("fetched", 0)
    message = (
        f"Recovered {created} new episodes"
        + (f" and merged {updated} existing episodes" if updated else "")
        + (f" out of {fetched} fetched" if fetched else "")
        + "."
    )

    state = session.get(PodcastImportState, podcast.id)
    import_status = None
    if state:
        import_status = {
            "source": state.source,
            "feed_total": state.feed_total,
            "imported_count": state.imported_count,
            "needs_full_import": state.needs_full_import,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        }

    return {
        "recovered_count": created,
        "updated_count": updated,
        "fetched": fetched,
        "duplicates": summary.get("duplicates"),
        "conflicts": summary.get("conflicts", []),
        "message": message,
        "import_status": import_status,
    }


@router.post("/{podcast_id}/link-spreaker-show", status_code=200)
async def link_spreaker_show(
    podcast_id: UUID,
    show_id: str = Body(..., embed=True, description="Numeric Spreaker show id to link"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    pod = session.exec(
        select(Podcast).where(Podcast.id == podcast_id, Podcast.user_id == current_user.id)
    ).first()
    if not pod:
        raise HTTPException(status_code=404, detail="Podcast not found.")
    if not isinstance(show_id, str) or not show_id.isdigit():
        raise HTTPException(status_code=400, detail="show_id must be a numeric Spreaker id")
    token = getattr(current_user, "spreaker_access_token", None)
    pod.spreaker_show_id = show_id
    if token:
        try:
            client = SpreakerClient(api_token=token)
            ok, resp = client.get_show(show_id)
            if ok and isinstance(resp, dict):
                show_obj = resp.get("show") or resp
                try:
                    rss_candidate = (
                        show_obj.get("rss_url")
                        or show_obj.get("feed_url")
                        or show_obj.get("xml_url")
                    )
                    if rss_candidate:
                        pod.rss_url_locked = pod.rss_url_locked or rss_candidate
                        if not pod.rss_url:
                            pod.rss_url = rss_candidate
                except Exception:
                    pass
                try:
                    for key in ("image_url", "cover_url", "cover_art_url", "image"):
                        if show_obj.get(key):
                            pod.remote_cover_url = show_obj.get(key)
                            break
                except Exception:
                    pass
        except Exception:
            pass
    session.add(pod)
    session.commit()
    session.refresh(pod)
    return {"message": "Linked to Spreaker show", "podcast": pod}


@router.post("/{podcast_id}/create-spreaker-show", status_code=200)
async def create_spreaker_show_for_podcast(
    podcast_id: UUID,
    title: Optional[str] = Body(None, embed=True),
    description: Optional[str] = Body(None, embed=True),
    language: Optional[str] = Body("en", embed=True),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    pod = session.exec(
        select(Podcast).where(Podcast.id == podcast_id, Podcast.user_id == current_user.id)
    ).first()
    if not pod:
        raise HTTPException(status_code=404, detail="Podcast not found.")
    if getattr(pod, "spreaker_show_id", None):
        raise HTTPException(status_code=400, detail="Podcast already linked to a Spreaker show.")
    token = getattr(current_user, "spreaker_access_token", None)
    if not token:
        raise HTTPException(status_code=401, detail="User is not connected to Spreaker")
    client = SpreakerClient(api_token=token)
    show_title = (title or pod.name or "Untitled").strip()
    show_description = description if description is not None else (pod.description or "")
    ok, result = client.create_show(title=show_title, description=show_description, language=language or "en")
    if not ok:
        msg = str(result)
        low = msg.lower()
        if "free account" in low or "can't create any more shows" in low or "cant create any more shows" in low:
            raise HTTPException(
                status_code=403,
                detail="You can only have one show on a free Spreaker account. Please upgrade your Spreaker plan to create additional shows.",
            )
        raise HTTPException(status_code=502, detail=f"Failed to create show on Spreaker: {result}")
    show_id = str(result.get("show_id")) if isinstance(result, dict) else None
    if not show_id or not show_id.isdigit():
        raise HTTPException(status_code=502, detail="Spreaker did not return a numeric show_id")
    pod.spreaker_show_id = show_id
    try:
        ok_show, resp_show = client.get_show(show_id)
        if ok_show:
            show_obj = resp_show.get("show") or resp_show
            rss_candidate = (
                show_obj.get("rss_url")
                or show_obj.get("feed_url")
                or show_obj.get("xml_url")
            )
            if rss_candidate:
                pod.rss_url_locked = pod.rss_url_locked or rss_candidate
                if not pod.rss_url:
                    pod.rss_url = rss_candidate
            for key in ("image_url", "cover_url", "cover_art_url", "image"):
                if isinstance(show_obj, dict) and show_obj.get(key):
                    pod.remote_cover_url = show_obj.get(key)
                    break
    except Exception:
        pass
    session.add(pod)
    session.commit()
    session.refresh(pod)
    return {
        "message": "Spreaker show created and linked",
        "spreaker_show_id": show_id,
        "podcast": pod,
    }
