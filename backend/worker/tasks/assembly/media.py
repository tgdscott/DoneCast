"""Media resolution helpers for episode assembly."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlmodel import select

from api.core import crud
from api.core.config import settings
from api.core.paths import APP_ROOT as APP_ROOT_DIR
from api.core.paths import MEDIA_DIR, WS_ROOT as PROJECT_ROOT
from api.models.podcast import Episode, MediaCategory, MediaItem
from api.services.audio.common import sanitize_filename


@dataclass
class MediaContext:
    template: any
    episode: Episode
    user: any
    cover_image_path: Optional[str]
    cleanup_settings: dict
    preferred_tts_provider: str
    base_audio_name: str
    source_audio_path: Optional[Path]
    base_stems: list[str]
    search_dirs: list[Path]


def _resolve_media_file(name: str) -> Optional[Path]:
    """Resolve a media filename to a local path."""

    try:
        path = Path(str(name))
        if path.is_absolute() and path.exists():
            return path
    except Exception:
        pass

    try:
        raw = str(name)
        if raw.startswith("gs://"):
            try:
                without_scheme = raw[len("gs://"):]
                bucket_name, key = without_scheme.split("/", 1)
                base = Path(key).name
                destination = MEDIA_DIR / base
                MEDIA_DIR.mkdir(parents=True, exist_ok=True)
                from google.cloud import storage  # lazy import

                client = storage.Client()
                blob = client.bucket(bucket_name).blob(key)
                blob.download_to_filename(str(destination))
                return destination
            except Exception:
                pass
    except Exception:
        pass

    try:
        base = Path(str(name)).name
    except Exception:
        base = str(name)

    candidates = [
        PROJECT_ROOT / "media_uploads" / base,
        APP_ROOT_DIR / "media_uploads" / base,
        APP_ROOT_DIR.parent / "media_uploads" / base,
        MEDIA_DIR / base,
    ]
    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate
        except Exception:
            continue
    return None


def _resolve_image_to_local(path_like: str | None) -> Optional[Path]:
    if not path_like:
        return None

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
            from google.cloud import storage

            client = storage.Client()
            blob = client.bucket(bucket_name).blob(key)
            blob.download_to_filename(str(local))
            return local
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
            PROJECT_ROOT / "media_uploads" / base,
            APP_ROOT_DIR / "media_uploads" / base,
            MEDIA_DIR / base,
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
        except Exception:
            logging.warning(
                "[assemble] Failed to resolve local cover image; continuing without embed",
                exc_info=True,
            )

    user_obj = crud.get_user_by_id(session, UUID(user_id)) if hasattr(crud, "get_user_by_id") else None
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
        has_user_key = bool(getattr(user_obj, "elevenlabs_api_key", None))
        has_env_key = bool(getattr(settings, "ELEVENLABS_API_KEY", None))
        preferred_tts_provider = "elevenlabs" if (has_user_key or has_env_key) else "google"

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

    base_audio_name = getattr(episode, "working_audio_name", None) or main_content_filename
    source_audio_path = _resolve_media_file(base_audio_name) or (
        PROJECT_ROOT / "media_uploads" / Path(str(base_audio_name)).name
    )

    try:
        if (not source_audio_path) or (not Path(str(source_audio_path)).exists()):
            basename = Path(str(base_audio_name)).name
            gcs_uri = None
            try:
                query = select(MediaItem).where(MediaItem.user_id == UUID(user_id))
                query = query.where(MediaItem.category == MediaCategory.main_content)
                for item in session.exec(query).all():
                    filename = str(getattr(item, "filename", "") or "")
                    if filename.startswith("gs://") and filename.rstrip().lower().endswith("/" + basename.lower()):
                        gcs_uri = filename
                        break
            except Exception:
                gcs_uri = None
            if gcs_uri:
                logging.info("[assemble] downloading main content from GCS: %s", gcs_uri)
                download = _resolve_media_file(gcs_uri)
                if download and Path(str(download)).exists():
                    source_audio_path = Path(str(download))
                    base_audio_name = Path(str(download)).name
                    try:
                        episode.working_audio_name = base_audio_name
                        session.add(episode)
                        session.commit()
                    except Exception:
                        session.rollback()
    except Exception:
        pass

    try:
        logging.info(
            "[assemble] resolved base audio path=%s", str(source_audio_path)
        )
    except Exception:
        pass

    words_json_path = None
    for directory in search_dirs:
        for stem in base_stems:
            candidate = directory / f"{stem}.json"
            legacy = directory / f"{stem}.words.json"
            if candidate.is_file():
                words_json_path = candidate
                break
            if legacy.is_file():
                words_json_path = legacy
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

    return (
        MediaContext(
            template=template,
            episode=episode,
            user=user_obj,
            cover_image_path=cover_image_path,
            cleanup_settings=cleanup_settings,
            preferred_tts_provider=preferred_tts_provider,
            base_audio_name=base_audio_name,
            source_audio_path=Path(str(source_audio_path))
            if source_audio_path
            else None,
            base_stems=base_stems,
            search_dirs=search_dirs,
        ),
        words_json_path,
        None,
    )

