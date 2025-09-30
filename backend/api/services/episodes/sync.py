from __future__ import annotations

from datetime import datetime, timezone
import html
from typing import Any, Dict, List

import json
import logging

from sqlmodel import Session, select

from api.models.podcast import Episode, EpisodeStatus, Podcast, PodcastImportState
from api.models.user import User
from api.services.publisher import SpreakerClient

from .merge import (
    merge_into_episode,
    merge_podcast_episode_duplicates,
    normalize_title,
)


def _parse_spreaker_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    text = str(value)
    try:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _spreaker_payload(item: Dict[str, Any]) -> Dict[str, Any]:
    publish_dt = _parse_spreaker_datetime(item.get("published_at") or item.get("publish_at"))
    now = datetime.now(timezone.utc)
    status = EpisodeStatus.published if publish_dt and publish_dt <= now else EpisodeStatus.processed

    def _coerce_tags(value: Any) -> List[str]:
        tags: List[str] = []
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict):
                    for key in ("name", "value", "label", "tag", "title"):
                        raw = entry.get(key)
                        if raw:
                            text = str(raw).strip()
                            if text and text not in tags:
                                tags.append(text)
                            break
                    else:
                        raw = str(entry).strip()
                        if raw and raw not in tags:
                            tags.append(raw)
                elif entry is not None:
                    raw = str(entry).strip()
                    if raw and raw not in tags:
                        tags.append(raw)
        elif isinstance(value, dict):
            for raw in value.values():
                text = str(raw).strip()
                if text and text not in tags:
                    tags.append(text)
        elif isinstance(value, str):
            parts = [part.strip() for part in value.split(",")]
            for part in parts:
                if part and part not in tags:
                    tags.append(part)
        return tags

    tags = _coerce_tags(item.get("tags"))
    if not tags:
        tags = _coerce_tags(item.get("tag_list"))
    if not tags:
        tags = _coerce_tags(item.get("category"))
    if not tags:
        tags = _coerce_tags(item.get("categories"))
    if not tags:
        tags = _coerce_tags(item.get("topics"))

    download_url = item.get("download_url") or item.get("stream_url")

    def _first_text(*keys: str) -> str | None:
        for key in keys:
            val = item.get(key)
            if not val:
                continue
            if isinstance(val, list):
                text_parts: List[str] = []
                for part in val:
                    if isinstance(part, dict):
                        for inner in ("value", "text", "data", "content"):
                            if part.get(inner):
                                text_parts.append(str(part[inner]))
                                break
                    elif isinstance(part, str):
                        text_parts.append(part)
                if text_parts:
                    return html.unescape("\n\n".join(text_parts))
            elif isinstance(val, dict):
                for inner in ("value", "text", "data", "content"):
                    if val.get(inner):
                        return html.unescape(str(val[inner]))
                return html.unescape(str(val))
            else:
                return html.unescape(str(val))
        return None

    meta: Dict[str, Any] = {}
    if item.get("permalink"):
        meta["spreaker_permalink"] = item["permalink"]
    if item.get("duration") is not None:
        meta["spreaker_duration"] = item.get("duration")
    meta["spreaker_last_sync"] = datetime.utcnow().isoformat() + "Z"

    return {
        "title": item.get("title") or item.get("name") or "Untitled Episode",
        "show_notes": _first_text(
            "description_html",
            "description_plain",
            "description_text",
            "description",
            "content_html",
            "content",
            "body",
            "summary",
        ),
        "final_audio_path": item.get("stream_url") or download_url,
        "cover_path": item.get("image_url"),
        "remote_cover_url": item.get("image_original_url") or item.get("image_url"),
        "spreaker_episode_id": str(item.get("episode_id")) if item.get("episode_id") is not None else None,
        "is_published_to_spreaker": True,
        "status": status,
        "publish_at": publish_dt,
        "publish_at_local": None,
        "season_number": item.get("season"),
        "episode_number": item.get("episode"),
        "tags": tags,
        "is_explicit": str(item.get("explicit") or "").lower() in {"1", "true", "yes", "explicit"},
        "meta": meta,
        "processed_at": publish_dt or datetime.utcnow(),
        "created_at": publish_dt or datetime.utcnow(),
        "source_media_url": download_url,
        "source_published_at": publish_dt,
    }

