from __future__ import annotations

"""Compatibility shim for transcription service.

This package name shadows the legacy module ``api.services.transcription``. Some
code imports the package (``from api.services import transcription``) while
others import specific modules such as
``api.services.transcription.assemblyai_client``. This module keeps both styles
working by providing the original helper functions and exporting the nested
modules.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import logging
import os
import uuid

from ...core.paths import MEDIA_DIR, TRANSCRIPTS_DIR
from .watchers import notify_watchers_processed, mark_watchers_failed, _candidate_filenames
from ..audio.common import sanitize_filename


class TranscriptionError(Exception):
    """Generic transcription failure."""


def _resolve_transcripts_bucket() -> str:
    bucket = (os.getenv("TRANSCRIPTS_BUCKET") or "").strip()
    fallback = (os.getenv("MEDIA_BUCKET") or "").strip()
    chosen = bucket or fallback
    if not chosen:
        raise TranscriptionError("Transcript bucket not configured")
    return chosen


def get_word_timestamps(filename: str) -> List[Dict[str, Any]]:
    """Return per-word timestamps for an uploaded media file.

    Strategy:
      1. AssemblyAI with speakers (preferred)
      2. Google Speech word offsets (adds ``speaker=None``)

    Raises on failure to keep callers' error handling consistent.
    """

    audio_path = MEDIA_DIR / filename
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {filename}")

    # Prefer AssemblyAI. Import lazily to avoid optional deps during package import.
    try:
        from ..transcription_assemblyai import assemblyai_transcribe_with_speakers  # local import
        logging.info("[transcription/pkg] Using AssemblyAI with disfluencies=True")
        return assemblyai_transcribe_with_speakers(filename)
    except Exception:
        logging.warning("[transcription/pkg] AssemblyAI failed; falling back to Google", exc_info=True)

    try:
        # Lazy import to avoid ImportError if google-cloud-speech isn't installed in test envs
        from ..transcription_google import google_transcribe_with_words  # local import
        words = google_transcribe_with_words(filename)
        for w in words:
            if "speaker" not in w:
                w["speaker"] = None
        return words
    except Exception:
        logging.warning("[transcription/pkg] Google fallback failed", exc_info=True)
        raise NotImplementedError("Only AssemblyAI and Google transcription are supported.")


def _is_gcs_path(path: str) -> bool:
    return isinstance(path, str) and path.startswith("gs://")


def _download_gcs_to_media(gcs_uri: str) -> str:
    """Download ``gs://bucket/key`` to ``MEDIA_DIR`` and return the local filename."""

    try:
        from google.cloud import storage  # type: ignore - optional dependency in tests
    except Exception as exc:  # pragma: no cover - optional dependency missing in tests
        raise RuntimeError("google-cloud-storage not installed") from exc

    without_scheme = gcs_uri[len("gs://") :]
    bucket_name, key = without_scheme.split("/", 1)
    dst_name = os.path.basename(key) or "audio"
    dst_path = MEDIA_DIR / dst_name
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(key)
    blob.download_to_filename(str(dst_path))
    return dst_name


