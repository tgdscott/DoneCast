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
from .speaker_identification import prepend_speaker_intros, map_speaker_labels



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
        logging.info("[transcription/pkg] Using AssemblyAI with disfluencies=False (removes filler words)")
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


def _is_gcs_url(path: str) -> bool:
    """Check if path is a GCS URL.
    
    Note: Intermediate files (uploads) always go to GCS, not R2.
    R2 is only for final files (assembled episodes).
    """
    if not isinstance(path, str):
        return False
    return path.startswith("gs://")


def _download_gcs_to_media(gcs_uri: str) -> str:
    """Download from GCS to MEDIA_DIR and return the local filename.
    
    Supports:
    - GCS: gs://bucket/key
    
    Note: Intermediate files (uploads) are always in GCS, so we only need to handle GCS URLs.
    """
    logging.info("[transcription] Downloading from GCS: %s", gcs_uri)
    
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Expected GCS URL (gs://...), got: {gcs_uri}")
    
    # Extract bucket and key from GCS URL
    without_scheme = gcs_uri[len("gs://"):]
    parts = without_scheme.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid GCS URI format: {gcs_uri}")
    
    bucket_name, key = parts
    
    # Download from GCS directly (bypass storage abstraction to ensure GCS)
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(key)
        
        # Download to MEDIA_DIR
        dst_name = os.path.basename(key) or "audio"
        dst_path = MEDIA_DIR / dst_name
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(dst_path))
        
        file_size = dst_path.stat().st_size
        logging.info("[transcription] Downloaded %d bytes from GCS to %s", file_size, dst_path)
        return dst_name
    except Exception as e:
        logging.error("[transcription] Failed to download from GCS %s: %s", gcs_uri, e, exc_info=True)
        raise FileNotFoundError(f"Failed to download from GCS: {gcs_uri}") from e


