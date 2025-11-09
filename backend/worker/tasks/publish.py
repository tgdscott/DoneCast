"""Celery task for publishing an episode to Spreaker."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, unquote
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

        # Check for cover image - priority: gcs_cover_path (R2 URL) > cover_path (local filename) > podcast cover
        cover_candidate = getattr(episode, "gcs_cover_path", None) or getattr(episode, "cover_path", None)
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
                    # Cover is in R2 - download it for publishing
                    logging.info("[publish] Cover image is in R2, downloading: %s", cover_candidate)
                    try:
                        import tempfile
                        from infrastructure import r2 as r2_storage
                        
                        # Parse R2 URL to extract bucket and key (same logic as audio)
                        try:
                            url_path = cover_candidate.replace("https://", "").replace("http://", "")
                            parts = url_path.split("/", 1)
                            if len(parts) != 2:
                                raise ValueError(f"Invalid R2 URL format: {cover_candidate}")
                            
                            domain_part = parts[0]
                            key = unquote(parts[1])  # URL-decode the key (R2 URLs may be URL-encoded)
                            
                            domain_parts = domain_part.split(".")
                            if len(domain_parts) < 5 or domain_parts[-4:] != ["r2", "cloudflarestorage", "com"]:
                                raise ValueError(f"Invalid R2 URL domain format: {domain_part}")
                            
                            bucket_name = domain_parts[0]
                            
                            logging.info("[publish] Parsed R2 cover URL: bucket=%s, key=%s", bucket_name, key)
                            
                            # Download using R2 client
                            file_bytes = r2_storage.download_bytes(bucket_name, key)
                            if not file_bytes:
                                raise RuntimeError(f"R2 download returned None for bucket={bucket_name}, key={key}")
                            
                            # Save to temp file
                            temp_fd, temp_path = tempfile.mkstemp(suffix=".jpg")
                            os.close(temp_fd)
                            with open(temp_path, "wb") as f:
                                f.write(file_bytes)
                            
                            # Ensure cover image constraints (size, format, etc.)
                            image_file_path = ensure_cover_image_constraints(temp_path)
                            logging.info("[publish] Downloaded and processed cover from R2: bucket=%s, key=%s (%d bytes)", 
                                       bucket_name, key, os.path.getsize(image_file_path) if image_file_path else 0)
                        except (ValueError, RuntimeError) as parse_err:
                            logging.error("[publish] Failed to parse or download R2 cover URL: %s", parse_err, exc_info=True)
                            # Fall through to local file lookup
                    except Exception as cover_err:
                        logging.warning("[publish] Failed to download cover from R2, trying local lookup: %s", cover_err)
                        # Fall through to local file lookup
                
                # If not an R2 URL or download failed, try local file lookup
                if not image_file_path:
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

        audio_path = str(episode.final_audio_path or "")
        
        # Check if we have an R2 URL stored (final files are in R2)
        r2_audio_url = getattr(episode, 'gcs_audio_path', None) or getattr(episode, 'r2_audio_path', None)
        if r2_audio_url and (r2_audio_url.startswith("https://") or r2_audio_url.startswith("http://")):
            # Audio is in R2 - download it using R2 client (R2 URLs require authentication)
            logging.info("[publish] Audio is in R2, downloading: %s", r2_audio_url)
            try:
                import tempfile
                from infrastructure import r2 as r2_storage
                
                # Parse R2 URL to extract bucket and key
                # Format: https://ppp-media.{account_id}.r2.cloudflarestorage.com/{key}
                # Or: https://{bucket}.{account_id}.r2.cloudflarestorage.com/{key}
                try:
                    # Remove https:// prefix
                    url_path = r2_audio_url.replace("https://", "").replace("http://", "")
                    # Split by first /
                    parts = url_path.split("/", 1)
                    if len(parts) != 2:
                        raise ValueError(f"Invalid R2 URL format: {r2_audio_url}")
                    
                    # Extract bucket from subdomain (format: bucket.account_id.r2.cloudflarestorage.com)
                    domain_part = parts[0]
                    key = unquote(parts[1])  # URL-decode the key (R2 URLs may be URL-encoded)
                    
                    # Parse bucket from domain (bucket.account_id.r2.cloudflarestorage.com)
                    domain_parts = domain_part.split(".")
                    if len(domain_parts) < 5 or domain_parts[-4:] != ["r2", "cloudflarestorage", "com"]:
                        raise ValueError(f"Invalid R2 URL domain format: {domain_part}")
                    
                    bucket_name = domain_parts[0]
                    
                    logging.info("[publish] Parsed R2 audio URL: bucket=%s, key=%s", bucket_name, key)
                    
                    # Download using R2 client
                    file_bytes = r2_storage.download_bytes(bucket_name, key)
                    if not file_bytes:
                        raise RuntimeError(f"R2 download returned None for bucket={bucket_name}, key={key}")
                    
                    # Save to temp file
                    temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
                    os.close(temp_fd)
                    with open(temp_path, "wb") as f:
                        f.write(file_bytes)
                    
                    audio_path = temp_path
                    logging.info("[publish] Downloaded audio from R2: bucket=%s, key=%s (%d bytes)", bucket_name, key, os.path.getsize(temp_path))
                except Exception as parse_err:
                    logging.error("[publish] Failed to parse R2 URL: %s", parse_err, exc_info=True)
                    raise RuntimeError(f"Failed to parse R2 URL for downloading: {r2_audio_url}") from parse_err
            except Exception as r2_err:
                logging.error("[publish] Failed to download audio from R2: %s", r2_err, exc_info=True)
                raise RuntimeError(f"Failed to download audio from R2 for publishing: {r2_err}") from r2_err
        
        # Try to resolve local path if we have a filename
        if audio_path and not os.path.isabs(audio_path) and not audio_path.startswith("http"):
            candidate = (FINAL_DIR / os.path.basename(audio_path)).resolve()
            if candidate.is_file():
                audio_path = str(candidate)
            else:
                alt = (MEDIA_DIR / os.path.basename(audio_path)).resolve()
                if alt.is_file():
                    audio_path = str(alt)
        
        # Verify file exists
        if not os.path.isfile(audio_path) and not audio_path.startswith("http"):
            # Final fallback: check media mirror for absolute paths as well
            alt = os.path.join(str(MEDIA_DIR), os.path.basename(audio_path))
            if os.path.isfile(alt):
                audio_path = alt
            else:
                # Last resort: check if we can download from R2 using the filename
                if not r2_audio_url:
                    raise RuntimeError(f"Final audio file not found for publishing: {audio_path}")
                # If we have r2_audio_url but download failed above, re-raise that error
                raise RuntimeError(f"Final audio file not found for publishing: {audio_path} (and R2 download failed)")

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
            # season_number/episode_number removed - Spreaker auto-assigns these,
            # ignoring our values and causing numbering conflicts. No longer sent.
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
                        ep_id,
                        publish_state="unpublished",
                        transcript_url=transcript_url,
                        # season_number/episode_number removed
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
                                ep_id,
                                image_file=image_file_path,
                                debug_try_all=True,
                                # season_number/episode_number removed
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