def sync_spreaker_episodes(
    session: Session,
    podcast: Podcast,
    user: User,
    *,
    client: SpreakerClient | None = None,
) -> Dict[str, Any]:
    """Fetch episodes from Spreaker and merge them with local records."""

    if not podcast.spreaker_show_id:
        raise ValueError("Podcast lacks a linked Spreaker show id")

    token = getattr(user, "spreaker_access_token", None)
    if client is None:
        if not token:
            raise ValueError("User must be connected to Spreaker")
        client = SpreakerClient(token)

    ok, payload = client.get_all_episodes_for_show(str(podcast.spreaker_show_id))
    if not ok or not isinstance(payload, dict):
        raise RuntimeError(f"Failed to fetch episodes from Spreaker: {payload}")

    items = payload.get("items") or []

    duplicates_summary = merge_podcast_episode_duplicates(session, podcast.id)
    session.flush()

    local_eps = session.exec(
        select(Episode).where(Episode.podcast_id == podcast.id, Episode.user_id == user.id)
    ).all()
    title_index: Dict[str, Episode] = {}
    for ep in local_eps:
        title_index[normalize_title(ep.title)] = ep

    created = 0
    updated = 0
    conflicts: List[Dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        payload_dict = _spreaker_payload(item)
        title_key = normalize_title(payload_dict.get("title"))
        if not title_key:
            continue
        existing = title_index.get(title_key)
        if existing:
            merge_result = merge_into_episode(existing, payload_dict, source="spreaker")
            conflicts.extend(merge_result["conflicts"])
            if merge_result["changed"]:
                session.add(existing)
                updated += 1
        else:
            new_ep = Episode(
                user_id=user.id,
                podcast_id=podcast.id,
                title=payload_dict.get("title") or "Untitled Episode",
                show_notes=payload_dict.get("show_notes"),
                final_audio_path=payload_dict.get("final_audio_path"),
                status=payload_dict.get("status") or EpisodeStatus.processed,
                publish_at=payload_dict.get("publish_at"),
                cover_path=payload_dict.get("cover_path"),
                remote_cover_url=payload_dict.get("remote_cover_url"),
                season_number=payload_dict.get("season_number"),
                episode_number=payload_dict.get("episode_number"),
                is_explicit=payload_dict.get("is_explicit", False),
                spreaker_episode_id=payload_dict.get("spreaker_episode_id"),
                is_published_to_spreaker=True,
                processed_at=payload_dict.get("processed_at"),
                created_at=payload_dict.get("created_at"),
                publish_at_local=payload_dict.get("publish_at_local"),
                source_media_url=payload_dict.get("source_media_url"),
                source_published_at=payload_dict.get("source_published_at"),
            )
            tags = payload_dict.get("tags") or []
            if tags:
                try:
                    new_ep.set_tags(tags)
                except Exception:
                    pass
            meta = payload_dict.get("meta") or {}
            if meta:
                try:
                    new_ep.meta_json = json.dumps(meta)
                except Exception:
                    new_ep.meta_json = json.dumps({})
            session.add(new_ep)
            title_index[title_key] = new_ep
            created += 1

    try:
        state = session.get(PodcastImportState, podcast.id)
        if not state:
            state = PodcastImportState(podcast_id=podcast.id, user_id=user.id)
        state.source = "spreaker"
        state.feed_total = len(items)
        state.imported_count = len(items)
        state.needs_full_import = False
        state.updated_at = datetime.utcnow()
        session.add(state)
    except Exception:
        logging.getLogger("api.importer").warning("Failed to update import state after recovery", exc_info=True)

    return {
        "fetched": len(items),
        "created": created,
        "updated": updated,
        "conflicts": conflicts,
        "duplicates": duplicates_summary,
    }


def push_local_episodes_to_spreaker(
    session: Session,
    podcast: Podcast,
    user: User,
    *,
    publish_state: str = "public",
) -> Dict[str, Any]:
    from api.services.episodes import publisher as episode_publisher

    episodes = session.exec(
        select(Episode).where(Episode.podcast_id == podcast.id, Episode.user_id == user.id)
    ).all()

    started = 0
    skipped_no_audio: List[str] = []
    errors: List[Dict[str, Any]] = []

    for ep in episodes:
        if getattr(ep, "spreaker_episode_id", None):
            continue
        if not getattr(ep, "final_audio_path", None):
            skipped_no_audio.append(str(ep.id))
            continue
        try:
            episode_publisher.publish(
                session=session,
                current_user=user,
                episode_id=ep.id,
                derived_show_id=str(podcast.spreaker_show_id),
                publish_state=publish_state,
                auto_publish_iso=None,
            )
            started += 1
        except Exception as exc:
            errors.append({"episode_id": str(ep.id), "error": str(exc)})

    return {
        "started": started,
        "skipped_no_audio": skipped_no_audio,
        "errors": errors,
    }