def _store_media_transcript_metadata(
    filename: str,
    *,
    stem: Optional[str] = None,
    safe_stem: Optional[str] = None,
    bucket: Optional[str] = None,
    key: Optional[str] = None,
    gcs_uri: Optional[str] = None,
    gcs_url: Optional[str] = None,
) -> None:
    """Persist transcript metadata for a media upload for future reuse."""

    logger = logging.getLogger("transcription")
    
    cleaned = (filename or "").strip()
    logger.info("[transcript_save] 🔍 ENTER: filename='%s'", cleaned)
    
    if not cleaned:
        logger.warning("[transcript_save] ❌ SKIP: Empty filename")
        return

    payload: Dict[str, Any] = {}
    if stem:
        payload["stem"] = stem
    if safe_stem:
        payload["bucket_stem"] = safe_stem
    if bucket:
        payload["gcs_bucket"] = bucket
    if key:
        payload["gcs_key"] = key
    if gcs_uri:
        payload["gcs_json"] = gcs_uri
    if gcs_url:
        payload.setdefault("gcs_url", gcs_url)

    logger.info("[transcript_save] 📦 Payload keys: %s", list(payload.keys()))
    
    if not payload:
        logger.warning("[transcript_save] ❌ SKIP: Empty payload")
        return

    try:
        from sqlmodel import Session, select

        from api.core import database as db
        from api.models.podcast import MediaItem
        from api.models.transcription import MediaTranscript
        
        logger.info("[transcript_save] ✅ Imports successful")
    except Exception as import_exc:
        logger.error(
            "[transcript_save] ❌ FATAL: Import failed: %s", import_exc, exc_info=True
        )
        return

    candidates = _candidate_filenames(cleaned)
    if cleaned not in candidates:
        candidates.insert(0, cleaned)
    
    logger.info("[transcript_save] 🔎 Candidate filenames: %s", candidates)

    try:
        logger.info("[transcript_save] 🔌 Opening database session...")
        with Session(db.engine) as session:
            logger.info("[transcript_save] 🔍 Searching for MediaItem in candidates...")
            media_item = session.exec(
                select(MediaItem).where(MediaItem.filename.in_(candidates))
            ).first()
            media_item_id = getattr(media_item, "id", None) if media_item else None
            
            logger.info("[transcript_save] MediaItem: id=%s", media_item_id)

            logger.info("[transcript_save] 🔍 Searching for existing MediaTranscript...")
            existing = session.exec(
                select(MediaTranscript).where(MediaTranscript.filename.in_(candidates))
            ).all()
            
            logger.info("[transcript_save] Found %d existing MediaTranscript records", len(existing))

            target = None
            for record in existing:
                if str(record.filename).strip() == cleaned:
                    target = record
                    break
            if target is None and existing:
                target = existing[0]

            serialized = json.dumps(payload)
            now = datetime.utcnow()

            if target is not None:
                logger.info("[transcript_save] ♻️ Updating existing MediaTranscript id=%s", target.id)
                target.filename = cleaned
                target.transcript_meta_json = serialized
                target.updated_at = now
                if media_item_id:
                    target.media_item_id = media_item_id
                session.add(target)
            else:
                logger.info("[transcript_save] ➕ Creating NEW MediaTranscript")
                new_record = MediaTranscript(
                    media_item_id=media_item_id,
                    filename=cleaned,
                    transcript_meta_json=serialized,
                    created_at=now,
                    updated_at=now,
                )
                session.add(new_record)
                logger.info("[transcript_save] MediaTranscript record created in session")

            logger.info("[transcript_save] 💾 Committing to database...")
            session.commit()
            logger.info("[transcript_save] ✅ SUCCESS: MediaTranscript saved for '%s'", cleaned)
    except Exception as db_exc:
        logger.error(
            "[transcript_save] ❌ DATABASE ERROR for '%s': %s", 
            cleaned, 
            db_exc, 
            exc_info=True
        )


def load_media_transcript_metadata_for_filename(session, filename: str) -> Dict[str, Any] | None:
    """Fetch stored transcript metadata for the provided media filename."""

    if session is None:
        return None

    cleaned = (filename or "").strip()
    if not cleaned:
        return None

    candidates = _candidate_filenames(cleaned)
    if cleaned not in candidates:
        candidates.insert(0, cleaned)

    try:
        from api.models.transcription import MediaTranscript
        from sqlmodel import select
    except Exception:
        return None

    try:
        records = session.exec(
            select(MediaTranscript).where(MediaTranscript.filename.in_(candidates))
        ).all()
    except Exception:
        return None

    target_stem = None
    try:
        target_stem = Path(cleaned).stem
    except Exception:
        target_stem = cleaned

    if (not records) and target_stem:
        try:
            all_records = session.exec(select(MediaTranscript)).all()
        except Exception:
            all_records = []
        normalized_target = str(target_stem or "").strip().lower()
        for record in all_records:
            try:
                payload = json.loads(record.transcript_meta_json or "{}")
            except Exception:
                continue
            candidates_stem = {
                str(payload.get("stem") or "").strip().lower(),
                str(payload.get("bucket_stem") or "").strip().lower(),
            }
            if normalized_target and normalized_target in candidates_stem:
                records = [record]
                break

    if not records:
        return None

    preferred = None
    for record in records:
        if str(record.filename).strip() == cleaned:
            preferred = record
            break
    if preferred is None:
        preferred = records[0]

    try:
        return json.loads(preferred.transcript_meta_json or "{}")
    except Exception:
        return None