def _store_media_transcript_metadata(
    filename: str,
    *,
    stem: Optional[str] = None,
    safe_stem: Optional[str] = None,
    bucket: Optional[str] = None,
    key: Optional[str] = None,
    gcs_uri: Optional[str] = None,
    gcs_url: Optional[str] = None,
    words: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Persist transcript metadata for a media upload for future reuse."""

    logger = logging.getLogger("transcription")
    
    cleaned = (filename or "").strip()
    if not cleaned:
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
    # If words provided explicitly, include them in the payload so DB-only retrieval is possible
    if words and isinstance(words, list) and len(words) > 0:
        payload.setdefault("words", words)
    
    if not payload:
        return

    try:
        from sqlmodel import Session, select

        from api.core import database as db
        from api.models.podcast import MediaItem
        from api.models.transcription import MediaTranscript
    except Exception as import_exc:
        logger.error(
            "[transcript_save] Import failed: %s", import_exc, exc_info=True
        )
        return

    candidates = _candidate_filenames(cleaned)
    if cleaned not in candidates:
        candidates.insert(0, cleaned)
    
    logger.info(
        "🔍 [transcript_save_candidates] filename='%s', candidates=%s",
        cleaned, candidates[:5]  # Show first 5 to avoid log spam
    )

    try:
        with Session(db.engine) as session:
            media_item = session.exec(
                select(MediaItem).where(MediaItem.filename.in_(candidates))
            ).first()
            media_item_id = getattr(media_item, "id", None) if media_item else None

            existing = session.exec(
                select(MediaTranscript).where(MediaTranscript.filename.in_(candidates))
            ).all()

            target = None
            for record in existing:
                if str(record.filename).strip() == cleaned:
                    target = record
                    break
            if target is None and existing:
                target = existing[0]

            # CRITICAL FIX: Store transcript words directly in metadata JSON for database-only retrieval
            # This ensures transcripts can be retrieved even if GCS is unavailable
            if "words" not in payload:
                # If words are not in payload, try to load from the transcript file that was just created
                # This happens when transcribe_media_file() calls this function after generating transcript
                try:
                    from pathlib import Path as PathLib
                    stem = PathLib(cleaned).stem if stem is None else stem
                    # Try to find the transcript JSON file that was just saved
                    transcript_candidates = [
                        TRANSCRIPTS_DIR / f"{stem}.json",
                        TRANSCRIPTS_DIR / f"{PathLib(cleaned).stem}.json",
                    ]
                    for candidate in transcript_candidates:
                        if candidate.exists():
                            with open(candidate, "r", encoding="utf-8") as fh:
                                words_data = json.load(fh)
                                if isinstance(words_data, list) and len(words_data) > 0:
                                    payload["words"] = words_data
                                    logger.info("[transcript_save] ✅ Loaded %d words from transcript file into metadata", len(words_data))
                                    break
                except Exception as words_load_err:
                    logger.debug("[transcript_save] Could not load words into metadata (non-critical): %s", words_load_err)
            
            serialized = json.dumps(payload)
            now = datetime.utcnow()

            if target is not None:
                target.filename = cleaned
                target.transcript_meta_json = serialized
                target.updated_at = now
                # CRITICAL FIX: Always update media_item_id if we found a MediaItem
                # This ensures the association is maintained even if transcript was created before MediaItem existed
                if media_item_id:
                    target.media_item_id = media_item_id
                session.add(target)
            else:
                new_record = MediaTranscript(
                    media_item_id=media_item_id,
                    filename=cleaned,
                    transcript_meta_json=serialized,
                    created_at=now,
                    updated_at=now,
                )
                session.add(new_record)

            session.commit()
            logger.info("[transcript_save] SUCCESS: Saved transcript metadata for '%s'", cleaned)
    except Exception as db_exc:
        logger.error(
            "[transcript_save] DATABASE ERROR for '%s': %s", 
            cleaned, 
            db_exc, 
            exc_info=True
        )
        # CRITICAL: Re-raise exception so caller knows metadata save failed
        raise


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


def transcribe_media_file(filename: str, user_id: Optional[str] = None, guest_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Synchronously transcribe a media file and persist transcript artifacts.
    
    Routes to appropriate transcription service based on MediaItem.use_auphonic flag:
    - use_auphonic=True → Auphonic (transcription + audio processing)
    - use_auphonic=False/None → AssemblyAI (transcription only)
    
    CRITICAL: Only ONE service runs. No fallbacks. Failures fail loudly.
    
    Args:
        filename: GCS URL or local path to audio file
        user_id: UUID string of user (required for MediaItem lookup)
        guest_ids: Optional list of guest library IDs for speaker identification (AssemblyAI only)
        
    Returns:
        List of word dicts with start/end/word/speaker keys
        
    Raises:
        TranscriptionError: If transcription fails (no fallback)
    """

    # DEBUG: Log what we received
    logging.info(f"[transcription] 🎬 CALLED with filename={filename}, user_id={user_id!r}, guest_ids={guest_ids}")
    
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

    # Helper function to charge credits after successful transcription
    def _charge_for_successful_transcription(user_obj, audio_file_path, use_auphonic_flag):
        """Charge credits only after transcription succeeds."""
        try:
            from api.core.database import get_session
            from api.services.billing import credits
            from pydub import AudioSegment
            
            session = next(get_session())
            
            # Get audio duration
            try:
                if not audio_file_path.exists():
                    raise FileNotFoundError(f"Audio file not found: {audio_file_path}")
                
                audio = AudioSegment.from_file(str(audio_file_path))
                # charge_for_transcription expects SECONDS, not minutes!
                duration_seconds = len(audio) / 1000.0  # pydub length is in milliseconds
                
                logging.info(
                    "[transcription] 💳 Charging credits: user=%s, duration=%.2f seconds (%.2f min), auphonic=%s",
                    user_obj.id,
                    duration_seconds,
                    duration_seconds / 60.0,
                    use_auphonic_flag
                )
                
                ledger_entry, cost_breakdown = credits.charge_for_transcription(
                    session=session,
                    user=user_obj,
                    duration_seconds=duration_seconds,
                    use_auphonic=use_auphonic_flag,
                    episode_id=None,  # Transcription happens before episode is created
                    correlation_id=f"transcription_{filename}_{uuid.uuid4().hex[:8]}",
                )
                
                logging.info(
                    "[transcription] ✅ Credits charged: %.2f credits (duration=%.2fs, rate=%.2f credits/sec, auphonic=%s)",
                    cost_breakdown['total_credits'],
                    cost_breakdown['duration_seconds'],
                    cost_breakdown['processing_rate_per_sec'],
                    use_auphonic_flag
                )
                
            except Exception as audio_err:
                logging.warning("[transcription] ⚠️ Could not determine audio duration for billing: %s", audio_err)
                # Don't fail transcription if billing fails
                
        except Exception as credits_err:
            logging.error("[transcription] ⚠️ Failed to charge credits (non-fatal): %s", credits_err, exc_info=True)
            # Don't fail transcription if credit charging fails

    # CRITICAL: Look up MediaItem to check use_auphonic flag (sole source of truth)
    if not user_id:
        raise TranscriptionError(
            f"user_id is required for transcription routing. Cannot determine which service to use for {filename}"
        )
    
    try:
        from api.core.database import get_session
        from api.models.podcast import MediaItem
        from api.models.user import User
        from sqlmodel import select

        session = next(get_session())
        logging.info(f"[transcription] 🔍 Looking up MediaItem for filename={filename}, user_id={user_id}")
        
        # CRITICAL FIX: Match EXACT filename, not basename
        # The filename in MediaItem is the full GCS URL: gs://bucket/user_id/media_uploads/file.mp3
        # We must match it exactly, not use .contains() which is unreliable
        media_item = session.exec(
            select(MediaItem)
            .where(MediaItem.user_id == user_id)
            .where(MediaItem.filename == filename)  # Exact match
            .order_by(MediaItem.created_at.desc())
        ).first()
        
        if not media_item:
            raise TranscriptionError(
                f"MediaItem not found for filename={filename}. "
                f"Cannot determine transcription service. MediaItem must exist before transcription."
            )


        
        # Get user for charging credits
        user = session.exec(select(User).where(User.id == user_id)).first()
        if not user:
            raise TranscriptionError(f"User not found: user_id={user_id}")
        
        # CRITICAL: Check MediaItem.use_auphonic flag (sole source of truth)
        # This flag is set when the file is uploaded based on the checkbox
        use_auphonic = getattr(media_item, "use_auphonic", False)
        logging.info(
            f"[transcription] MediaItem {media_item.id} → use_auphonic={use_auphonic} "
            f"(filename={filename})"
        )
        
        if use_auphonic:
            # Auphonic path - NO FALLBACKS
            logging.info(f"[transcription] 🎯 ROUTING TO Auphonic (MediaItem.use_auphonic=True)")
            
            from api.services.transcription_auphonic import auphonic_transcribe_and_process
            
            try:
                result = auphonic_transcribe_and_process(filename, str(user_id))
            except Exception as auphonic_err:
                # FAIL LOUDLY - no fallback to AssemblyAI
                error_msg = (
                    f"Auphonic transcription FAILED for {filename}. "
                    f"MediaItem.use_auphonic=True but Auphonic processing failed. "
                    f"Error: {auphonic_err}"
                )
                logging.error(f"[transcription] ❌ {error_msg}", exc_info=True)
                raise TranscriptionError(error_msg) from auphonic_err
            
            # Update MediaItem with Auphonic outputs
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
            
            # CRITICAL FIX: Store transcript metadata in MediaTranscript table
            # This ensures transcripts are findable during assembly regardless of device/environment
            try:
                transcript_words = result.get("transcript", [])
                if transcript_words:
                    # Extract GCS URL from Auphonic result (transcript was uploaded to GCS)
                    # Format: gs://bucket/transcripts/{user_id}/{stem}.json
                    from pathlib import Path as PathLib
                    stem = PathLib(filename).stem
                    safe_stem = sanitize_filename(stem) or stem
                    gcs_bucket = os.getenv("TRANSCRIPTS_BUCKET") or os.getenv("MEDIA_BUCKET") or ""
                    gcs_key = f"transcripts/{user_id}/{stem}.json"
                    gcs_uri = f"gs://{gcs_bucket}/{gcs_key}" if gcs_bucket else None
                    
                    # Store metadata with words included
                    _store_media_transcript_metadata(
                        filename,  # Use original filename (GCS URI or local path)
                        stem=stem,
                        safe_stem=safe_stem,
                        bucket=gcs_bucket if gcs_bucket else None,
                        key=gcs_key if gcs_bucket else None,
                        gcs_uri=gcs_uri,
                        gcs_url=None,
                        words=transcript_words,
                    )
                    
                    # Update MediaTranscript with words if not already included
                    try:
                        from api.services.transcription.watchers import _candidate_filenames
                        candidates = _candidate_filenames(filename)
                        if filename not in candidates:
                            candidates.insert(0, filename)
                        
                        transcript_record = session.exec(
                            select(MediaTranscript).where(MediaTranscript.filename.in_(candidates))
                        ).first()
                        
                        if transcript_record:
                            meta = json.loads(transcript_record.transcript_meta_json or "{}")
                            if "words" not in meta or not meta.get("words"):
                                meta["words"] = transcript_words
                                transcript_record.transcript_meta_json = json.dumps(meta)
                                if media_item:
                                    transcript_record.media_item_id = media_item.id
                                session.add(transcript_record)
                                session.commit()
                                logging.info("[transcription] ✅ Updated MediaTranscript with %d words from Auphonic", len(transcript_words))
                    except Exception as words_update_err:
                        logging.warning("[transcription] Failed to update MediaTranscript with words (non-critical): %s", words_update_err)
            except Exception as metadata_err:
                logging.error("[transcription] ❌ Failed to store Auphonic transcript metadata: %s", metadata_err, exc_info=True)
                # Don't fail transcription if metadata save fails, but log it loudly
            
            # ========== CHARGE CREDITS FOR TRANSCRIPTION (AFTER SUCCESS) ==========
            # Only charge if transcription succeeded - failures are on us
            try:
                # Get audio file path for duration calculation
                if _is_gcs_url(filename):
                    local_filename = _download_gcs_to_media(filename)
                    audio_path = MEDIA_DIR / local_filename
                else:
                    audio_path = MEDIA_DIR / filename
                
                _charge_for_successful_transcription(user, audio_path, use_auphonic=True)
            except Exception as charge_err:
                logging.warning("[transcription] ⚠️ Failed to charge after success (non-fatal): %s", charge_err)
            # ========== END CREDIT CHARGING ==========
            
            # Notify watchers and return transcript
            notify_watchers_processed(filename)
            return result["transcript"]
        
        else:
            # AssemblyAI path - NO FALLBACKS
            logging.info(f"[transcription] 🎯 ROUTING TO AssemblyAI (MediaItem.use_auphonic=False/None)")
        
    except TranscriptionError:
        # Re-raise TranscriptionError as-is (no fallback)
        raise
    except Exception as e:
        # FAIL LOUDLY - no fallback
        error_msg = (
            f"Transcription routing FAILED for {filename}. "
            f"Error: {e}"
        )
        logging.error(f"[transcription] ❌ {error_msg}", exc_info=True)
        raise TranscriptionError(error_msg) from e
    
    # AssemblyAI transcription path (MediaItem.use_auphonic=False/None)
    # Global safeguard: allow disabling transcription at runtime.
    raw_toggle = os.getenv("ALLOW_TRANSCRIPTION") or os.getenv("TRANSCRIBE_ENABLED")

    # First, if we already have a transcript JSON, reuse it and return early.
    existing = _read_existing_transcript_for(filename)
    if existing is not None:
        logging.info("[transcription] Reusing existing transcript for %s", filename)
        notify_watchers_processed(filename)
        return existing

    local_name = filename
    delete_after = False
    
    # Speaker identification vars
    intro_duration_s = 0.0
    podcast_context_id = None
    episode_guest_intros = []
    podcast_speaker_intros = None
    
    try:
        if _is_gcs_url(filename):
            try:
                local_name = _download_gcs_to_media(filename)
                delete_after = True
                logging.info("[transcription] Downloaded GCS file to local: %s -> %s", filename, local_name)
            except Exception as exc:  # pragma: no cover - network dependent
                logging.error("[transcription] GCS download failed for %s: %s", filename, exc, exc_info=True)
                raise

        # Respect global kill-switch if set to falsey values.
        if raw_toggle and str(raw_toggle).strip().lower() in {"0", "false", "no", "off"}:
            raise TranscriptionError("Transcription disabled by environment")

        # =====================================================================
        # SPEAKER IDENTIFICATION: Prepend intros if guest_ids provided
        # =====================================================================
        if guest_ids and user_id:
            try:
                from api.core.database import get_session
                from api.models.podcast import Podcast
                from sqlmodel import select
                
                # Use existing session if possible, else create new
                # (Assuming one session per task execution is fine)
                session = next(get_session())
                
                # Find user's podcasts to locate guests
                user_podcasts = session.exec(select(Podcast).where(Podcast.user_id == user_id)).all()
                
                found_guests = []
                target_podcast = None
                
                for pod in user_podcasts:
                    lib = pod.guest_library or []
                    # lib is list of dicts: {id, name, gcs_path, ...}
                    matches = [g for g in lib if g.get("id") in guest_ids]
                    if matches:
                        found_guests.extend(matches)
                        if not target_podcast:
                            target_podcast = pod
                
                if found_guests:
                    episode_guest_intros = found_guests
                    logging.info("[transcription] Found %d guests in library for speaker ID", len(found_guests))
                    
                    if target_podcast:
                        podcast_context_id = target_podcast.id
                        podcast_speaker_intros = target_podcast.speaker_intros
                        logging.info("[transcription] Using host intros from podcast %s", target_podcast.title)
                    
                    # Prepend intros to local audio file
                    # Note: local_name is just a filename in MEDIA_DIR, we need full path
                    local_path = MEDIA_DIR / local_name
                    if local_path.exists():
                        prepended_path, duration = prepend_speaker_intros(
                            main_audio_path=local_path,
                            podcast_speaker_intros=podcast_speaker_intros,
                            episode_guest_intros=episode_guest_intros
                        )
                        
                        if duration > 0:
                            intro_duration_s = duration
                            # Use the prepended file for transcription
                            # It returns a Path object, get name relative to MEDIA_DIR if needed
                            # But get_word_timestamps expects filename in MEDIA_DIR
                            # prepend_speaker_intros saves to MEDIA_DIR, so just get name
                            local_name = prepended_path.name
                            # Don't delete this temp file immediately, wait for cleanup
                            delete_after = True # It's a temp file
                            logging.info(
                                "[transcription] 🎙️ Prepended speaker intros (duration: %.2fs) -> %s",
                                intro_duration_s,
                                local_name
                            )
            except Exception as speaker_err:
                logging.error("[transcription] Failed to setup speaker identification: %s", speaker_err, exc_info=True)
                # Continue without speaker ID
        # =====================================================================

        words = get_word_timestamps(local_name)
        
        # =====================================================================
        # SPEAKER IDENTIFICATION: Map labels and shift timestamps
        # =====================================================================
        if intro_duration_s > 0:
            try:
                logging.info("[transcription] Post-processing transcript with intros (duration: %.2fs)", intro_duration_s)
                words = map_speaker_labels(
                    words=words,
                    podcast_id=podcast_context_id,
                    episode_id=None, # No episode yet
                    speaker_intros=podcast_speaker_intros,
                    guest_intros=episode_guest_intros,
                    intro_duration_s=intro_duration_s
                )
            except Exception as map_err:
                logging.error("[transcription] Failed to map speakers/strip intros: %s", map_err, exc_info=True)
        # =====================================================================

        # DIAGNOSTIC: Confirm AssemblyAI returned data
        logging.info("🟢 [STEP_2_COMPLETE] Got %d words from AssemblyAI for filename='%s'", len(words), filename)
        
        # CRITICAL: Store the ORIGINAL filename (GCS URI or local path) for database lookup
        # Bug: We were using local_name (downloaded filename) which breaks GCS URI lookups
        original_filename = filename
        
        try:
            logging.info("🟡 [STEP_4_START] Creating TRANSCRIPTS_DIR and preparing payload")
            TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
            stem = Path(local_name).stem
            payload = json.dumps(words, ensure_ascii=False, indent=2)
            
            # DIAGNOSTIC: Confirm we built the payload
            logging.info("🟢 [STEP_5_COMPLETE] Built JSON payload - stem='%s', payload_size=%d bytes", stem, len(payload))

            safe_stem = sanitize_filename(stem) or stem or f"transcript-{uuid.uuid4().hex}"
            out_path = TRANSCRIPTS_DIR / f"{stem}.json"
            # Always persist locally (overwrite with freshest)
            out_path.write_text(payload, encoding="utf-8")
            
            # DIAGNOSTIC: Confirm local save worked
            logging.info("🟢 [STEP_7_COMPLETE] Saved transcript locally to '%s'", out_path)

            # Upload permanently to cloud storage in a deterministic location: transcripts/{safe_stem}.json
            logging.info("🟡 [STEP_8_START] Preparing cloud storage upload - safe_stem='%s'", safe_stem)
            gcs_url = None
            gcs_uri = None
            bucket = None
            key = None
            # Use a resilient upload helper that will attempt the configured storage helper
            # and fall back to direct google.cloud.storage upload with retries.
            def _upload_transcript_to_gcs(bucket_name: str, key_name: str, data_bytes: bytes) -> Optional[str]:
                """Attempt to upload bytes to the configured storage.

                Returns a GCS URI string (gs://bucket/key) on success, or None on failure.
                """
                # First, try the existing storage abstraction if available
                try:
                    from infrastructure import storage  # type: ignore
                    storage_url = storage.upload_bytes(
                        bucket_name,
                        key_name,
                        data_bytes,
                        content_type="application/json; charset=utf-8",
                    )
                    if storage_url:
                        if storage_url.startswith("gs://"):
                            return storage_url
                        # If storage abstraction returned non-gs URL, still try the direct client
                except Exception as primary_exc:
                    logging.warning("[transcription] storage.upload_bytes failed: %s", primary_exc, exc_info=True)

                # Fallback: use google.cloud.storage directly with small retries
                try:
                    from google.cloud import storage as gcs_storage
                    client = gcs_storage.Client()
                    bucket = client.bucket(bucket_name)
                    blob = bucket.blob(key_name)

                    # Try upload with retries
                    attempts = 3
                    for attempt in range(1, attempts + 1):
                        try:
                            blob.upload_from_string(data_bytes, content_type="application/json; charset=utf-8")
                            return f"gs://{bucket_name}/{key_name}"
                        except Exception as e:
                            logging.warning("[transcription] Direct GCS upload attempt %d failed: %s", attempt, e)
                            if attempt == attempts:
                                raise
                except Exception as gcs_exc:
                    logging.error("[transcription] Direct GCS upload failed: %s", gcs_exc, exc_info=True)
                    return None

            try:
                bucket = _resolve_transcripts_bucket()
                key = f"transcripts/{safe_stem}.json"
                uploaded = _upload_transcript_to_gcs(bucket, key, payload.encode("utf-8"))
                if uploaded:
                    gcs_uri = uploaded
                    gcs_url = f"https://storage.googleapis.com/{bucket}/{key}"
                else:
                    gcs_uri = None
                    gcs_url = None

                logging.info("🟢 [STEP_9_COMPLETE] Cloud storage upload result - gcs_uri='%s', gcs_url='%s'", gcs_uri, gcs_url)
            except Exception as upload_exc:
                logging.error(
                    "[transcription] ⚠️ Failed to upload transcript to cloud storage after retries: %s",
                    upload_exc,
                    exc_info=True,
                )
                logging.warning("🔴 [STEP_9_FAILED] Cloud storage upload FAILED - continuing with local copy and DB metadata save")

            # CRITICAL FIX: Use original_filename (GCS URI) not local_name (downloaded file)
            # This ensures database lookups match the filename stored in MediaItem
            # ALSO: Store transcript words directly in metadata for database-only retrieval
            logging.info(
                "🔵 [transcript_metadata_save_attempt] BEFORE save - original_filename='%s', stem='%s', gcs_uri='%s', words_count=%d",
                original_filename, stem, gcs_uri, len(words)
            )
            try:
                # CRITICAL: Include words in metadata payload for database-only retrieval
                # This ensures transcripts can be found even if GCS is unavailable
                # Ensure we persist words into DB metadata too (so transcripts are findable even if GCS later disappears)
                _store_media_transcript_metadata(
                    original_filename,  # ← FIX: Was 'filename' before, use original GCS URI
                    stem=stem,
                    safe_stem=safe_stem,
                    bucket=bucket,
                    key=key,
                    gcs_uri=gcs_uri,
                    gcs_url=gcs_url,
                    words=words,
                )
                # After saving metadata, update it with words if not already included
                try:
                    from api.core.database import get_session
                    from api.models.transcription import MediaTranscript
                    from sqlmodel import select
                    from api.services.transcription.watchers import _candidate_filenames
                    
                    session = next(get_session())
                    candidates = _candidate_filenames(original_filename)
                    if original_filename not in candidates:
                        candidates.insert(0, original_filename)
                    
                    transcript_record = session.exec(
                        select(MediaTranscript).where(MediaTranscript.filename.in_(candidates))
                    ).first()
                    
                    if transcript_record:
                        meta = json.loads(transcript_record.transcript_meta_json or "{}")
                        if "words" not in meta or not meta.get("words"):
                            meta["words"] = words
                            transcript_record.transcript_meta_json = json.dumps(meta)
                            session.add(transcript_record)
                            session.commit()
                            logging.info("[transcription] ✅ Updated MediaTranscript with %d words in metadata", len(words))
                except Exception as words_update_err:
                    logging.warning("[transcription] Failed to update transcript metadata with words (non-critical): %s", words_update_err)
                logging.info(
                    "✅ [transcript_metadata_save_attempt] AFTER save SUCCESS - original_filename='%s'",
                    original_filename
                )
            except Exception as metadata_exc:
                # LOUD FAILURE: This is CRITICAL - transcript is useless if metadata isn't saved
                logging.error(
                    "[transcription] 🚨 CRITICAL: Failed to save transcript metadata for %s: %s", 
                    original_filename, 
                    metadata_exc, 
                    exc_info=True
                )
                
                # Send Slack alert for critical failure
                try:
                    import os as _os
                    import httpx
                    slack_webhook = _os.getenv("SLACK_OPS_WEBHOOK_URL", "").strip()
                    if slack_webhook:
                        payload = {
                            "text": f"🚨 *CRITICAL: Transcript Metadata Save Failed*\n"
                                    f"Failed to save transcript metadata to database\n"
                                    f"*File:* `{original_filename}`\n"
                                    f"*Error:* {str(metadata_exc)[:500]}\n"
                                    f"*Impact:* Episode assembly will fail - transcript not findable\n"
                                    f"*Action:* Check database connectivity and MediaTranscript table"
                        }
                        httpx.post(slack_webhook, json=payload, timeout=5.0)
                        logging.info("[transcription] Slack alert sent for metadata save failure")
                except Exception as alert_exc:
                    logging.error("[transcription] Failed to send Slack alert: %s", alert_exc)
                
                # Don't suppress this error - it's critical
                raise TranscriptionError(
                    f"Critical: Transcript generated but metadata save failed for {original_filename}: {metadata_exc}"
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
        except TranscriptionError:
            # Re-raise critical errors (like metadata save failures) - don't suppress them
            raise
        except Exception as persistence_exc:
            # Log non-critical persistence failures but don't fail the entire transcription
            logging.error(
                "[transcription] ⚠️ Non-critical persistence error (continuing): %s",
                persistence_exc,
                exc_info=True
            )

        # CRITICAL: Mark MediaItem as transcript_ready ONLY if transcript persisted
        # We consider persistence successful when either:
        # - A GCS URI/url exists for the transcript (gcs_uri/gcs_url), OR
        # - A MediaTranscript record exists and contains "words" in its metadata
        try:
            from api.core.database import get_session
            from api.models.podcast import MediaItem
            from api.models.transcription import MediaTranscript
            from sqlmodel import select

            session = next(get_session())

            # Determine whether transcript metadata contains words
            transcript_has_words = False
            try:
                candidates = _candidate_filenames(original_filename)
                if original_filename not in candidates:
                    candidates.insert(0, original_filename)
                record = session.exec(
                    select(MediaTranscript).where(MediaTranscript.filename.in_(candidates))
                ).first()
                if record:
                    try:
                        meta = json.loads(record.transcript_meta_json or "{}")
                        if isinstance(meta.get("words"), list) and len(meta.get("words")) > 0:
                            transcript_has_words = True
                    except Exception:
                        transcript_has_words = False
            except Exception:
                # Non-fatal - we'll rely on gcs_uri/gcs_url if DB check fails
                transcript_has_words = False

            can_mark_ready = bool(gcs_uri or gcs_url or transcript_has_words)

            # CRITICAL FIX: Use original_filename (GCS URL) not local filename
            # When GCS files are downloaded for transcription, `filename` becomes the local name
            # But MediaItem.filename stores the GCS URL, so we must use original_filename
            media_item = session.exec(
                select(MediaItem).where(MediaItem.filename == original_filename)
            ).first()

            if media_item:
                if can_mark_ready:
                    media_item.transcript_ready = True
                    # CRITICAL FIX: Store GCS transcript location in MediaItem so worker can find it
                    # Worker looks for this during assembly when episode.meta_json doesn't have it
                    transcript_meta = {
                        "gcs_uri": gcs_uri,
                        "gcs_url": gcs_url,
                        "bucket": bucket,
                        "key": key,
                        "stem": stem,
                        "safe_stem": safe_stem,
                    }
                    media_item.transcript_meta_json = json.dumps(transcript_meta)
                    session.add(media_item)
                    session.commit()

                    if transcript_has_words:
                        logging.info("[transcription] ✅ Marked MediaItem %s as transcript_ready (words=%d, gcs_uri=%s)", media_item.id, len(words), gcs_uri)
                    else:
                        logging.info("[transcription] ✅ Marked MediaItem %s as transcript_ready (gcs present: %s)", media_item.id, gcs_uri)
                else:
                    # DO NOT mark as ready if we have no durable transcript
                    logging.warning(
                        "[transcription] ⚠️ Transcript NOT persisted for %s - not marking MediaItem %s as ready (gcs_uri=%s, gcs_url=%s, words_in_db=%s)",
                        filename,
                        media_item.id,
                        bool(gcs_uri),
                        bool(gcs_url),
                        transcript_has_words,
                    )
            else:
                logging.warning("[transcription] ⚠️ Could not find MediaItem for filename=%s", filename)
        except Exception as mark_err:
            logging.error("[transcription] ❌ Failed to determine/mark MediaItem transcript readiness: %s", mark_err, exc_info=True)
            # Don't fail the entire transcription if this fails

        # ========== CHARGE CREDITS FOR TRANSCRIPTION (AFTER SUCCESS) ==========
        # Only charge if transcription succeeded - failures are on us
        if user_id:
            try:
                from api.core.database import get_session
                from api.models.user import User
                from sqlmodel import select
                
                session = next(get_session())
                user = session.exec(select(User).where(User.id == user_id)).first()
                
                if user:
                    # Use local_name (the audio file that was transcribed)
                    # local_name could be a full path or just a filename
                    if Path(local_name).is_absolute():
                        audio_path = Path(local_name)
                    else:
                        audio_path = MEDIA_DIR / local_name
                    _charge_for_successful_transcription(user, audio_path, use_auphonic=False)
            except Exception as charge_err:
                logging.warning("[transcription] ⚠️ Failed to charge after success (non-fatal): %s", charge_err)
        # ========== END CREDIT CHARGING ==========

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

