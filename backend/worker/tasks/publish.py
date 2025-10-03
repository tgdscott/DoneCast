"""Celery task for publishing an episode to Spreaker."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional
from uuid import UUID

from .app import celery_app
from api.core import crud
from api.core.database import get_session
from api.core.paths import FINAL_DIR, MEDIA_DIR, WS_ROOT as PROJECT_ROOT
from api.services.image_utils import ensure_cover_image_constraints
from api.services.episodes.transcripts import transcript_endpoints_for_episode
from api.core.config import settings
from api.services.publisher import SpreakerClient


@celery_app.task(name="publish_episode_to_spreaker_task")
def publish_episode_to_spreaker_task(
    episode_id: str,
    spreaker_show_id: str,
    title: str,
    description: Optional[str],
    auto_published_at: Optional[str],
    spreaker_access_token: str,
    publish_state: str,
) -> dict:
    """Push the final audio to Spreaker and update database state."""

    logging.info("[publish] CWD = %s", os.getcwd())
    session = next(get_session())

    try:
        episode = crud.get_episode_by_id(session, UUID(episode_id))
        if not episode:
            logging.warning(
                "[publish] stale job: episode %s not found; dropping task",
                episode_id,
            )
            return {"dropped": True, "reason": "episode not found", "episode_id": episode_id}

        if not episode.final_audio_path:
            logging.warning(
                "[publish] stale job: episode %s has no final audio; dropping task",
                episode_id,
            )
            return {"dropped": True, "reason": "no final audio", "episode_id": episode_id}

        cover_candidate = getattr(episode, "cover_path", None)
        if not cover_candidate and getattr(episode, "podcast_id", None):
            pod = crud.get_podcast_by_id(session, episode.podcast_id)
            if pod and pod.cover_path:
                cover_candidate = pod.cover_path

        image_file_path: Optional[str] = None
        if isinstance(cover_candidate, str) and cover_candidate:
            cover_candidate = cover_candidate.strip()
            if cover_candidate:
                lower = cover_candidate.lower()
                if lower.startswith(("http://", "https://")):
                    # Already remote; nothing to upload but keep existing metadata
                    image_file_path = None
                else:
                    candidates: list[Path] = []
                    raw_path = Path(cover_candidate)
                    if raw_path.is_file():
                        candidates.append(raw_path)
                    else:
                        base_name = raw_path.name
                        candidate_strings = [
                            cover_candidate,
                            str(raw_path),
                            base_name,
                            f"media_uploads/{cover_candidate}",
                            f"media_uploads/{base_name}",
                        ]
                        unique_strings = []
                        for item in candidate_strings:
                            if item and item not in unique_strings:
                                unique_strings.append(item)
                        for rel in unique_strings:
                            try:
                                candidates.extend(
                                    [
                                        (PROJECT_ROOT / rel).resolve(),
                                        (MEDIA_DIR / rel).resolve(),
                                    ]
                                )
                            except Exception:
                                candidates.append(PROJECT_ROOT / rel)
                                candidates.append(MEDIA_DIR / rel)
                        if base_name:
                            candidates.extend(
                                [
                                    (MEDIA_DIR / base_name).resolve(),
                                    (FINAL_DIR / base_name).resolve(),
                                    (PROJECT_ROOT / "media_uploads" / base_name).resolve(),
                                ]
                            )
                    resolved_cover: Optional[Path] = None
                    for cand in candidates:
                        try:
                            if cand.is_file():
                                resolved_cover = cand
                                break
                        except Exception:
                            continue
                    if resolved_cover:
                        image_file_path = ensure_cover_image_constraints(str(resolved_cover))

        desc = (
            description
            or getattr(episode, "description", None)
            or getattr(episode, "show_notes", None)
            or ""
        )

        audio_path = str(episode.final_audio_path)
        if audio_path and not os.path.isabs(audio_path):
            candidate = (FINAL_DIR / os.path.basename(audio_path)).resolve()
            if candidate.is_file():
                audio_path = str(candidate)
            else:
                alt = (MEDIA_DIR / os.path.basename(audio_path)).resolve()
                if alt.is_file():
                    audio_path = str(alt)
        if not os.path.isfile(audio_path):
            # Final fallback: check media mirror for absolute paths as well
            alt = os.path.join(str(MEDIA_DIR), os.path.basename(audio_path))
            if os.path.isfile(alt):
                audio_path = alt
            else:
                raise RuntimeError(f"Final audio file not found for publishing: {audio_path}")

        # Ensure the episode keeps a stable basename so downstream tooling finds the asset
        try:
            final_basename = os.path.basename(audio_path)
            if final_basename and final_basename != os.path.basename(str(episode.final_audio_path)):
                episode.final_audio_path = final_basename
        except Exception:
            pass

        api_base_url = None
        for candidate in [
            os.getenv("PUBLIC_API_BASE"),
            os.getenv("API_BASE_URL"),
            os.getenv("OAUTH_BACKEND_BASE"),
            getattr(settings, "OAUTH_BACKEND_BASE", None),
            getattr(settings, "APP_BASE_URL", None),
            getattr(settings, "SPREAKER_REDIRECT_URI", None),
        ]:
            cand = (candidate or "").strip() if candidate else ""
            if not cand:
                continue
            parsed = urlparse(cand)
            if not (parsed.scheme and parsed.netloc):
                continue
            host_lower = parsed.netloc.lower()
            path_lower = (parsed.path or "").lower()
            computed: Optional[str] = None
            if "api" in host_lower.split(".") or path_lower.startswith("/api"):
                computed = f"{parsed.scheme}://{parsed.netloc}"
            elif host_lower.startswith("app."):
                swapped = host_lower.replace("app.", "api.", 1)
                computed = f"{parsed.scheme}://{swapped}"
            elif path_lower and "/api/" in path_lower:
                computed = f"{parsed.scheme}://{parsed.netloc}"
            if computed:
                api_base_url = computed.rstrip("/")
                break

        transcript_info = transcript_endpoints_for_episode(episode, api_base_url=api_base_url)
        transcript_url = transcript_info.get("absolute_text") or transcript_info.get("text")

        client = SpreakerClient(spreaker_access_token)

        parsed_auto_str: Optional[str] = None
        if auto_published_at:
            try:
                dt = datetime.fromisoformat(auto_published_at.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                parsed_auto_str = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            except Exception as exc:
                logging.warning(
                    "Invalid auto_published_at '%s': %s; sending without scheduling.",
                    auto_published_at,
                    exc,
                )
                parsed_auto_str = None

        logging.info(
            "[publish] Uploading episode %s to show %s auto_published_at=%s",
            episode_id,
            spreaker_show_id,
            parsed_auto_str,
        )
        if not str(spreaker_show_id).isdigit():
            raise RuntimeError(
                f"Spreaker show id must be numeric; got {spreaker_show_id}"
            )

        tags_arg: Optional[str] = None
        try:
            if hasattr(episode, "tags"):
                tag_list = episode.tags()
                if isinstance(tag_list, (list, tuple)):
                    tags_arg = ",".join(t for t in [str(t).strip() for t in tag_list] if t)
        except Exception:
            pass

        explicit_arg = bool(getattr(episode, "is_explicit", False))

        ok, result = client.upload_episode(
            show_id=str(spreaker_show_id),
            title=title,
            file_path=audio_path,
            description=desc,
            publish_state=publish_state,
            auto_published_at=parsed_auto_str,
            image_file=image_file_path,
            tags=tags_arg,
            explicit=explicit_arg,
            transcript_url=transcript_url,
        )

        if not ok:
            episode.spreaker_publish_error = str(result)
            try:
                import json as _json

                episode.spreaker_publish_error_detail = _json.dumps(result)
            except Exception:
                episode.spreaker_publish_error_detail = None
            session.add(episode)
            session.commit()
            return {"ok": False, "error": str(result)}

        original_auto = parsed_auto_str
        if original_auto:
            if str(getattr(episode, "status", "")) != "published":
                try:
                    from api.models.podcast import EpisodeStatus as _EpStatus

                    episode.status = _EpStatus.processed  # type: ignore[attr-defined]
                except Exception:
                    episode.status = "processed"  # type: ignore[assignment]
            try:
                dt = datetime.strptime(original_auto, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
                episode.publish_at = dt
            except Exception:
                pass
            episode.is_published_to_spreaker = False
        else:
            try:
                from api.models.podcast import EpisodeStatus as _EpStatus

                episode.status = _EpStatus.published  # type: ignore[attr-defined]
            except Exception:
                episode.status = "published"  # type: ignore[assignment]
            episode.is_published_to_spreaker = True

            try:
                desired_private = str(publish_state).lower() in {"unpublished", "private"}
            except Exception:
                desired_private = False
            if desired_private and isinstance(result, dict) and result.get("episode_id"):
                try:
                    ep_id = str(result["episode_id"])
                    ok_upd, upd_resp = client.update_episode(
                        ep_id, publish_state="unpublished", transcript_url=transcript_url
                    )
                    logging.info(
                        "[publish] enforced private via update ok=%s", ok_upd
                    )
                    if not ok_upd:
                        logging.warning(
                            "[publish] private enforce failed: %s", upd_resp
                        )
                except Exception:
                    logging.warning(
                        "[publish] failed to enforce private via update",
                        exc_info=True,
                    )

        remote_stream_url: Optional[str] = None

        try:
            if isinstance(result, dict) and result.get("episode_id"):
                ep_id = str(result["episode_id"])
                ok_ep, ep_resp = client.get_episode(ep_id)
                remote_url = None
                if ok_ep:
                    ep_obj = ep_resp.get("episode") or ep_resp
                    remote_url = (
                        ep_obj.get("image_url")
                        or ep_obj.get("image_original_url")
                        or ep_obj.get("image_large_url")
                    )
                    remote_stream_url = ep_obj.get("download_url") or ep_obj.get("stream_url")
                if not remote_url and image_file_path and os.path.isfile(image_file_path):
                    try:
                        ok_img, _ = client.update_episode_image(ep_id, image_file_path)
                        logging.info(
                            "[publish] attempted episode image update ok=%s", ok_img
                        )
                        if not ok_img:
                            ok_upd_img, _ = client.update_episode(
                                ep_id, image_file=image_file_path, debug_try_all=True
                            )
                            logging.info(
                                "[publish] fallback image update via update_episode ok=%s",
                                ok_upd_img,
                            )
                    except Exception:
                        logging.warning(
                            "[publish] episode image update attempt error",
                            exc_info=True,
                        )
                    ok_ep2, ep_resp2 = client.get_episode(ep_id)
                    if ok_ep2:
                        ep_obj = ep_resp2.get("episode") or ep_resp2
                        remote_url = (
                            ep_obj.get("image_url")
                            or ep_obj.get("image_original_url")
                            or ep_obj.get("image_large_url")
                        )
                        remote_stream_url = remote_stream_url or ep_obj.get("download_url") or ep_obj.get("stream_url")
                if remote_url:
                    if remote_url != getattr(episode, "remote_cover_url", None):
                        setattr(episode, "remote_cover_url", remote_url)
        except Exception:
            logging.warning("[publish] cover sync error", exc_info=True)

        if isinstance(result, dict) and result.get("episode_id"):
            episode.spreaker_episode_id = str(result["episode_id"])
            try:
                meta = json.loads(getattr(episode, "meta_json", "{}") or "{}")
            except Exception:
                meta = {}
            spreaker_meta = meta.get("spreaker")
            if not isinstance(spreaker_meta, dict):
                spreaker_meta = {}
            if remote_stream_url:
                spreaker_meta["remote_audio_url"] = remote_stream_url
                spreaker_meta.setdefault(
                    "remote_audio_first_seen",
                    datetime.now(timezone.utc).isoformat(),
                )

            if transcript_url:
                spreaker_meta["transcript_url"] = transcript_url
                spreaker_meta["transcript_available"] = bool(transcript_info.get("available"))
            meta["spreaker"] = spreaker_meta
            transcripts_meta = meta.get("transcripts")
            if not isinstance(transcripts_meta, dict):
                transcripts_meta = {}
            if transcript_info.get("text"):
                transcripts_meta.setdefault("primary", transcript_info.get("text"))
                transcripts_meta.setdefault("text", transcript_info.get("text"))
            if transcript_info.get("json"):
                transcripts_meta.setdefault("json", transcript_info.get("json"))
            if transcript_info.get("absolute_text"):
                transcripts_meta.setdefault("absolute_text", transcript_info.get("absolute_text"))
            transcripts_meta["available"] = bool(transcript_info.get("available"))
            meta["transcripts"] = transcripts_meta
            try:
                episode.meta_json = json.dumps(meta)
            except Exception:
                logging.warning("[publish] Failed to encode spreaker metadata", exc_info=True)

        episode.spreaker_publish_error = None
        episode.spreaker_publish_error_detail = None
        episode.needs_republish = False
        session.add(episode)
        session.commit()

        logging.info(
            "Published to Spreaker: %s (id=%s)",
            episode.title,
            episode.spreaker_episode_id,
        )
        try:
            from api.models.notification import Notification

            note = Notification(
                user_id=episode.user_id,
                type="publish",
                title="Episode published",
                body=f"{episode.title}",
            )
            session.add(note)
            session.commit()
        except Exception:
            logging.warning("[publish] Failed to create notification", exc_info=True)

        return {"ok": True, "episode_id": episode.id, "result": result}
    except Exception as exc:
        logging.exception("[publish] error for episode %s: %s", episode_id, exc)
        raise
    finally:
        try:
            session.close()
        except Exception:
            pass