def _read_existing_transcript_for(filename: str) -> List[Dict[str, Any]] | None:
    """Return transcript words if an existing JSON is present for filename.

    Checks TRANSCRIPTS_DIR and a workspace-level transcripts folder for common
    variants, reusing existing artifacts to avoid re-transcription.
    """
    try:
        stem = Path(filename).stem
    except Exception:
        stem = Path(str(filename)).stem

    candidates = [
        TRANSCRIPTS_DIR / f"{stem}.json",
        TRANSCRIPTS_DIR / f"{stem}.words.json",
    ]
    # Workspace-level transcripts directory
    try:
        ws_root = MEDIA_DIR.parent  # WS_ROOT
        ws_tr = ws_root / "transcripts"
        candidates.extend([ws_tr / f"{stem}.json", ws_tr / f"{stem}.words.json"])
    except Exception:
        pass

    for path in candidates:
        try:
            if path.is_file():
                data = path.read_text(encoding="utf-8")
                return json.loads(data)
        except Exception:
            continue
    return None


def transcribe_media_file(filename: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Synchronously transcribe a media file and persist transcript artifacts.
    
    Routes to appropriate transcription service based on user subscription tier:
    - Pro users → Auphonic (transcription + audio processing)
    - Other tiers → AssemblyAI (transcription only)
    
    Args:
        filename: GCS URL or local path to audio file
        user_id: UUID string of user (required for tier-based routing)
        
    Returns:
        List of word dicts with start/end/word/speaker keys
    """

    # DEBUG: Log what we received
    logging.info(f"[transcription] 🎬 CALLED with filename={filename}, user_id={user_id!r} (type={type(user_id).__name__})")
    
    # ========== IDEMPOTENCY CHECK: Prevent duplicate transcriptions ==========
    # Critical for container restarts: if this file is already transcribed, return cached result
    try:
        from api.core.database import get_session
        from api.models.transcription import MediaTranscript
        from sqlmodel import select
        
        session = next(get_session())
        
        # Check if transcript already exists for this filename
        existing_transcript = session.exec(
            select(MediaTranscript).where(MediaTranscript.filename == filename)
        ).first()
        
        if existing_transcript:
            logging.warning(
                "[transcription] ⚠️ IDEMPOTENCY: Transcript already exists for %s (created %s) - returning cached result to prevent duplicate charges",
                filename,
                existing_transcript.created_at
            )
            
            # Return cached transcript data
            try:
                import json
                transcript_meta = json.loads(existing_transcript.transcript_meta_json or "{}")
                if transcript_meta.get("words"):
                    logging.info(
                        "[transcription] ✅ Returning %d words from cached transcript",
                        len(transcript_meta["words"])
                    )
                    return transcript_meta["words"]
                else:
                    logging.warning("[transcription] ⚠️ Cached transcript has no words, will re-transcribe")
            except Exception as cache_err:
                logging.error("[transcription] ❌ Failed to parse cached transcript: %s", cache_err)
                # Fall through to re-transcribe if cache is corrupt
    except Exception as idempotency_err:
        logging.error("[transcription] ⚠️ Idempotency check failed (non-fatal): %s", idempotency_err)
        # Fall through to transcribe if idempotency check fails
    # ========== END IDEMPOTENCY CHECK ==========

    # ========== CHARGE CREDITS FOR TRANSCRIPTION (UPFRONT) ==========
    # We charge upfront even if transcription fails because we pay the API regardless
    if user_id:
        try:
            from api.core.database import get_session
            from api.models.user import User
            from api.services.billing import credits
            from api.services.auphonic_helper import should_use_auphonic
            from sqlmodel import select
            from pydub import AudioSegment
            
            session = next(get_session())
            user = session.exec(select(User).where(User.id == user_id)).first()
            
            if user:
                # Get audio duration
                try:
                    if _is_gcs_path(filename):
                        local_filename = _download_gcs_to_media(filename)
                        audio_path = MEDIA_DIR / local_filename
                    else:
                        audio_path = MEDIA_DIR / filename
                    
                    audio = AudioSegment.from_file(str(audio_path))
                    duration_minutes = len(audio) / 1000 / 60
                    
                    # Check if user is Pro tier (Auphonic) or other tiers (AssemblyAI)
                    use_auphonic_flag = should_use_auphonic(user)
                    
                    logging.info(
                        "[transcription] 💳 Charging credits: user=%s, duration=%.2f min, auphonic=%s",
                        user.id,
                        duration_minutes,
                        use_auphonic_flag
                    )
                    
                    ledger_entry, cost_breakdown = credits.charge_for_transcription(
                        session=session,
                        user=user,
                        duration_minutes=duration_minutes,
                        use_auphonic=use_auphonic_flag,
                        correlation_id=f"transcription_{filename}_{uuid.uuid4().hex[:8]}",
                    )
                    
                    logging.info(
                        "[transcription] ✅ Credits charged: %.2f credits (pipeline=%s, multiplier=%.2fx)",
                        cost_breakdown['total_credits'],
                        cost_breakdown['pipeline'],
                        cost_breakdown['multiplier']
                    )
                    
                except Exception as audio_err:
                    logging.warning("[transcription] ⚠️ Could not determine audio duration for billing: %s", audio_err)
                    # Don't fail transcription if billing fails
                    
        except Exception as credits_err:
            logging.error("[transcription] ⚠️ Failed to charge credits (non-fatal): %s", credits_err, exc_info=True)
            # Don't fail transcription if credit charging fails
    # ========== END CREDIT CHARGING ==========

    # If user_id not provided, fall back to legacy behavior (AssemblyAI)
    if user_id:
        try:
            from api.core.database import get_session
            from api.models.user import User
            from api.services.auphonic_helper import should_use_auphonic
            from sqlmodel import select

            session = next(get_session())
            logging.info(f"[transcription] 🔍 Looking up user_id={user_id}")
            user = session.exec(select(User).where(User.id == user_id)).first()

            if not user:
                logging.warning(f"[transcription] ⚠️ User not found: user_id={user_id}, falling back to AssemblyAI")
            else:
                logging.info(f"[transcription] ✅ Found user: id={user.id}, email={user.email}, tier={getattr(user, 'tier', 'NONE')}")

            if user and should_use_auphonic(user):
                # Pro user → Auphonic
                logging.info(f"[transcription] user_id={user_id} tier={getattr(user, 'tier', 'unknown')} → Auphonic")
                
                from api.services.transcription_auphonic import auphonic_transcribe_and_process
                
                result = auphonic_transcribe_and_process(filename, str(user_id))
                
                # Update MediaItem with Auphonic outputs
                from api.models.podcast import MediaItem
                
                # Find MediaItem by filename (could be partial match for GCS URLs)
                filename_search = filename.split("/")[-1] if "/" in filename else filename
                media_item = session.exec(
                    select(MediaItem)
                    .where(MediaItem.user_id == user.id)
                    .where(MediaItem.filename.contains(filename_search))
                    .order_by(MediaItem.created_at.desc())
                ).first()
                
                if media_item:
                    media_item.auphonic_processed = True
                    media_item.auphonic_cleaned_audio_url = result.get("cleaned_audio_url")
                    media_item.auphonic_original_audio_url = result.get("original_audio_url")
                    
                    # Save Auphonic metadata (legacy format for backward compatibility)
                    if result.get("auphonic_output_file"):
                        media_item.auphonic_output_file = result["auphonic_output_file"]
                    
                    # Store AI-generated metadata and chapters as JSON
                    auphonic_meta = {}
                    
                    # Legacy show_notes support (deprecated in favor of brief_summary)
                    if result.get("show_notes"):
                        auphonic_meta["show_notes"] = result["show_notes"]
                    
                    # NEW: AI-generated summaries
                    if result.get("brief_summary"):
                        auphonic_meta["brief_summary"] = result["brief_summary"]
                    if result.get("long_summary"):
                        auphonic_meta["long_summary"] = result["long_summary"]
                    
                    # NEW: AI-extracted tags
                    if result.get("tags"):
                        auphonic_meta["tags"] = result["tags"]
                    
                    # Chapters
                    if result.get("chapters"):
                        auphonic_meta["chapters"] = result["chapters"]
                    
                    # Production UUID for tracking
                    if result.get("production_uuid"):
                        auphonic_meta["production_uuid"] = result["production_uuid"]
                    
                    if auphonic_meta:
                        media_item.auphonic_metadata = json.dumps(auphonic_meta)
                    
                    session.add(media_item)
                    session.commit()
                    logging.info(f"[transcription] Updated MediaItem {media_item.id} with Auphonic outputs")
                else:
                    logging.warning(f"[transcription] Could not find MediaItem for filename={filename}")
                
                # Notify watchers and return transcript
                notify_watchers_processed(filename)
                return result["transcript"]
            
            elif user:
                # Free/Creator/Unlimited → AssemblyAI (existing logic below)
                logging.info(f"[transcription] user_id={user_id} tier={getattr(user, 'tier', 'unknown')} → AssemblyAI")
            else:
                logging.warning(f"[transcription] user_id={user_id} not found, using AssemblyAI")
        
        except Exception as e:
            logging.error(f"[transcription] ❌ TIER_ROUTING_FAILED user_id={user_id} error_type={type(e).__name__} error={e}", exc_info=True)
            # Fall through to AssemblyAI on error
            logging.warning(f"[transcription] ⚠️ Falling back to AssemblyAI after routing error")
    else:
        logging.info(f"[transcription] No user_id provided, using AssemblyAI (legacy behavior)")
    
    # Legacy behavior: Use AssemblyAI (Free/Creator/Unlimited tiers or no user_id)
    # Global safeguard: allow disabling brand-new transcription at runtime.
    raw_toggle = os.getenv("ALLOW_TRANSCRIPTION") or os.getenv("TRANSCRIBE_ENABLED")

    # First, if we already have a transcript JSON, reuse it and return early.
    existing = _read_existing_transcript_for(filename)
    if existing is not None:
        logging.info("[transcription] Reusing existing transcript for %s", filename)
        notify_watchers_processed(filename)
        return existing

    local_name = filename
    delete_after = False
    try:
        if _is_gcs_path(filename):
            try:
                local_name = _download_gcs_to_media(filename)
                delete_after = True
            except Exception as exc:  # pragma: no cover - network dependent
                logging.error("[transcription] GCS download failed for %s: %s", filename, exc)
                raise

        # Respect global kill-switch if set to falsey values.
        if raw_toggle and str(raw_toggle).strip().lower() in {"0", "false", "no", "off"}:
            raise TranscriptionError("Transcription disabled by environment")

        words = get_word_timestamps(local_name)
        try:
            TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
            stem = Path(local_name).stem
            payload = json.dumps(words, ensure_ascii=False, indent=2)

            safe_stem = sanitize_filename(stem) or stem or f"transcript-{uuid.uuid4().hex}"
            out_path = TRANSCRIPTS_DIR / f"{stem}.json"
            # Always persist locally (overwrite with freshest)
            out_path.write_text(payload, encoding="utf-8")

            # Upload permanently to GCS in a deterministic location: transcripts/{safe_stem}.json
            gcs_url = None
            gcs_uri = None
            bucket = None
            key = None
            try:
                bucket = _resolve_transcripts_bucket()
                from ...infrastructure.gcs import upload_bytes  # type: ignore

                key = f"transcripts/{safe_stem}.json"
                gcs_uri = upload_bytes(
                    bucket,
                    key,
                    payload.encode("utf-8"),
                    content_type="application/json; charset=utf-8",
                )
                if gcs_uri and gcs_uri.startswith("gs://"):
                    gcs_url = f"https://storage.googleapis.com/{bucket}/{key}"
                else:
                    gcs_uri = None
            except Exception as upload_exc:
                # CRITICAL FIX: Don't fail transcription if GCS upload fails
                # Local transcript is already saved, and recovery logic can retry GCS upload later
                logging.error(
                    "[transcription] ⚠️ Failed to upload transcript to GCS (will use local copy): %s",
                    upload_exc,
                    exc_info=True,
                )
                # Don't raise - allow transcription to complete with local transcript

            try:
                _store_media_transcript_metadata(
                    filename,
                    stem=stem,
                    safe_stem=safe_stem,
                    bucket=bucket,
                    key=key,
                    gcs_uri=gcs_uri,
                    gcs_url=gcs_url,
                )
            except Exception:
                logging.warning(
                    "[transcription] Failed to record media transcript metadata for %s", filename, exc_info=True
                )

            # Record the GCS key on the episode for deterministic reuse during assembly
            try:
                from api.services.episodes.repo import get_episode_by_id, update_episode
                from uuid import UUID
                episode_id = None
                try:
                    episode_id = UUID(stem)
                except Exception:
                    pass
                if episode_id:
                    from api.core.database import get_session
                    session_gen = get_session()
                    session = next(session_gen)
                    ep = get_episode_by_id(session, episode_id)
                    if ep:
                        meta = json.loads(ep.meta_json or "{}")
                        transcripts = dict(meta.get("transcripts", {}))
                        transcripts["stem"] = stem
                        transcripts["bucket_stem"] = safe_stem
                        if gcs_uri:
                            transcripts["gcs_json"] = gcs_uri
                            transcripts["gcs_url"] = gcs_url or transcripts.get("gcs_url")
                            transcripts["gcs_key"] = key
                            transcripts["gcs_bucket"] = bucket
                        elif gcs_url:
                            transcripts["gcs_url"] = gcs_url
                        meta["transcripts"] = transcripts
                        ep.meta_json = json.dumps(meta)
                        update_episode(session, ep, {"meta_json": ep.meta_json})
            except Exception as e:
                logging.warning(f"Failed to associate transcript with episode: {e}")
        except Exception:  # pragma: no cover - best effort persistence
            pass

        # CRITICAL: Mark MediaItem as transcript_ready BEFORE notifying watchers
        # This ensures files become available for assembly even without watchers
        try:
            from api.core.database import get_session
            from api.models.podcast import MediaItem
            from sqlmodel import select
            
            session = next(get_session())
            media_item = session.exec(
                select(MediaItem).where(MediaItem.filename == filename)
            ).first()
            
            if media_item:
                # Mark as transcript_ready regardless of content (even empty/instrumental)
                # This allows users to proceed with assembly and see what was transcribed
                media_item.transcript_ready = True
                
                session.add(media_item)
                session.commit()
                
                if not words or len(words) == 0:
                    logging.warning("[transcription] ⚠️ Empty transcript (instrumental/no speech) for %s", filename)
                else:
                    logging.info("[transcription] ✅ Marked MediaItem %s as transcript_ready (words=%d)", 
                                 media_item.id, len(words))
            else:
                logging.warning("[transcription] ⚠️ Could not find MediaItem for filename=%s", filename)
        except Exception as mark_err:
            logging.error("[transcription] ❌ Failed to mark MediaItem as ready: %s", mark_err, exc_info=True)
            # Don't fail the entire transcription if this fails

        notify_watchers_processed(filename)
        return words
    except Exception as exc:
        mark_watchers_failed(filename, str(exc))
        try:
            from api.core import database as db
            from api.models.podcast import MediaItem
            from sqlmodel import Session, select

            with Session(db.engine) as session:
                item = session.exec(
                    select(MediaItem).where(MediaItem.filename == filename)
                ).first()
                if item:
                    session.delete(item)
                    session.commit()
        except Exception:
            logging.warning(
                "[transcription] Failed to roll back media item after transcription error",
                exc_info=True,
            )
        try:
            (MEDIA_DIR / filename).unlink(missing_ok=True)
        except Exception:
            pass
        raise
    finally:
        if delete_after:
            try:
                (MEDIA_DIR / local_name).unlink(missing_ok=True)
            except Exception:
                pass


# Re-export frequently used helper modules for compatibility with legacy imports
from . import assemblyai_client  # noqa: E402  # isort: skip
from . import transcription_runner  # noqa: E402  # isort: skip


__all__ = [
    "TranscriptionError",
    "get_word_timestamps",
    "transcribe_media_file",
    "load_media_transcript_metadata_for_filename",
    "assemblyai_client",
    "transcription_runner",
]

