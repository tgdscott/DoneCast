"""Media resolution helpers for episode assembly."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any
from uuid import UUID

from sqlmodel import select

from api.core import crud
from api.core.config import settings
from api.core.paths import APP_ROOT as APP_ROOT_DIR
from api.core.paths import MEDIA_DIR, WS_ROOT as PROJECT_ROOT, CLEANED_DIR
from api.models.podcast import Episode, MediaCategory
# Explicit import to avoid UnboundLocalError when referenced inside helpers
from api.models.podcast import MediaItem
from api.services.audio.common import sanitize_filename


@dataclass
class MediaContext:
    template: Any
    episode: Episode
    user: Any
    # Extracted scalar values to avoid DetachedInstanceError
    user_id: Optional[str]
    episode_id: Optional[str]
    audio_cleanup_settings_json: Optional[str]
    cover_image_path: Optional[str]
    cleanup_settings: dict
    preferred_tts_provider: str
    base_audio_name: str
    source_audio_path: Optional[Path]
    base_stems: list[str]
    search_dirs: list[Path]
    elevenlabs_api_key: Optional[str] = None


def _ensure_media_dir_copy(path: Path) -> Path:
    """Copy *path* into ``MEDIA_DIR`` if needed and return the persistent path."""

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        resolved = path.resolve()
    except Exception:
        resolved = path

    if not resolved.exists() or resolved.is_dir():
        return resolved

    dest = MEDIA_DIR / resolved.name

    try:
        if dest.exists():
            try:
                if resolved.samefile(dest):
                    return dest
            except Exception:
                if dest.resolve() == resolved.resolve():
                    return dest

            try:
                src_stat = resolved.stat()
                dst_stat = dest.stat()
                if (
                    src_stat.st_size == dst_stat.st_size
                    and src_stat.st_mtime <= dst_stat.st_mtime
                ):
                    return dest
            except Exception:
                return dest

        tmp_dest = dest.with_suffix(dest.suffix + ".tmp")
        try:
            if tmp_dest.exists():
                tmp_dest.unlink()
        except Exception:
            pass
        shutil.copy2(resolved, tmp_dest)
        tmp_dest.replace(dest)
        return dest
    except Exception:
        return resolved


def _resolve_media_file(name: str) -> Optional[Path]:
    """Resolve a media filename to a local path."""

    try:
        path = Path(str(name))
        if path.is_absolute() and path.exists():
            return _ensure_media_dir_copy(path)
    except Exception:
        pass

    try:
        raw = str(name)
        if raw.startswith("gs://") or raw.startswith("http"):
            try:
                if raw.startswith("gs://"):
                    without_scheme = raw[len("gs://"):]
                    bucket_name, key = without_scheme.split("/", 1)
                    base = Path(key).name
                    destination = MEDIA_DIR / base
                    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

                    try:
                        from google.cloud import storage  # lazy import

                        client = storage.Client()
                        blob = client.bucket(bucket_name).blob(key)
                        blob.download_to_filename(str(destination))
                        file_size = destination.stat().st_size
                        logging.info(
                            "[assemble] ✅ Downloaded from GCS (direct): %s -> %s (%d bytes)",
                            raw,
                            destination,
                            file_size,
                        )
                        return _ensure_media_dir_copy(destination)
                    except Exception as gcs_err:
                        logging.error(
                            "[assemble] ❌ CRITICAL: Failed to download from GCS %s: %s. "
                            "Worker server needs GCS credentials. Set GOOGLE_APPLICATION_CREDENTIALS "
                            "environment variable pointing to a service account key file, "
                            "or run 'gcloud auth application-default login' to use Application Default Credentials. "
                            "See: https://cloud.google.com/docs/authentication/application-default-credentials",
                            raw,
                            gcs_err,
                            exc_info=True,
                        )
                        raise
                else:
                    logging.warning(
                        "[assemble] Skipping non-GCS URL for intermediate media (expected gs://): %s", raw
                    )
            except Exception as gcs_err:
                logging.error("[assemble] ❌ Failed to download from cloud storage URL %s: %s", raw, gcs_err)
                raise
    except Exception:
        pass

    search_dirs = [
        MEDIA_DIR,
        MEDIA_DIR / "media_uploads",
        PROJECT_ROOT / "media_uploads",
        PROJECT_ROOT / "cleaned_audio",
        APP_ROOT_DIR / "media_uploads",
        APP_ROOT_DIR.parent / "media_uploads",
        CLEANED_DIR,
    ]

    alt_basenames: set[str] = set()

    def _add_alt(candidate: str) -> None:
        if not candidate:
            return
        try:
            alt_basenames.add(candidate)
            alt_basenames.add(Path(candidate).name)
        except Exception:
            alt_basenames.add(candidate)
        try:
            sanitized = sanitize_filename(candidate)
            if sanitized:
                alt_basenames.add(sanitized)
            # Mirror uploader behavior that replaces special characters with underscores
            uploader_style = re.sub(r"[^A-Za-z0-9._-]", "_", candidate)
            if uploader_style:
                alt_basenames.add(uploader_style)
        except Exception:
            pass

    raw_name = str(name)
    _add_alt(raw_name)

    try:
        base = Path(raw_name).name
    except Exception:
        base = raw_name

    _add_alt(base)
    try:
        lower_base = base.lower()
        if lower_base != base:
            _add_alt(lower_base)
    except Exception:
        pass

    for alt in list(alt_basenames):
        for directory in search_dirs:
            candidate = Path(directory) / alt
            if candidate.exists():
                return _ensure_media_dir_copy(candidate)

    return None


def _resolve_image_to_local(path_like: str | Path) -> Optional[Path]:
    """Resolve an image reference (cover art) to a local file path."""

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        candidate = Path(str(path_like))
        if candidate.is_absolute() and candidate.exists():
            return candidate
    except Exception:
        pass

    try:
        raw = str(path_like)
        if raw.startswith("gs://"):
            without = raw[len("gs://"):]
            bucket_name, key = without.split("/", 1)
            base = Path(key).name
            local = MEDIA_DIR / base

            try:
                from google.cloud import storage

                client = storage.Client()
                blob = client.bucket(bucket_name).blob(key)
                blob.download_to_filename(str(local))
                logging.info("[assemble] ✅ Downloaded image from GCS (direct): %s -> %s", raw, local)
                return local
            except Exception as gcs_err:
                logging.error(
                    "[assemble] ❌ Failed to download image from GCS %s: %s. "
                    "Worker server needs GCS credentials. Set GOOGLE_APPLICATION_CREDENTIALS "
                    "environment variable or run 'gcloud auth application-default login'.",
                    raw,
                    gcs_err,
                    exc_info=True,
                )
    except Exception:
        pass

    try:
        raw = str(path_like)
        if raw.lower().startswith(("http://", "https://")):
            import requests

            base = sanitize_filename(Path(raw).name)
            if not any(base.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
                base = f"{Path(base).stem}.jpg"
            local = MEDIA_DIR / base
            resp = requests.get(raw, timeout=10)
            if resp.status_code == 200 and resp.content:
                data = resp.content[: 10 * 1024 * 1024]
                with open(local, "wb") as fh:
                    fh.write(data)
                return local
    except Exception:
        pass

    try:
        base = Path(str(path_like)).name
        for candidate in [
            MEDIA_DIR / base,
            PROJECT_ROOT / "media_uploads" / base,
            APP_ROOT_DIR / "media_uploads" / base,
        ]:
            if candidate.exists():
                return candidate
    except Exception:
        pass

    return None


def _load_cleanup_settings(user_obj) -> dict:
    if not user_obj or not getattr(user_obj, "audio_cleanup_settings_json", None):
        return {}
    try:
        import json

        return json.loads(user_obj.audio_cleanup_settings_json or "{}")
    except Exception:
        return {}


def resolve_media_context(
    *,
    session,
    episode_id: str,
    template_id: str,
    main_content_filename: str,
    output_filename: str,
    episode_details: dict,
    user_id: str,
):
    """Resolve database entities and local media artifacts for assembly."""

    template = crud.get_template_by_id(session, UUID(template_id))
    if not template:
        logging.warning(
            "[assemble] stale job: template %s not found; dropping task", template_id
        )
        try:
            log_path = (PROJECT_ROOT / "assembly_logs") / f"{episode_id}.log"
            log_path.parent.mkdir(exist_ok=True)
            with open(log_path, "w", encoding="utf-8") as fh:
                fh.write(f"[assemble] template not found: {template_id}\n")
        except Exception:
            pass
        return None, None, {"dropped": True, "reason": "template not found", "template_id": template_id}
    
    # Eagerly load template attributes while session is valid to avoid lazy-loading errors later
    try:
        _ = template.timing_json
        _ = template.segments_json
        
        # Resolve music_asset_id to music_filename in background_music_rules
        import json
        from api.models.podcast import MusicAsset
        background_music_rules = json.loads(template.background_music_rules_json or "[]")
        for rule in background_music_rules:
            if rule.get("music_asset_id") and not rule.get("music_filename"):
                # Resolve asset ID to filename
                try:
                    music_asset = session.exec(
                        select(MusicAsset).where(MusicAsset.id == rule["music_asset_id"])
                    ).first()
                    if music_asset:
                        rule["music_filename"] = music_asset.filename
                        logging.info(f"[assemble] Resolved music_asset_id {rule['music_asset_id']} to {music_asset.filename}")
                    else:
                        logging.warning(f"[assemble] music_asset_id {rule['music_asset_id']} not found")
                except Exception as e:
                    logging.error(f"[assemble] Error resolving music_asset_id: {e}")
        # Write back the resolved rules
        template.background_music_rules_json = json.dumps(background_music_rules)
    except Exception:
        logging.debug("[assemble] Failed to eagerly load template attributes", exc_info=True)

    episode = crud.get_episode_by_id(session, UUID(episode_id))
    if not episode:
        logging.warning(
            "[assemble] stale job: episode %s not found; dropping task", episode_id
        )
        try:
            log_path = (PROJECT_ROOT / "assembly_logs") / f"{episode_id}.log"
            log_path.parent.mkdir(exist_ok=True)
            with open(log_path, "w", encoding="utf-8") as fh:
                fh.write(f"[assemble] episode not found: {episode_id}\n")
        except Exception:
            pass
        return None, None, {"dropped": True, "reason": "episode not found", "episode_id": episode_id}

    # CRITICAL: Eagerly load episode attributes while session is still valid
    # This prevents DetachedInstanceError when accessing attributes after session closes
    try:
        _ = episode.user_id  # Force load
        _ = episode.id  # Force load
        _ = episode.status  # Force load
        _ = episode.final_audio_path  # Force load
        _ = episode.title  # Force load
        _ = episode.show_notes  # Force load
        _ = episode.working_audio_name  # Force load
        _ = episode.meta_json  # Force load
    except Exception:
        logging.debug("[assemble] Failed to eagerly load episode attributes", exc_info=True)

    if getattr(episode, "status", None) == "processed" and getattr(
        episode, "final_audio_path", None
    ):
        logging.info(
            "[assemble] duplicate task for already processed episode %s; skipping reassembly",
            episode_id,
        )
        return None, None, {
            "message": "Episode already processed (idempotent skip)",
            "episode_id": episode.id,
        }

    cover_image_path = (episode_details or {}).get("cover_image_path")
    if cover_image_path:
        logging.info("[assemble] cover_image_path from FE: %s", cover_image_path)
        try:
            local_cover = _resolve_image_to_local(cover_image_path)
            if local_cover and local_cover.exists():
                cover_image_path = str(local_cover)
                logging.info(
                    "[assemble] resolved local cover image: %s", cover_image_path
                )
            else:
                # If not found via standard resolution, try database lookup (like template segments)
                # Cover images might be stored as MediaItems with episode_cover category
                logging.info("[assemble] Cover image not found locally, trying database lookup for: %s", cover_image_path)
                try:
                    # Try to find MediaItem by filename or basename
                    cover_filename = str(cover_image_path)
                    cover_basename = Path(cover_filename).name
                    
                    # Search for MediaItem with episode_cover category
                    query = select(MediaItem).where(MediaItem.user_id == UUID(user_id))
                    query = query.where(MediaItem.category == MediaCategory.episode_cover)
                    all_cover_items = list(session.exec(query).all())
                    
                    logging.info("[assemble] Found %d episode_cover MediaItems for user %s", len(all_cover_items), user_id)
                    
                    # Try multiple matching strategies
                    media_item = None
                    for item in all_cover_items:
                        filename = str(item.filename or "")
                        if not filename:
                            continue
                        
                        # Strategy 1: Exact match
                        if filename == cover_filename or filename == cover_basename:
                            media_item = item
                            logging.info("[assemble] Matched cover MediaItem by exact filename: '%s'", filename)
                            break
                        
                        # Strategy 2: Filename ends with basename (for GCS URLs)
                        if filename.endswith(cover_basename):
                            media_item = item
                            logging.info("[assemble] Matched cover MediaItem by ending: '%s' ends with '%s'", filename, cover_basename)
                            break
                        
                        # Strategy 3: Filename contains cover_filename
                        if cover_filename in filename or cover_basename in filename:
                            media_item = item
                            logging.info("[assemble] Matched cover MediaItem by partial: '%s' in '%s'", cover_filename, filename)
                            break
                    
                    if media_item and media_item.filename:
                        resolved_cover_url = str(media_item.filename)
                        logging.info("[assemble] Found cover MediaItem id=%s, filename='%s'", media_item.id, resolved_cover_url)
                        
                        # If MediaItem has GCS URL, download it
                        if resolved_cover_url.startswith("gs://"):
                            try:
                                local_cover = _resolve_image_to_local(resolved_cover_url)
                                if local_cover and local_cover.exists():
                                    cover_image_path = str(local_cover)
                                    logging.info("[assemble] ✅ Downloaded cover from GCS via MediaItem: %s -> %s", resolved_cover_url, cover_image_path)
                                else:
                                    logging.warning("[assemble] Failed to download cover from GCS URL: %s", resolved_cover_url)
                            except Exception as gcs_err:
                                logging.error("[assemble] Failed to download cover from GCS: %s", gcs_err, exc_info=True)
                        elif resolved_cover_url.startswith("http"):
                            # R2 URL - try to download it (though intermediate files should be in GCS)
                            logging.warning("[assemble] Cover MediaItem has R2 URL (should be GCS): %s", resolved_cover_url)
                            try:
                                local_cover = _resolve_image_to_local(resolved_cover_url)
                                if local_cover and local_cover.exists():
                                    cover_image_path = str(local_cover)
                                    logging.info("[assemble] Downloaded cover from R2 URL: %s", resolved_cover_url)
                            except Exception as r2_err:
                                logging.error("[assemble] Failed to download cover from R2: %s", r2_err, exc_info=True)
                        else:
                            logging.warning("[assemble] Cover MediaItem filename is not a GCS/R2 URL: '%s'", resolved_cover_url)
                    else:
                        logging.warning("[assemble] No cover MediaItem found for filename: %s", cover_image_path)
                except Exception as db_err:
                    logging.warning("[assemble] Failed to lookup cover MediaItem: %s", db_err, exc_info=True)
        except Exception:
            logging.warning(
                "[assemble] Failed to resolve local cover image; continuing without embed",
                exc_info=True,
            )

    user_obj = crud.get_user_by_id(session, UUID(user_id)) if hasattr(crud, "get_user_by_id") else None
    
    # CRITICAL: Eagerly load user attributes while session is still valid
    # This prevents DetachedInstanceError when accessing attributes after session closes
    if user_obj:
        try:
            _ = user_obj.email  # Force load
            _ = user_obj.id  # Force load
        except Exception:
            logging.debug("[assemble] Failed to eagerly load user attributes", exc_info=True)
    
    cleanup_settings = _load_cleanup_settings(user_obj)

    preferred_tts_provider = None
    try:
        preferred_tts_provider = (
            (cleanup_settings.get("ttsProvider") or "").strip().lower()
            if isinstance(cleanup_settings, dict)
            else None
        )
    except Exception:
        preferred_tts_provider = None

    if preferred_tts_provider not in {"elevenlabs", "google"}:
        has_env_key = bool(getattr(settings, "ELEVENLABS_API_KEY", None))
        preferred_tts_provider = "elevenlabs" if has_env_key else "google"

    logging.info(
        "[assemble] start: output=%s, template=%s, user=%s",
        output_filename,
        template_id,
        user_id,
    )

    base_stems: list[str] = []
    try:
        base_stems.append(Path(main_content_filename).stem)
    except Exception:
        pass
    try:
        working_name = getattr(episode, "working_audio_name", None)
        if isinstance(working_name, str) and working_name:
            base_stems.append(Path(working_name).stem)
    except Exception:
        pass
    try:
        meta_dict = (
            json.loads(getattr(episode, "meta_json", "{}") or "{}")
            if getattr(episode, "meta_json", None)
            else {}
        )
    except Exception:
        meta_dict = {}
    try:
        cleaned_meta_name = meta_dict.get("cleaned_audio")
        if isinstance(cleaned_meta_name, str) and cleaned_meta_name:
            base_stems.append(Path(cleaned_meta_name).stem)
    except Exception:
        pass
    try:
        if output_filename:
            base_stems.append(Path(output_filename).stem)
    except Exception:
        pass
    base_stems = [s for s in dict.fromkeys([s for s in base_stems if s])]

    search_dirs = [PROJECT_ROOT / "transcripts"]
    try:
        ws_root = PROJECT_ROOT.parent
        if ws_root and (ws_root / "transcripts").exists():
            search_dirs.append(ws_root / "transcripts")
    except Exception:
        pass

    stored_working = getattr(episode, "working_audio_name", None)

    candidate_names: list[str] = []

    def _add_candidate(value: Optional[str]) -> None:
        try:
            candidate = str(value or "").strip()
        except Exception:
            candidate = ""
        if not candidate:
            return
        if candidate not in candidate_names:
            candidate_names.append(candidate)

    try:
        logging.info("[assemble] episode meta snapshot: %s", meta_dict)
    except Exception:
        pass

    _add_candidate(stored_working if isinstance(stored_working, str) else None)
    _add_candidate(meta_dict.get("cleaned_audio") if isinstance(meta_dict.get("cleaned_audio"), str) else None)

    sources_meta = meta_dict.get("cleaned_audio_sources")
    if isinstance(sources_meta, dict):
        for value in sources_meta.values():
            if isinstance(value, str):
                _add_candidate(value)

    for key_name in ("cleaned_audio_gcs_uri", "cleaned_audio_gcs_url"):
        hint = meta_dict.get(key_name)
        if isinstance(hint, str):
            _add_candidate(hint)

    bucket_hint = (
        meta_dict.get("cleaned_audio_bucket")
        if isinstance(meta_dict.get("cleaned_audio_bucket"), str)
        else None
    )
    bucket_hint = (bucket_hint or os.getenv("MEDIA_BUCKET") or "").strip()
    key_hint = meta_dict.get("cleaned_audio_bucket_key")
    if bucket_hint and isinstance(key_hint, str) and key_hint.strip():
        normalized_key = key_hint.strip().lstrip("/")
        _add_candidate(f"gs://{bucket_hint}/{normalized_key}")

    _add_candidate(main_content_filename)

    base_audio_name = Path(str(main_content_filename)).name if main_content_filename else ""
    source_audio_path: Optional[Path] = None

    try:
        logging.info("[assemble] audio resolution candidates: %s", candidate_names)
    except Exception:
        pass

    # First, try to resolve from candidates (might include GCS URLs if already in database)
    for candidate in candidate_names:
        resolved = _resolve_media_file(candidate)
        if resolved and Path(str(resolved)).exists():
            promoted = _ensure_media_dir_copy(Path(str(resolved)))
            if promoted and promoted.exists():
                source_audio_path = promoted
                base_audio_name = promoted.name
                logging.info("[assemble] Resolved audio from candidate: %s -> %s", candidate, source_audio_path)
            else:
                source_audio_path = Path(str(resolved))
                base_audio_name = source_audio_path.name
                logging.info("[assemble] Resolved audio from candidate (direct): %s -> %s", candidate, source_audio_path)
            if candidate != main_content_filename:
                try:
                    episode.working_audio_name = base_audio_name
                    session.add(episode)
                    session.commit()
                except Exception:
                    session.rollback()
            break

    # If file not found, look up MediaItem in database and download from GCS
    file_exists = source_audio_path and Path(str(source_audio_path)).exists()
    if not file_exists:
        basename = Path(str(base_audio_name or main_content_filename)).name
        logging.info("[assemble] Audio file not found locally, looking up MediaItem for: %s (basename: %s)", main_content_filename, basename)
        gcs_uri = None
        media_item = None
        
        # Look up MediaItem by filename - try multiple matching strategies
        try:
            query = select(MediaItem).where(MediaItem.user_id == UUID(user_id))
            query = query.where(MediaItem.category == MediaCategory.main_content)
            all_items = list(session.exec(query).all())
            logging.info("[assemble] Found %d main_content MediaItems for user %s", len(all_items), user_id)
            
            for item in all_items:
                filename = str(getattr(item, "filename", "") or "")
                if not filename:
                    continue
                
                logging.debug("[assemble] Checking MediaItem: id=%s, filename='%s'", item.id, filename)
                
                # Strategy 1: Exact match
                if filename == basename or filename == main_content_filename:
                    media_item = item
                    logging.info("[assemble] Matched MediaItem by exact filename: %s", filename)
                    break
                
                # Strategy 2: Filename ends with basename (for GCS URLs like gs://bucket/path/basename.mp3)
                filename_lower = filename.lower()
                basename_lower = basename.lower()
                if filename_lower.endswith("/" + basename_lower) or filename_lower.endswith(basename_lower):
                    media_item = item
                    logging.info("[assemble] Matched MediaItem by ending: %s (basename: %s)", filename, basename)
                    break
                
                # Strategy 3: Basename is in filename (partial match)
                if basename in filename or filename in basename:
                    media_item = item
                    logging.info("[assemble] Matched MediaItem by partial match: %s (basename: %s)", filename, basename)
                    break
                
                # Strategy 4: Extract basename from filename and compare
                try:
                    filename_basename = Path(filename).name
                    if filename_basename.lower() == basename_lower:
                        media_item = item
                        logging.info("[assemble] Matched MediaItem by extracted basename: %s (basename: %s)", filename, basename)
                        break
                except Exception:
                    pass
        except Exception as e:
            logging.warning("[assemble] Error looking up MediaItem: %s", e, exc_info=True)
            media_item = None
        
        # If MediaItem found, try to get GCS URL
        if media_item:
            filename = str(getattr(media_item, "filename", "") or "")
            logging.info("[assemble] MediaItem filename value: '%s' (starts with gs://: %s, starts with http: %s, length=%d)", 
                        filename, filename.startswith("gs://"), filename.startswith("http"), len(filename))
            logging.info("[assemble] MediaItem details: id=%s, user_id=%s, category=%s, filesize=%s", 
                        media_item.id, media_item.user_id, media_item.category, getattr(media_item, 'filesize', 'N/A'))
            
            if filename.startswith("gs://") or filename.startswith("http"):
                # Direct GCS/R2 URL - download directly
                gcs_uri = filename
                logging.info("[assemble] ✅ Found MediaItem with GCS/R2 URL: %s", gcs_uri)
                logging.info("[assemble] Downloading from cloud storage...")
                try:
                    downloaded_path = _resolve_media_file(gcs_uri)
                    if downloaded_path and Path(str(downloaded_path)).exists():
                        source_audio_path = downloaded_path
                        base_audio_name = Path(str(downloaded_path)).name
                        logging.info("[assemble] ✅ Successfully downloaded from cloud storage: %s -> %s", gcs_uri, source_audio_path)
                    else:
                        logging.error("[assemble] ❌ Failed to download from cloud storage URL: %s", gcs_uri)
                        logging.error("[assemble] Downloaded path: %s, exists: %s", downloaded_path, downloaded_path.exists() if downloaded_path else False)
                except Exception as download_err:
                    logging.error("[assemble] ❌ Exception downloading from cloud storage: %s", download_err, exc_info=True)
                    gcs_uri = None  # Reset so we can try alternative paths
            else:
                # Just a filename - construct GCS path based on upload pattern
                # Main content files are uploaded to: {user_id}/media_uploads/{filename}
                # CRITICAL: Intermediate files are ALWAYS in GCS, never R2
                try:
                    gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
                    # Note: storage_backend is ignored - we always use GCS for intermediate files
                    
                    # Convert user_id to hex format if it's a UUID
                    try:
                        user_uuid = UUID(user_id)
                        user_id_hex = user_uuid.hex
                    except (ValueError, AttributeError):
                        # Already in hex format or invalid
                        user_id_hex = str(user_id).replace("-", "")
                    
                    logging.info("[assemble] Constructing GCS paths for user_id=%s (hex=%s), filename=%s, bucket=%s (intermediate files always in GCS)",
                                user_id, user_id_hex, filename, gcs_bucket)
                    
                    # Try multiple path patterns - the file might be in different locations
                    path_candidates = [
                        f"{user_id_hex}/media_uploads/{filename}",  # New upload pattern
                        f"{user_id_hex}/media/main_content/{filename}",  # Old pattern
                        f"{user_id}/media_uploads/{filename}",  # UUID format (if not converted)
                        f"{user_id}/media/main_content/{filename}",  # UUID format old pattern
                    ]
                    
                    gcs_uri = None
                    # Use GCS client directly to check if file exists (NEVER check R2 for intermediate files)
                    try:
                        from google.cloud import storage as gcs_storage
                        client = gcs_storage.Client()
                        bucket_obj = client.bucket(gcs_bucket)
                        
                        for candidate_key in path_candidates:
                            logging.info("[assemble] Checking GCS path: gs://%s/%s", gcs_bucket, candidate_key)
                            try:
                                blob = bucket_obj.blob(candidate_key)
                                if blob.exists():
                                    gcs_uri = f"gs://{gcs_bucket}/{candidate_key}"
                                    logging.info("[assemble] ✅ Found file at GCS path: %s", gcs_uri)
                                    break
                                else:
                                    logging.debug("[assemble] File not found at: gs://%s/%s", gcs_bucket, candidate_key)
                            except Exception as check_err:
                                logging.warning("[assemble] Error checking path %s: %s", candidate_key, check_err)
                    except Exception as gcs_client_err:
                        logging.error("[assemble] Failed to initialize GCS client for blob existence check: %s", gcs_client_err, exc_info=True)
                    
                    if not gcs_uri:
                        logging.error("[assemble] ❌ File not found in GCS at any of these paths:")
                        for candidate_key in path_candidates:
                            logging.error("[assemble]   - gs://%s/%s", gcs_bucket, candidate_key)
                        logging.error("[assemble] MediaItem filename in DB: '%s'", filename)
                        logging.error("[assemble] MediaItem id: %s", media_item.id)
                        logging.error("[assemble] This suggests the file was not uploaded to GCS, or was uploaded to a different path")
                        logging.error("[assemble] ACTION REQUIRED: Verify the file was uploaded successfully. Check:")
                        logging.error("[assemble]   1. Upload logs to see if GCS upload succeeded")
                        logging.error("[assemble]   2. GCS bucket %s to see if file exists", gcs_bucket)
                        logging.error("[assemble]   3. MediaItem record in database to verify filename matches GCS path")
                        # Try to list files in the user's directory to see what's actually there
                        try:
                            from google.cloud import storage as gcs_storage
                            client = gcs_storage.Client()
                            bucket_obj = client.bucket(gcs_bucket)
                            user_prefix = f"{user_id_hex}/media_uploads/"
                            blobs = list(bucket_obj.list_blobs(prefix=user_prefix, max_results=10))
                            if blobs:
                                logging.info("[assemble] Found %d files in GCS at prefix %s:", len(blobs), user_prefix)
                                for blob in blobs[:5]:  # Show first 5
                                    logging.info("[assemble]   - %s", blob.name)
                            else:
                                logging.warning("[assemble] No files found in GCS at prefix %s", user_prefix)
                        except Exception as list_err:
                            logging.warning("[assemble] Could not list GCS files: %s", list_err)
                except Exception as e:
                    logging.warning("[assemble] Error constructing GCS path: %s", e, exc_info=True)
                    gcs_uri = None
        
        # Download from GCS if we have a URI
        # CRITICAL: Intermediate files are ALWAYS in GCS, not R2
        if gcs_uri:
            logging.info("[assemble] downloading main content from GCS: %s", gcs_uri)
            try:
                download = _resolve_media_file(gcs_uri)
                if download:
                    download_path = Path(str(download))
                    # CRITICAL: Verify file exists immediately after download
                    if download_path.exists():
                        # Ensure the file is in MEDIA_DIR (persistent location)
                        # _ensure_media_dir_copy will copy it if needed, or return the same path if already in MEDIA_DIR
                        promoted = _ensure_media_dir_copy(download_path)
                        
                        # CRITICAL: Verify the promoted path exists and is absolute
                        if promoted and promoted.exists():
                            # Use absolute path to avoid any relative path issues
                            source_audio_path = promoted.resolve()
                            base_audio_name = source_audio_path.name
                            file_size = source_audio_path.stat().st_size
                            
                            # CRITICAL: Double-check file still exists before setting
                            if not source_audio_path.exists():
                                raise RuntimeError(f"File disappeared after copy: {source_audio_path}")
                            
                            logging.info("[assemble] ✅ File downloaded and verified in MEDIA_DIR: %s (exists: True, size: %d bytes, absolute: %s)", 
                                       source_audio_path, file_size, source_audio_path.is_absolute())
                        else:
                            # Fallback: use the download path directly if promotion failed
                            if download_path.exists():
                                source_audio_path = download_path.resolve()
                                base_audio_name = source_audio_path.name
                                file_size = source_audio_path.stat().st_size
                                logging.warning("[assemble] ⚠️ Using download path directly (promotion may have failed): %s (size: %d bytes)", 
                                              source_audio_path, file_size)
                            else:
                                raise FileNotFoundError(f"Downloaded file does not exist: {download_path}")
                    else:
                        raise FileNotFoundError(f"Download returned path that doesn't exist: {download_path}")
                else:
                    raise RuntimeError(f"Download returned None for: {gcs_uri}")
                
                # Save the base_audio_name to the episode
                try:
                    episode.working_audio_name = base_audio_name
                    session.add(episode)
                    session.commit()
                    logging.info("[assemble] Saved working_audio_name to episode: %s", base_audio_name)
                except Exception as save_err:
                    session.rollback()
                    logging.warning("[assemble] Failed to save working_audio_name: %s", save_err)
                
                # CRITICAL: Final verification before returning
                if not source_audio_path or not source_audio_path.exists():
                    raise FileNotFoundError(f"File does not exist at final path: {source_audio_path}")
                
                logging.info("[assemble] ✅ Successfully downloaded and verified main content: %s (size: %d bytes)", 
                           source_audio_path, source_audio_path.stat().st_size)
            except Exception as e:
                logging.error("[assemble] ❌ Exception downloading from GCS %s: %s", gcs_uri, e, exc_info=True)
                # Don't set source_audio_path if download failed - let it fall through to error handling
                source_audio_path = None
                base_audio_name = None

    # Final fallback: try local paths (but these should rarely be needed if GCS download worked)
    if (not source_audio_path) or (not Path(str(source_audio_path)).exists()):
        fallback_name = Path(str(main_content_filename)).name
        logging.info("[assemble] GCS download failed or not attempted, trying local fallback paths for: %s", fallback_name)
        # Try MEDIA_DIR first (actual storage), then workspace fallback
        fallback_candidates = [
            MEDIA_DIR / fallback_name,
            PROJECT_ROOT / "media_uploads" / fallback_name,
        ]
        for candidate in fallback_candidates:
            if candidate.exists():
                source_audio_path = candidate.resolve()
                base_audio_name = fallback_name
                logging.info("[assemble] Found file in local fallback path: %s", source_audio_path)
                break
        else:
            # Fuzzy match: Strip hash and find files with matching suffix
            # Example: b6d5f77e699e444ba31ae1b4cb15feb4_HASH_TheSmashingMachine.mp3
            # Should match any b6d5f77e699e444ba31ae1b4cb15feb4_*_TheSmashingMachine.mp3
            try:
                parts = fallback_name.split('_', 2)  # Split on first 2 underscores
                if len(parts) == 3:
                    user_prefix = parts[0]
                    suffix = parts[2]  # The actual filename part
                    pattern = f"{user_prefix}_*_{suffix}"
                    
                    logging.info(f"[assemble] Exact file not found, trying fuzzy match: {pattern}")
                    
                    for search_dir in [MEDIA_DIR, PROJECT_ROOT / "media_uploads"]:
                        matches = list(search_dir.glob(pattern))
                        if matches:
                            # Use the most recent match
                            match = max(matches, key=lambda p: p.stat().st_mtime)
                            logging.info(f"[assemble] Fuzzy match found: {match.name}")
                            source_audio_path = match.resolve()
                            base_audio_name = match.name
                            break
                    else:
                        logging.warning(f"[assemble] No fuzzy matches found for pattern: {pattern}")
            except Exception as e:
                logging.warning(f"[assemble] Fuzzy match failed: {e}")
            
            # If still not found, use workspace path (will fail later with clear error)
            if not source_audio_path or not Path(str(source_audio_path)).exists():
                source_audio_path = (PROJECT_ROOT / "media_uploads" / fallback_name).resolve()
                base_audio_name = fallback_name

    # Final check - if still no file, log detailed diagnostics
    if not source_audio_path or not Path(str(source_audio_path)).exists():
        logging.info(
            "[assemble] ❌ CRITICAL: Audio file not found after all attempts. main_content_filename=%s, resolved_path=%s",
            main_content_filename,
            source_audio_path
        )
        logging.info(
            "[assemble] Please ensure the file was uploaded to GCS and the MediaItem has the correct filename/GCS URL"
        )
    else:
        logging.info(
            "[assemble] ✅ resolved base audio path=%s", str(source_audio_path)
        )

    words_json_path = None
    for directory in search_dirs:
        for stem in base_stems:
            for name in (
                f"{stem}.json",
                f"{stem}.words.json",
                f"{stem}.original.json",
                f"{stem}.original.words.json",
                f"{stem}.final.json",
                f"{stem}.final.words.json",
                f"{stem}.nopunct.json",
            ):
                candidate = directory / name
                if candidate.is_file():
                    words_json_path = candidate
                    break
            if words_json_path:
                break
        if words_json_path:
            break

    try:
        logging.info(
            "[assemble] resolved words_json_path=%s stems=%s search=%s",
            str(words_json_path) if words_json_path else "None",
            base_stems,
            list(map(str, search_dirs)),
        )
    except Exception:
        pass

    # If not found locally, try episode.meta_json hint for a GCS transcript and download it
    if not words_json_path:
        try:
            import json

            meta = json.loads(getattr(episode, "meta_json", "{}") or "{}") if getattr(episode, "meta_json", None) else {}
            gcs_json = None
            transcripts_meta = meta.get("transcripts") if isinstance(meta, dict) else None
            bucket_name_hint = None
            bucket_stem_hint = None
            candidate_stems: list[str] = []

            def _add_stem(value: Optional[str]) -> None:
                try:
                    normalized = str(value or "").strip()
                except Exception:
                    normalized = ""
                if not normalized:
                    return
                if normalized not in candidate_stems:
                    candidate_stems.append(normalized)

            def _sanitize(value: Optional[str]) -> Optional[str]:
                if not value:
                    return None
                try:
                    sanitized = sanitize_filename(str(value))
                except Exception:
                    return None
                return sanitized or None

            if isinstance(transcripts_meta, dict):
                gcs_json = transcripts_meta.get("gcs_json") or transcripts_meta.get("gcs_url")
                bucket_name_hint = (
                    transcripts_meta.get("gcs_bucket")
                    or transcripts_meta.get("bucket")
                    or transcripts_meta.get("bucket_name")
                )
                bucket_stem_hint = transcripts_meta.get("bucket_stem")
                _add_stem(bucket_stem_hint)
                sanitized_bucket_stem = _sanitize(bucket_stem_hint)
                if sanitized_bucket_stem:
                    _add_stem(sanitized_bucket_stem)
                stem_hint = transcripts_meta.get("stem")
                sanitized_stem_hint = _sanitize(stem_hint)
                if sanitized_stem_hint:
                    _add_stem(sanitized_stem_hint)
                _add_stem(stem_hint)
            if not gcs_json:
                # Some older paths may store at top level
                gcs_json = meta.get("gcs_json") or meta.get("transcript_gcs_json")

            key_from_gcs = None
            bucket_from_gcs = None
            prefix_from_gcs: Optional[str] = None
            base_name_from_key: Optional[str] = None
            suffix_order: list[str] = []
            default_suffixes = [
                "",
                ".words",
                ".original",
                ".original.words",
                ".final",
                ".final.words",
                ".nopunct",
            ]

            if gcs_json and isinstance(gcs_json, str):
                normalized = gcs_json.strip()
                # CRITICAL: Skip R2 URLs - transcripts are ALWAYS in GCS, not R2
                if normalized.startswith("r2://") or "r2.cloudflarestorage.com" in normalized:
                    logging.warning("[assemble] Skipping R2 URL for transcript (transcripts must be in GCS): %s", normalized)
                    gcs_json = None  # Clear so we use bucket fallback instead
                    normalized = ""
                
                try:
                    if normalized.startswith("gs://"):
                        without_scheme = normalized[len("gs://"):]
                    elif "storage.googleapis.com/" in normalized:
                        without_scheme = normalized.split("storage.googleapis.com/", 1)[1]
                    else:
                        without_scheme = ""
                except Exception:
                    without_scheme = ""

                if without_scheme:
                    try:
                        bucket_from_gcs, key_from_gcs = without_scheme.split("/", 1)
                    except Exception:
                        bucket_from_gcs, key_from_gcs = None, None
                else:
                    bucket_from_gcs, key_from_gcs = None, None

            if key_from_gcs:
                try:
                    key_path = Path(key_from_gcs)
                    parent = str(key_path.parent)
                    prefix_from_gcs = parent if parent and parent != "." else None
                    key_name = key_path.name
                    detected_suffix = None
                    for suffix in sorted(default_suffixes, key=len, reverse=True):
                        token = f"{suffix}.json" if suffix else ".json"
                        if key_name.endswith(token):
                            detected_suffix = suffix
                            base_name_from_key = key_name[: -len(token)]
                            break
                    if base_name_from_key is None:
                        base_name_from_key = key_path.stem
                    if detected_suffix is not None:
                        suffix_order.append(detected_suffix)
                    sanitized_base = _sanitize(base_name_from_key)
                    if sanitized_base:
                        _add_stem(sanitized_base)
                    _add_stem(base_name_from_key)
                except Exception:
                    base_name_from_key = None

            for stem in base_stems:
                sanitized = _sanitize(stem)
                if sanitized:
                    _add_stem(sanitized)
                _add_stem(stem)

            for suffix in default_suffixes:
                if suffix not in suffix_order:
                    suffix_order.append(suffix)

            bucket_candidates = [bucket_name_hint, bucket_from_gcs]
            try:
                env_bucket = (os.getenv("TRANSCRIPTS_BUCKET") or os.getenv("MEDIA_BUCKET") or "").strip()
            except Exception:
                env_bucket = ""
            bucket_candidates.append(env_bucket or None)
            bucket_name = None
            for candidate in bucket_candidates:
                if candidate:
                    try:
                        normalized_bucket = str(candidate).strip()
                    except Exception:
                        normalized_bucket = ""
                    if normalized_bucket:
                        bucket_name = normalized_bucket
                        break

            if not prefix_from_gcs:
                prefix_from_gcs = "transcripts"

            candidate_keys: list[tuple[str, str]] = []
            seen_keys: set[str] = set()

            def _compose_key(stem: str, suffix: str) -> str:
                relative = f"{stem}{suffix}.json"
                if prefix_from_gcs:
                    return f"{prefix_from_gcs.rstrip('/')}/{relative}"
                return relative

            for stem in candidate_stems:
                for suffix in suffix_order:
                    candidate_key = _compose_key(stem, suffix)
                    if candidate_key in seen_keys:
                        continue
                    candidate_keys.append((candidate_key, f"{stem}{suffix}" if suffix else stem))
                    seen_keys.add(candidate_key)

            # PRIORITY 1: Try to download directly from stored GCS URI first
            # This ensures transcripts can be found even if environment uses different bucket
            if bucket_from_gcs and key_from_gcs and not words_json_path:
                try:
                    from google.cloud import storage
                    client = storage.Client()
                    bucket_obj = client.bucket(bucket_from_gcs)
                    blob = bucket_obj.blob(key_from_gcs)
                    if blob.exists():
                        data = blob.download_as_bytes()
                        if data:
                            safe_local_name = _sanitize(base_name_from_key) or _sanitize(Path(key_from_gcs).stem) or "transcript"
                            local_path = (PROJECT_ROOT / "transcripts") / f"{safe_local_name}.json"
                            try:
                                local_path.parent.mkdir(parents=True, exist_ok=True)
                                local_path.write_bytes(data)
                                if local_path.exists() and local_path.stat().st_size > 0:
                                    words_json_path = local_path
                                    logging.info(
                                        "[assemble] ✅ Downloaded transcript from stored GCS URI: gs://%s/%s -> %s",
                                        bucket_from_gcs,
                                        key_from_gcs,
                                        local_path,
                                    )
                                else:
                                    logging.warning("[assemble] Downloaded transcript from stored URI but file is empty: gs://%s/%s", bucket_from_gcs, key_from_gcs)
                            except Exception as write_err:
                                logging.warning("[assemble] Failed to write transcript from stored URI to %s: %s", local_path, write_err)
                        else:
                            logging.warning("[assemble] Stored GCS URI exists but returned empty data: gs://%s/%s", bucket_from_gcs, key_from_gcs)
                    else:
                        logging.warning("[assemble] Stored GCS URI does not exist (will try fallback): gs://%s/%s", bucket_from_gcs, key_from_gcs)
                except Exception as direct_download_err:
                    logging.warning(
                        "[assemble] Failed to download from stored GCS URI gs://%s/%s: %s (will try fallback methods)",
                        bucket_from_gcs,
                        key_from_gcs,
                        direct_download_err,
                    )

            if key_from_gcs and key_from_gcs not in seen_keys:
                candidate_keys.append((key_from_gcs, Path(key_from_gcs).stem))
                seen_keys.add(key_from_gcs)

            # PRIORITY 2: Try environment-based lookup (only if stored URI didn't work)
            if bucket_name and candidate_keys and not words_json_path:
                attempted_keys: list[str] = []

                # First try infrastructure.gcs helper (test-friendly, patched in unit tests)
                try:
                    try:
                        from backend.infrastructure import gcs as backend_gcs  # type: ignore
                    except Exception:
                        backend_gcs = gcs

                    for candidate_key, stem_with_suffix in candidate_keys:
                        attempted_keys.append(candidate_key)
                        try:
                            data = backend_gcs.download_gcs_bytes(bucket_name, candidate_key)
                        except Exception as download_err:
                            logging.debug(
                                "[assemble] Failed to download transcript via helper gs://%s/%s: %s",
                                bucket_name,
                                candidate_key,
                                download_err,
                            )
                            continue
                        if not data:
                            continue
                        safe_local_name = _sanitize(stem_with_suffix) or _sanitize(Path(candidate_key).stem) or "transcript"
                        local_path = (PROJECT_ROOT / "transcripts") / f"{safe_local_name}.json"
                        try:
                            local_path.parent.mkdir(parents=True, exist_ok=True)
                            local_path.write_bytes(data)
                        except Exception as write_err:
                            logging.warning("[assemble] Failed to write transcript to %s: %s", local_path, write_err)
                            continue
                        if local_path.exists() and local_path.stat().st_size > 0:
                            words_json_path = local_path
                            logging.info(
                                "[assemble] ✅ Downloaded transcript JSON from GCS: gs://%s/%s -> %s",
                                bucket_name,
                                candidate_key,
                                local_path,
                            )
                            break
                    # If still not found, fall back to direct GCS client
                    if not words_json_path:
                        try:
                            from google.cloud import storage

                            client = storage.Client()
                            bucket_obj = client.bucket(bucket_name)
                            for candidate_key, stem_with_suffix in candidate_keys:
                                if candidate_key in attempted_keys:
                                    pass
                                else:
                                    attempted_keys.append(candidate_key)
                                try:
                                    blob = bucket_obj.blob(candidate_key)
                                    if blob.exists():
                                        data = blob.download_as_bytes()
                                    else:
                                        continue
                                except Exception as download_err:
                                    logging.debug(
                                        "[assemble] Failed to download transcript from GCS gs://%s/%s: %s",
                                        bucket_name,
                                        candidate_key,
                                        download_err,
                                    )
                                    continue
                                if not data:
                                    continue
                                safe_local_name = _sanitize(stem_with_suffix) or _sanitize(Path(candidate_key).stem) or "transcript"
                                local_path = (PROJECT_ROOT / "transcripts") / f"{safe_local_name}.json"
                                try:
                                    local_path.parent.mkdir(parents=True, exist_ok=True)
                                    local_path.write_bytes(data)
                                except Exception as write_err:
                                    logging.warning("[assemble] Failed to write transcript to %s: %s", local_path, write_err)
                                    continue
                                if local_path.exists() and local_path.stat().st_size > 0:
                                    words_json_path = local_path
                                    logging.info(
                                        "[assemble] ✅ Downloaded transcript JSON from GCS: gs://%s/%s -> %s",
                                        bucket_name,
                                        candidate_key,
                                        local_path,
                                    )
                                    break
                        except Exception as gcs_client_err:
                            logging.debug("[assemble] GCS client fallback failed: %s", gcs_client_err)

                    if not words_json_path:
                        if gcs_json:
                            logging.warning(
                                "[assemble] Failed to download transcript JSON from %s (tried keys=%s)",
                                gcs_json,
                                attempted_keys,
                            )
                        elif bucket_stem_hint:
                            logging.warning(
                                "[assemble] Unable to locate transcript JSON in bucket=%s for stems=%s",
                                bucket_name,
                                candidate_stems,
                            )
                except Exception:
                    logging.warning(
                        "[assemble] Failed to download transcript JSON for episode=%s",
                        getattr(episode, "id", episode_id),
                        exc_info=True,
                    )
        except Exception:
            pass

    if not words_json_path:
        bucket_guess = (os.getenv("TRANSCRIPTS_BUCKET") or os.getenv("MEDIA_BUCKET") or "").strip()
        if bucket_guess:
            try:
                # CRITICAL: Use GCS client directly (NEVER use R2 for transcripts)
                from google.cloud import storage
                client = storage.Client()
                bucket_obj = client.bucket(bucket_guess)

                candidate_stems: list[str] = []
                for stem in base_stems:
                    if not stem:
                        continue
                    sanitized = sanitize_filename(str(stem))
                    for candidate in (sanitized, str(stem)):
                        normalized = str(candidate or "").strip()
                        if normalized and normalized not in candidate_stems:
                            candidate_stems.append(normalized)

                for candidate in candidate_stems:
                    key = f"transcripts/{candidate}.json"
                    try:
                        blob = bucket_obj.blob(key)
                        if blob.exists():
                            data = blob.download_as_bytes()
                        else:
                            continue
                    except Exception as download_err:
                        logging.debug("[assemble] Failed to download transcript from GCS gs://%s/%s: %s", 
                                    bucket_guess, key, download_err)
                        continue
                    if not data:
                        continue
                    local_path = (PROJECT_ROOT / "transcripts") / f"{sanitize_filename(candidate)}.json"
                    try:
                        local_path.parent.mkdir(parents=True, exist_ok=True)
                        local_path.write_bytes(data)
                    except Exception as write_err:
                        logging.warning("[assemble] Failed to write transcript to %s: %s", local_path, write_err)
                        continue
                    if local_path.exists() and local_path.stat().st_size > 0:
                        words_json_path = local_path
                        logging.info(
                            "[assemble] ✅ Downloaded transcript JSON from GCS: gs://%s/%s -> %s", 
                            bucket_guess, key, local_path
                        )
                        break
            except Exception as gcs_err:
                logging.warning(
                    "[assemble] Unable to download transcript JSON from configured GCS bucket %s: %s", 
                    bucket_guess, gcs_err, exc_info=True
                )

    # Extract scalar values to avoid DetachedInstanceError when session closes
    user_id_val = str(getattr(episode, "user_id", "") or "").strip() if episode else None
    episode_id_val = str(getattr(episode, "id", "") or "").strip() if episode else None
    audio_settings_json = getattr(user_obj, "audio_cleanup_settings_json", None) if user_obj else None
    elevenlabs_api_key = getattr(user_obj, "elevenlabs_api_key", None) if user_obj else None

    return (
        MediaContext(
            template=template,
            episode=episode,
            user=user_obj,
            user_id=user_id_val,
            episode_id=episode_id_val,
            audio_cleanup_settings_json=audio_settings_json,
            elevenlabs_api_key=elevenlabs_api_key,
            cover_image_path=cover_image_path,
            cleanup_settings=cleanup_settings,
            preferred_tts_provider=preferred_tts_provider,
            base_audio_name=base_audio_name or "",  # Ensure not None
            source_audio_path=Path(str(source_audio_path)).resolve() if source_audio_path else None,
            base_stems=base_stems,
            search_dirs=search_dirs,
        ),
        words_json_path,
        None,
    )

