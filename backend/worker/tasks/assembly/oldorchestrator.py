"""Final orchestration for episode assembly."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import List
from uuid import UUID

from sqlmodel import select

from api.core import crud
from api.core.database import session_scope
from api.models.notification import Notification
from api.models.podcast import MediaCategory, MediaItem, Episode, EpisodeStatus
from api.models.user import User
# Import the audio package and alias it to the expected name. The orchestrator
# calls audio_processor.process_and_assemble_episode(...), and api.services.audio
# re-exports process_and_assemble_episode from its __init__.py.
from api.services import audio as audio_processor
from api.services.mailer import mailer
from api.core.paths import WS_ROOT as PROJECT_ROOT, FINAL_DIR, MEDIA_DIR
from infrastructure import storage
from infrastructure.tasks_client import enqueue_http_task

# Optional transcription orchestration hook (may be provided by workers)
try:
    from backend.worker.tasks.assembly import transcribe_episode  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    transcribe_episode = None

from . import media, transcript
from .transcript import _commit_with_retry


ASSEMBLY_LOG_DIR = PROJECT_ROOT / "assembly_logs"
ASSEMBLY_LOG_DIR.mkdir(exist_ok=True)


async def run_proprietary_audio_analysis(main_content_filename: str) -> dict:
    """Simulate advanced audio analysis with placeholder metrics."""
    return {
        "integrated_lufs": -21.0,
        "signal_to_noise_ratio": 9.0,
        "dnsmos_score": 3.2,
    }


def classify_quality(metrics: dict) -> str:
    """Classify audio quality based on DNSMOS and SNR thresholds."""

    dnsmos = float(metrics.get("dnsmos_score", 0.0)) if metrics else 0.0
    snr = float(metrics.get("signal_to_noise_ratio", 0.0)) if metrics else 0.0

    if dnsmos < 2.5 or snr < 0:
        return "Extremely Bad"
    if dnsmos < 3.0 or snr < 5:
        return "Very Bad"
    if dnsmos < 3.5 or snr < 10:
        return "Fairly Bad"
    if dnsmos <= 4.0 or snr <= 15:
        return "Slightly Bad"
    return "Good"


async def _handle_audio_decision(*, session, episode: Episode | None, main_content_filename: str, user: User | None):
    """Evaluate audio quality and determine whether to pause for user input.

    Returns {"status": "paused"} when user needs to decide, otherwise
    {"status": "continue", "use_auphonic": bool}.
    """

    if episode is None:
        logging.warning("[assemble] Audio decision skipped: episode not found")
        return {"status": "continue", "use_auphonic": False}

    if user is None:
        logging.warning("[assemble] Audio decision skipped: user not found")
        return {"status": "continue", "use_auphonic": False}

    quality_metrics = await run_proprietary_audio_analysis(main_content_filename)
    severity_level = classify_quality(quality_metrics)

    raw_settings = getattr(user, "audio_gate_settings", {}) or {}
    settings = raw_settings
    if isinstance(raw_settings, str):
        try:
            settings = json.loads(raw_settings)
        except Exception:
            logging.warning("[assemble] Failed to parse audio_gate_settings JSON; defaulting to normal flow")
            settings = {}

    action = None
    if isinstance(settings, dict):
        action = settings.get(severity_level)

    normalized_action = str(action or "").strip().lower()

    if normalized_action in {"ask me", "ask_me", "ask", "pause", "prompt"}:
        try:
            meta = json.loads(episode.meta_json or "{}")
        except Exception:
            meta = {}

        aqg_meta = meta.get("audio_quality_gate") or {}
        aqg_meta.update({
            "severity_level": severity_level,
            "metrics": quality_metrics,
        })
        meta["audio_quality_gate"] = aqg_meta
        episode.meta_json = json.dumps(meta)

        try:
            episode.status = EpisodeStatus.awaiting_audio_decision  # type: ignore[attr-defined]
        except Exception:
            episode.status = "awaiting_audio_decision"  # type: ignore[assignment]

        session.add(episode)
        if not _commit_with_retry(session):
            raise RuntimeError("Failed to persist awaiting_audio_decision state")

        logging.info("[assemble] Episode %s paused for user decision: %s", episode.id, severity_level)
        return {"status": "paused", "episode_id": str(episode.id)}

    if normalized_action in {"advanced", "advanced processing", "advanced_processing"}:
        return {"status": "continue", "use_auphonic": True}

    # Default path: proceed with normal processing
    return {"status": "continue", "use_auphonic": False}


def _persist_stream_log(episode, log_data) -> None:
    if not isinstance(log_data, list):
        return

    try:
        max_entries = 800
        max_len = 4000
        trimmed: list[str] = []
        for entry in log_data[:max_entries]:
            if isinstance(entry, str) and len(entry) > max_len:
                trimmed.append(entry[:max_len] + "...(truncated)")
            else:
                trimmed.append(entry)
        log_path = ASSEMBLY_LOG_DIR / f"{episode.id}.log"
        with open(log_path, "w", encoding="utf-8") as fh:
            for line in trimmed:
                try:
                    fh.write(line.replace("\n", " ") + "\n")
                except Exception:
                    pass
    except Exception:
        logging.warning("[assemble] Failed to persist assembly log", exc_info=True)


def _cleanup_main_content(*, session, episode, main_content_filename: str) -> None:
    try:
        raw_value = str(main_content_filename or "").strip()
        if not raw_value:
            logging.info("[cleanup] No main_content_filename provided, skipping cleanup")
            return

        # Check user's auto_delete_raw_audio setting
        from api.models.user import User
        import json
        
        user = session.get(User, episode.user_id)
        if not user:
            logging.warning("[cleanup] Could not find user for episode, skipping cleanup check")
            return
            
        auto_delete = False
        try:
            settings_json = getattr(user, 'audio_cleanup_settings_json', None)
            if settings_json:
                settings = json.loads(settings_json)
                auto_delete = bool(settings.get('autoDeleteRawAudio', False))
            logging.info("[cleanup] User auto_delete_raw_audio setting: %s", auto_delete)
        except Exception as e:
            logging.warning("[cleanup] Could not parse user settings, defaulting to not delete: %s", e)
            auto_delete = False
        
        if not auto_delete:
            logging.info("[cleanup] User has disabled auto-delete for raw audio files, creating 'safe to delete' notification")
            # Find the MediaItem to mark it as used
            main_fn = os.path.basename(raw_value)
            candidates: set[str] = {raw_value}
            if main_fn:
                candidates.add(main_fn)
            if raw_value.startswith("gs://"):
                try:
                    without_scheme = raw_value[len("gs://") :]
                    if without_scheme:
                        candidates.add(without_scheme)
                except Exception:
                    pass
            
            query = select(MediaItem).where(
                MediaItem.user_id == episode.user_id,
                MediaItem.category == MediaCategory.main_content,
            )
            media_item = None
            all_items = session.exec(query).all()
            
            for item in all_items:
                stored = str(getattr(item, "filename", "") or "").strip()
                if not stored:
                    continue
                if stored in candidates:
                    media_item = item
                    break
                for candidate in candidates:
                    if stored.endswith(candidate) or candidate.endswith(stored):
                        media_item = item
                        break
                if media_item:
                    break
            
            if media_item:
                # Mark the MediaItem as used by this episode
                media_item.used_in_episode_id = episode.id
                
                # Create notification for user
                friendly_name = media_item.friendly_name or os.path.basename(media_item.filename)
                episode_title = episode.title or "your episode"
                
                notification = Notification(
                    user_id=user.id,
                    type="info",
                    title="Raw Audio File Ready to Delete",
                    body=f"Your raw file '{friendly_name}' was successfully used in '{episode_title}' and can now be safely deleted from your Media Library."
                )
                session.add(notification)
                
                try:
                    if not _commit_with_retry(session):
                        logging.error("[cleanup] Failed to save notification and MediaItem update after retries")
                    else:
                        logging.info("[cleanup] ✅ Created notification and marked MediaItem as used in episode")
                except Exception as e:
                    logging.error("[cleanup] Exception creating notification: %s", e, exc_info=True)
                    session.rollback()
            else:
                logging.warning("[cleanup] Could not find MediaItem to mark as used")
            
            return

        logging.info("[cleanup] Starting cleanup for main_content_filename: %s", raw_value)
        
        main_fn = os.path.basename(raw_value)
        # Build a set of plausible filename representations to match against the
        # stored MediaItem filename. In practice uploads are stored as gs:// URIs
        # (or local paths) while episode metadata may only persist the basename.
        candidates: set[str] = {raw_value}
        if main_fn:
            candidates.add(main_fn)
        if raw_value.startswith("gs://"):
            try:
                without_scheme = raw_value[len("gs://") :]
                if without_scheme:
                    candidates.add(without_scheme)
            except Exception:
                pass

        logging.info("[cleanup] Looking for MediaItem with candidates: %s", list(candidates)[:3])
        
        query = select(MediaItem).where(
            MediaItem.user_id == episode.user_id,
            MediaItem.category == MediaCategory.main_content,
        )
        media_item = None
        all_items = session.exec(query).all()
        logging.info("[cleanup] Found %d main_content MediaItems for user", len(all_items))
        
        for item in all_items:
            stored = str(getattr(item, "filename", "") or "").strip()
            if not stored:
                continue
            if stored in candidates:
                media_item = item
                logging.info("[cleanup] Matched MediaItem by exact filename: %s", stored)
                break
            # Fallback: match when either value endswith the other to support
            # cases like gs://bucket/path/<name> vs <name>.
            for candidate in candidates:
                if stored.endswith(candidate) or candidate.endswith(stored):
                    media_item = item
                    logging.info("[cleanup] Matched MediaItem by partial filename: %s (candidate: %s)", stored, candidate)
                    break
            if media_item:
                break
        
        if not media_item:
            logging.warning("[cleanup] Could not find MediaItem matching candidates: %s", list(candidates)[:3])
            return
        if media_item.category != MediaCategory.main_content:
            logging.warning("[cleanup] Found MediaItem but category is %s, not main_content", media_item.category)
            return

        filename = str(media_item.filename or "").strip()
        removed_file = False

        if filename.startswith("gs://"):
            logging.info("[cleanup] Attempting to delete GCS object: %s", filename)
            try:
                without_scheme = filename[len("gs://") :]
                bucket_name, key = without_scheme.split("/", 1)
                if bucket_name and key:
                    from google.cloud import storage  # type: ignore

                    client = storage.Client()
                    bucket = client.bucket(bucket_name)
                    blob = bucket.blob(key)
                    
                    # Check if blob exists before deleting
                    if blob.exists():
                        blob.delete()
                        removed_file = True
                        logging.info("[cleanup] Successfully deleted GCS object: %s", filename)
                    else:
                        logging.warning("[cleanup] GCS object does not exist: %s", filename)
                        removed_file = True  # Consider it removed if it doesn't exist
            except Exception as e:
                logging.warning(
                    "[cleanup] Failed to delete GCS object %s: %s", filename, e, exc_info=True
                )
        else:
            try:
                base_name = Path(filename).name
            except Exception:
                base_name = filename

            file_candidates: list[Path] = []
            for root in {MEDIA_DIR, PROJECT_ROOT / "media_uploads", Path("media_uploads")}:
                try:
                    file_candidates.append((root / base_name).resolve(strict=False))
                except Exception:
                    continue

            seen: set[str] = set()
            for candidate in file_candidates:
                try:
                    key = str(candidate)
                except Exception:
                    key = repr(candidate)
                if key in seen:
                    continue
                seen.add(key)
                if candidate.exists():
                    try:
                        candidate.unlink()
                        removed_file = True
                    except Exception:
                        logging.warning(
                            "[cleanup] Unable to unlink file %s", candidate, exc_info=True
                        )

        # Delete the MediaTranscript first (foreign key constraint)
        from api.models.transcription import MediaTranscript
        transcript_query = select(MediaTranscript).where(MediaTranscript.media_item_id == media_item.id)
        transcripts = session.exec(transcript_query).all()
        if transcripts:
            logging.info("[cleanup] Deleting %d MediaTranscript record(s) for MediaItem (id=%s)", len(transcripts), media_item.id)
            for transcript in transcripts:
                session.delete(transcript)
        
        # Delete the MediaItem from database
        logging.info("[cleanup] Deleting MediaItem (id=%s) from database", media_item.id)
        try:
            session.delete(media_item)
            if not _commit_with_retry(session):
                logging.error("[cleanup] Failed to delete MediaItem from database after retries (id=%s)", media_item.id)
            else:
                logging.info("[cleanup] Successfully deleted MediaItem from database (id=%s)", media_item.id)
        except Exception as e:
            logging.error("[cleanup] Exception deleting MediaItem from database: %s", e, exc_info=True)
            session.rollback()
            raise

        logging.info(
            "[cleanup] ✅ Cleanup complete for %s (GCS file removed: %s, DB record removed: True)",
            media_item.filename,
            removed_file,
        )
    except Exception as e:
        logging.error("[cleanup] ❌ Cleanup failed: %s", e, exc_info=True)


def _mark_episode_error(session, episode, reason: str) -> None:
    """Persist a failure state for the episode when assembly cannot produce audio."""

    try:
        from api.models.podcast import EpisodeStatus as EpStatus

        episode.status = EpStatus.error  # type: ignore[attr-defined]
    except Exception:
        episode.status = "error"  # type: ignore[assignment]

    try:
        episode.final_audio_path = None
    except Exception:
        pass

    try:
        session.add(episode)
        if not _commit_with_retry(session):
            logging.error("[_mark_episode_error] Failed to commit error status after retries")
    except Exception:
        session.rollback()
    
    # Create error notification for user
    try:
        episode_title = episode.title or "Untitled Episode"
        notification = Notification(
            user_id=episode.user_id,
            type="error",
            title="Episode Assembly Failed",
            body=f"Failed to assemble '{episode_title}': {reason}"
        )
        session.add(notification)
        if not _commit_with_retry(session):
            logging.error("[_mark_episode_error] Failed to create error notification after retries")
        else:
            logging.info("[_mark_episode_error] ✅ Created error notification for user")
    except Exception as e:
        logging.error("[_mark_episode_error] Exception creating error notification: %s", e, exc_info=True)
        session.rollback()
    
    logging.error("[assemble] %s", reason)


def _finalize_episode(
    *,
    session,
    media_context: media.MediaContext,
    transcript_context: transcript.TranscriptContext,
    main_content_filename: str,
    output_filename: str,
    tts_values: dict,
    use_auphonic: bool,
):
    episode = media_context.episode
    stream_log_path = str(ASSEMBLY_LOG_DIR / f"{episode.id}.log")
    
    # ========== CHECK IF ADVANCED AUDIO ASSETS ARE AVAILABLE ==========
    # Advanced mastering runs during upload/transcription; if requested we expect
    # the MediaItem to mark itself as processed so we can pull the cleaned audio here.
    auphonic_requested = bool(use_auphonic)
    auphonic_processed = False
    auphonic_cleaned_audio_path = None
    auphonic_processed_path = None  # For backward compatibility
    
    if auphonic_requested:
        try:
            from api.models.podcast import MediaItem, MediaCategory
            from sqlmodel import select
            
            filename_search = main_content_filename.split("/")[-1]
            logging.info(
                "[assemble] 🔍 Searching for advanced audio assets: user=%s, filename_contains='%s'",
                episode.user_id,
                filename_search,
            )
            
            media_item = session.exec(
                select(MediaItem)
                .where(MediaItem.user_id == episode.user_id)
                .where(MediaItem.category == MediaCategory.main_content)
                .where(MediaItem.filename.contains(filename_search))
                .order_by(MediaItem.created_at.desc())
            ).first()
            
            if media_item and media_item.auphonic_processed:
                auphonic_processed = True
                logging.info("[assemble] ✅ Advanced audio located via MediaItem %s", media_item.id)
                
                if media_item.auphonic_cleaned_audio_url and media_item.auphonic_cleaned_audio_url.startswith("gs://"):
                    from pathlib import Path as PathLib
                    
                    temp_dir = PathLib(tempfile.gettempdir()) / f"auphonic_{episode.id}"
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    temp_audio_path = temp_dir / f"auphonic_cleaned_{episode.id}.mp3"
                    
                    try:
                        parts = media_item.auphonic_cleaned_audio_url[5:].split("/", 1)
                        bucket_name = parts[0]
                        key = parts[1] if len(parts) > 1 else ""
                        
                        file_bytes = storage.download_bytes(bucket_name, key)
                        temp_audio_path.write_bytes(file_bytes)
                        
                        auphonic_cleaned_audio_path = temp_audio_path
                        auphonic_processed_path = temp_audio_path
                        main_content_filename = str(temp_audio_path)
                        
                        logging.info(
                            "[assemble] Downloaded advanced audio master: %s (%d bytes)",
                            temp_audio_path,
                            len(file_bytes),
                        )
                    except Exception as e:
                        logging.error("[assemble] Failed to download advanced audio master: %s", e)
                        auphonic_processed = False
                
                if media_item and media_item.auphonic_metadata:
                    try:
                        import json
                        
                        auphonic_meta = json.loads(media_item.auphonic_metadata)
                        logging.info("[assemble] ✅ Advanced metadata available: %s", list(auphonic_meta.keys()))
                        
                        if auphonic_meta.get("brief_summary"):
                            episode.brief_summary = auphonic_meta["brief_summary"]
                            logging.info("[assemble] ✅ Saved brief_summary (%d chars)", len(auphonic_meta["brief_summary"]))
                        
                        if auphonic_meta.get("long_summary"):
                            episode.long_summary = auphonic_meta["long_summary"]
                            logging.info("[assemble] ✅ Saved long_summary (%d chars)", len(auphonic_meta["long_summary"]))
                        
                        if auphonic_meta.get("tags"):
                            episode.episode_tags = json.dumps(auphonic_meta["tags"])
                            logging.info("[assemble] ✅ Saved %d tags", len(auphonic_meta["tags"]))
                        
                        if auphonic_meta.get("chapters"):
                            episode.episode_chapters = json.dumps(auphonic_meta["chapters"])
                            logging.info("[assemble] ✅ Saved %d chapters", len(auphonic_meta["chapters"]))
                    except Exception as e:
                        logging.warning("[assemble] Failed to parse advanced audio metadata: %s", e)
            else:
                logging.warning(
                    "[assemble] ⚠️ Advanced audio requested but no processed MediaItem found for '%s'",
                    filename_search,
                )
        except Exception as e:
            logging.error("[assemble] Failed to load advanced audio state: %s", e, exc_info=True)
            auphonic_processed = False
    else:
        logging.info("[assemble] Advanced audio disabled for this episode; using standard pipeline")
    
    # Build cleanup options
    if auphonic_processed:
        # Skip filler/silence removal for Auphonic audio (already processed)
        # BUT allow Flubber and Intern (user-directed features)
        cleanup_opts = {
            **transcript_context.mixer_only_options,
            "internIntent": transcript_context.intern_intent,
            "flubberIntent": transcript_context.flubber_intent,
            "auphonic_processed": True,  # Pass flag to orchestrator_steps
            "removePauses": False,  # Skip silence compression
            "removeFillers": False,  # Skip filler removal
        }
        logging.info("[assemble] Using Auphonic-processed audio, skipping filler/silence removal")
    else:
        # Standard cleanup for AssemblyAI + custom processing
        cleanup_opts = {
            **transcript_context.mixer_only_options,
            "internIntent": transcript_context.intern_intent,
            "flubberIntent": transcript_context.flubber_intent,
            "auphonic_processed": False,
        }
    
    # ========== END AUPHONIC CHECK ==========

    # NEW: Check if we should use chunked processing for long files
    # NOTE: Chunked processing is skipped if Auphonic was used (already processed)
    use_chunking = False
    
    if not auphonic_processed:  # Only use chunking if NOT Auphonic-processed
        from pathlib import Path as PathLib
        from worker.tasks.assembly import chunked_processor
        
        # Find the main audio file path
        # Use the resolved source_audio_path from media_context if available (full path to downloaded file)
        if media_context.source_audio_path and media_context.source_audio_path.exists():
            main_audio_path = media_context.source_audio_path
            logging.info("[assemble] Using resolved source_audio_path for chunking check: %s", main_audio_path)
        else:
            # Fallback to working_audio_name or main_content_filename
            audio_name = episode.working_audio_name or main_content_filename
            main_audio_path = MEDIA_DIR / audio_name if not PathLib(audio_name).is_absolute() else PathLib(audio_name)
            logging.info("[assemble] Using fallback path for chunking check: %s", main_audio_path)
        
        use_chunking = chunked_processor.should_use_chunking(main_audio_path)
    
    if use_chunking:
        logging.info("[assemble] File duration >10min, using chunked processing for episode_id=%s", episode.id)
        
        # Split audio into chunks
        try:
            # Get user_id from episode
            from uuid import UUID as UUIDType
            user_uuid = UUIDType(str(episode.user_id)) if episode.user_id else UUIDType(str(episode.podcast.user_id))
            
            chunks = chunked_processor.split_audio_into_chunks(
                audio_path=main_audio_path,
                user_id=user_uuid,
                episode_id=episode.id,
            )
            
            # Split transcript to match chunks
            if transcript_context.words_json_path:
                chunked_processor.split_transcript_for_chunks(
                    transcript_path=PathLib(transcript_context.words_json_path),
                    chunks=chunks,
                )
            
            # Save chunk manifest to episode metadata
            manifest_path = PathLib(tempfile.gettempdir()) / f"chunks_{episode.id}_manifest.json"
            chunked_processor.save_chunk_manifest(chunks, manifest_path)
            
            # Dispatch Cloud Tasks for each chunk
            cleanup_options = {
                **transcript_context.mixer_only_options,
                "internIntent": transcript_context.intern_intent,
                "flubberIntent": transcript_context.flubber_intent,
            }
            
            for chunk in chunks:
                # VALIDATION: Ensure chunk has valid GCS URI before dispatching
                if not chunk.gcs_audio_uri or not chunk.gcs_audio_uri.startswith("gs://"):
                    logging.error(
                        "[assemble] ❌ Cannot dispatch chunk %d: invalid gcs_audio_uri=%s. "
                        "This should not happen - chunk upload should have failed before this point.",
                        chunk.index, chunk.gcs_audio_uri
                    )
                    chunk.status = "failed"
                    # This is a critical error - abort chunking and fall back
                    raise RuntimeError(
                        f"Chunk {chunk.index} has invalid gcs_audio_uri: {chunk.gcs_audio_uri}. "
                        "Chunked processing cannot continue. Falling back to direct processing."
                    )
                
                chunk_payload = {
                    "episode_id": str(episode.id),
                    "chunk_id": chunk.chunk_id,
                    "chunk_index": chunk.index,
                    "total_chunks": len(chunks),  # Used to detect last chunk for trailing silence trim
                    "gcs_audio_uri": chunk.gcs_audio_uri,  # Guaranteed to be valid gs:// URI
                    "gcs_transcript_uri": chunk.gcs_transcript_uri,
                    "cleanup_options": cleanup_options,
                    "user_id": str(media_context.user_id),
                }
                
                try:
                    task_info = enqueue_http_task("/api/tasks/process-chunk", chunk_payload)
                    logging.info("[assemble] ✅ Dispatched chunk %d task: %s", chunk.index, task_info)
                except Exception as e:
                    logging.error("[assemble] ❌ Failed to dispatch chunk %d: %s", chunk.index, e)
                    # Mark chunk as failed
                    chunk.status = "failed"
                    # Dispatch failure is also critical - abort chunking
                    raise RuntimeError(
                        f"Failed to dispatch chunk {chunk.index}: {e}. "
                        "Chunked processing cannot continue. Falling back to direct processing."
                    ) from e
            
            # Wait for all chunks to complete
            import time
            max_wait_seconds = 1800  # 30 minutes (matches Cloud Tasks deadline)
            poll_interval = 5  # 5 seconds
            retry_after_seconds = 600  # Retry stuck chunks after 10 minutes
            start_time = time.time()
            chunk_dispatch_times = {}  # Track when each chunk was dispatched
            chunk_retry_counts = {}  # Track retry attempts per chunk
            
            # Record initial dispatch times
            for chunk in chunks:
                chunk_dispatch_times[chunk.chunk_id] = start_time
                chunk_retry_counts[chunk.chunk_id] = 0
            
            logging.info("[assemble] Waiting for %d chunks to complete...", len(chunks))
            
            while time.time() - start_time < max_wait_seconds:
                # Check if all chunks have cleaned URIs in storage backend
                all_complete = True
                for chunk in chunks:
                    if not chunk.gcs_audio_uri:
                        all_complete = False
                        continue
                    
                    cleaned_uri = chunk.gcs_audio_uri.replace(".wav", "_cleaned.mp3")
                    
                    # Parse URI to check existence
                    if cleaned_uri.startswith("gs://"):
                        parts = cleaned_uri[5:].split("/", 1)
                        if len(parts) == 2:
                            from infrastructure import gcs
                            bucket_name, blob_path = parts
                            exists = gcs.blob_exists(bucket_name, blob_path)
                            
                            if exists:
                                chunk.cleaned_path = f"/tmp/{chunk.chunk_id}_cleaned.mp3"
                                chunk.gcs_cleaned_uri = cleaned_uri
                                chunk.status = "completed"
                            else:
                                all_complete = False
                                
                                # AUTOMATIC RETRY: If chunk hasn't completed after retry_after_seconds, re-dispatch
                                elapsed = time.time() - chunk_dispatch_times.get(chunk.chunk_id, start_time)
                                max_retries = 3
                                
                                if elapsed > retry_after_seconds and chunk_retry_counts.get(chunk.chunk_id, 0) < max_retries:
                                    logging.warning(
                                        "[assemble] Chunk %s not completed after %.0fs, re-dispatching (retry %d/%d)",
                                        chunk.chunk_id, elapsed, chunk_retry_counts[chunk.chunk_id] + 1, max_retries
                                    )
                                    
                                    # Re-dispatch the stuck chunk task with FULL payload (same as initial dispatch)
                                    from infrastructure import tasks_client
                                    task_payload = {
                                        "episode_id": str(episode.id),
                                        "chunk_id": chunk.chunk_id,
                                        "chunk_index": chunk.index,
                                        "total_chunks": len(chunks),
                                        "gcs_audio_uri": chunk.gcs_audio_uri,
                                        "gcs_transcript_uri": chunk.gcs_transcript_uri,
                                        "cleanup_options": cleanup_options,
                                        "user_id": str(media_context.user_id),
                                    }
                                    
                                    try:
                                        task_info = tasks_client.enqueue_http_task(
                                            "/api/tasks/process-chunk",
                                            task_payload,
                                        )
                                        logging.info("[assemble] Re-dispatched chunk %s: %s", chunk.chunk_id, task_info)
                                        
                                        # Reset dispatch time and increment retry counter
                                        chunk_dispatch_times[chunk.chunk_id] = time.time()
                                        chunk_retry_counts[chunk.chunk_id] += 1
                                    except Exception as retry_err:
                                        logging.error("[assemble] Failed to re-dispatch chunk %s: %s", chunk.chunk_id, retry_err)
                
                if all_complete:
                    logging.info("[assemble] All %d chunks completed in %.1f seconds",
                               len(chunks), time.time() - start_time)
                    break
                
                time.sleep(poll_interval)
            
            if not all_complete:
                # Log which chunks failed before raising
                failed_chunks = [c.chunk_id for c in chunks if c.status != "completed"]
                logging.error("[assemble] Chunk processing timed out after %ds. Failed chunks: %s", max_wait_seconds, failed_chunks)
                raise RuntimeError(f"Chunk processing timed out after {max_wait_seconds}s. Failed: {failed_chunks}")
            
            # Download and reassemble chunks
            logging.info("[assemble] Reassembling %d chunks...", len(chunks))
            
            # Download cleaned chunks
            for chunk in chunks:
                if chunk.gcs_cleaned_uri:
                    gcs_uri = chunk.gcs_cleaned_uri
                    if gcs_uri.startswith("gs://"):
                        parts = gcs_uri[5:].split("/", 1)
                        if len(parts) == 2:
                            from infrastructure import gcs
                            bucket_name, blob_path = parts
                            cleaned_bytes = gcs.download_gcs_bytes(bucket_name, blob_path)
                            if cleaned_bytes:
                                chunk_path = PathLib(f"/tmp/{chunk.chunk_id}_cleaned.mp3")
                                chunk_path.write_bytes(cleaned_bytes)
                                chunk.cleaned_path = str(chunk_path)
                                logging.info("[assemble] Downloaded chunk %d: %s", chunk.index, chunk_path)
            
            # Reassemble into single file
            reassembled_path = PathLib(f"/tmp/{episode.id}_reassembled.mp3")
            chunked_processor.reassemble_chunks(chunks, reassembled_path)
            
            # Use reassembled file as main content for mixing
            main_content_filename = str(reassembled_path)
            mix_only_mode = True
            
            logging.info("[assemble] Chunked processing complete, proceeding to mixing with %s", main_content_filename)
            
        except Exception as e:
            logging.error("[assemble] Chunked processing failed: %s", e, exc_info=True)
            logging.warning("[assemble] Falling back to direct processing")
            use_chunking = False
    
    # Determine which audio file to use for mixing
    # Priority: Auphonic processed > chunked reassembled > resolved source path > working_audio_name > main_content_filename
    if auphonic_processed and auphonic_processed_path:
        audio_input_path = str(auphonic_processed_path)
    elif use_chunking:
        audio_input_path = main_content_filename  # This is the reassembled path
    else:
        # Use the resolved source_audio_path from media_context if available (full path to downloaded file)
        # This ensures the audio processor can find the file that was downloaded from GCS
        if media_context.source_audio_path:
            source_path = Path(str(media_context.source_audio_path))
            # CRITICAL: Resolve to absolute path and verify file exists
            try:
                source_path = source_path.resolve()
            except Exception as resolve_err:
                logging.warning("[assemble] Failed to resolve path %s: %s", source_path, resolve_err)
            
            # Verify the file exists at the resolved path
            if source_path.exists() and source_path.is_file():
                audio_input_path = str(source_path)
                file_size = source_path.stat().st_size
                logging.info("[assemble] ✅ Using resolved source_audio_path: %s (exists: True, size: %d bytes, absolute: %s)", 
                           audio_input_path, file_size, source_path.is_absolute())
            else:
                # File doesn't exist at resolved path - this is a CRITICAL error
                logging.error("[assemble] ❌ CRITICAL: Resolved source_audio_path doesn't exist: %s (is_file: %s, exists: %s)", 
                            source_path, source_path.is_file() if source_path.exists() else False, source_path.exists())
                
                # Try MEDIA_DIR with just the filename as fallback
                filename_only = source_path.name
                media_dir_path = MEDIA_DIR / filename_only
                
                # Check if file exists in MEDIA_DIR
                if media_dir_path.exists() and media_dir_path.is_file():
                    audio_input_path = str(media_dir_path.resolve())
                    file_size = media_dir_path.stat().st_size
                    logging.warning("[assemble] ⚠️ Using fallback path in MEDIA_DIR: %s (size: %d bytes)", audio_input_path, file_size)
                else:
                    # CRITICAL ERROR: File not found anywhere
                    logging.error("[assemble] ❌ CRITICAL: File not found at any location:")
                    logging.error("[assemble]   - Original resolved path: %s (exists: %s)", source_path, source_path.exists())
                    logging.error("[assemble]   - MEDIA_DIR fallback: %s (exists: %s)", media_dir_path, media_dir_path.exists())
                    logging.error("[assemble]   - MEDIA_DIR value: %s", MEDIA_DIR)
                    logging.error("[assemble]   - PROJECT_ROOT value: %s", PROJECT_ROOT)
                    
                    # Try to list files in MEDIA_DIR for debugging
                    try:
                        if MEDIA_DIR.exists():
                            files_in_media_dir = list(MEDIA_DIR.glob("*"))
                            logging.error("[assemble]   - Files in MEDIA_DIR: %s", [f.name for f in files_in_media_dir[:10]])
                    except Exception as list_err:
                        logging.error("[assemble]   - Failed to list MEDIA_DIR: %s", list_err)
                    
                    # Last resort: use the resolved path anyway (will fail with clear error)
                    audio_input_path = str(source_path)
                    logging.error("[assemble] ❌ Using non-existent path (will fail): %s", audio_input_path)
        else:
            # Fallback to working_audio_name or main_content_filename
            # If working_audio_name is just a filename, it should be relative to MEDIA_DIR
            audio_input_path = episode.working_audio_name or main_content_filename
            logging.info("[assemble] Using fallback audio_input_path: %s", audio_input_path)
    
    # Prepare cleanup options - respect existing cleanup_opts from Auphonic if set
    # Otherwise, skip all cleaning if chunking was used, or use normal options
    if auphonic_processed:
        # cleanup_opts already set by Auphonic block above (skip all cleaning)
        pass
    elif use_chunking:
        # Audio is already fully cleaned and reassembled - just mix it
        # BUT: Intern/Flubber need to be applied at the mixing stage if user reviewed them
        cleanup_opts = {
            **transcript_context.mixer_only_options,
            "internIntent": transcript_context.intern_intent,  # Preserve user's intent (for Intern audio insertion)
            "flubberIntent": "skip",  # Skip filler removal (already done in chunks)
            "removePauses": False,  # Skip silence removal (already done in chunks)
            "removeFillers": False,  # Skip filler word removal (already done in chunks)
        }
    else:
        # Normal cleanup options
        cleanup_opts = {
            **transcript_context.mixer_only_options,
            "internIntent": transcript_context.intern_intent,
            "flubberIntent": transcript_context.flubber_intent,
        }
    
    # Standard audio processing (for short files or chunking fallback)
    # CRITICAL SECTION: This is where exit code -9 crashes have been occurring
    try:
        # CRITICAL: Verify template is available before calling audio processor
        template_obj = media_context.template
        if template_obj is None:
            logging.error("[assemble] ❌ CRITICAL: Template is None in media_context - template mixing will fail!")
        else:
            template_id = getattr(template_obj, 'id', 'unknown')
            template_segments_json = getattr(template_obj, 'segments_json', None)
            try:
                import json
                segments_count = len(json.loads(template_segments_json or "[]"))
                logging.info("[assemble] ✅ Template verified: id=%s, segments_count=%d", template_id, segments_count)
            except Exception as e:
                logging.warning("[assemble] ⚠️ Failed to parse template segments_json: %s", e)
        
        logging.info("[assemble] Starting audio processor with audio_input_path=%s, mix_only=%s, template_id=%s", 
                    audio_input_path, True, getattr(template_obj, 'id', 'None') if template_obj else 'None')
        
        final_path, log_data, ai_note_additions = audio_processor.process_and_assemble_episode(
            template=template_obj,  # Use verified template object
            main_content_filename=audio_input_path,
            output_filename=output_filename,
            cleanup_options=cleanup_opts,
            tts_overrides=tts_values or {},
            cover_image_path=media_context.cover_image_path,
            elevenlabs_api_key=media_context.elevenlabs_api_key,
            tts_provider=media_context.preferred_tts_provider,
            mix_only=True,  # Always mix_only since cleaning is done
            words_json_path=str(transcript_context.words_json_path)
            if transcript_context.words_json_path
            else None,
            log_path=stream_log_path,
        )
        
        logging.info("[assemble] Audio processor completed successfully")
        
    except MemoryError as mem_err:
        logging.error("[assemble] MEMORY EXHAUSTION during audio processing: %s", mem_err, exc_info=True)
        _mark_episode_error(
            session,
            episode,
            reason=f"Episode assembly failed due to memory exhaustion: {mem_err}",
        )
        raise RuntimeError(f"Audio processing failed due to memory exhaustion: {mem_err}")
    except Exception as proc_err:
        logging.error("[assemble] AUDIO PROCESSOR CRASHED: %s", proc_err, exc_info=True)
        logging.error("[assemble] This may indicate FFmpeg crash, memory spike, or audio format incompatibility")
        logging.error(
            "[assemble] audio_input_path=%s, advanced_requested=%s, use_chunking=%s",
            audio_input_path,
            auphonic_requested,
            use_chunking,
        )
        _mark_episode_error(
            session,
            episode,
            reason=f"Episode assembly crashed during audio processing: {type(proc_err).__name__}: {proc_err}",
        )
        raise RuntimeError(f"Audio processor crashed: {type(proc_err).__name__}: {proc_err}")

    logging.info(
        "[assemble] processor invoked: mix_only=True words_json=%s",
        str(transcript_context.words_json_path)
        if transcript_context.words_json_path
        else "None",
    )

    final_path_str = str(final_path or "").strip()
    if not final_path_str:
        _mark_episode_error(
            session,
            episode,
            reason="Episode assembly did not return a final audio path",
        )
        raise RuntimeError("Episode assembly produced no final audio path")

    try:
        final_path_obj = Path(final_path_str)
    except Exception:
        final_path_obj = Path(str(final_path))

    final_basename = final_path_obj.name
    if not final_basename:
        _mark_episode_error(
            session,
            episode,
            reason=f"Episode assembly produced invalid filename from path={final_path_str!r}",
        )
        raise RuntimeError("Episode assembly produced an invalid final audio filename")

    # Ensure the canonical copy lives under FINAL_DIR
    try:
        dest_final = FINAL_DIR / final_basename
        src_exists = final_path_obj.exists()
        if src_exists:
            try:
                if final_path_obj.resolve() != dest_final.resolve():
                    dest_final.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(final_path_obj, dest_final)
                    final_path_obj = dest_final
            except Exception:
                dest_final.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(final_path_obj, dest_final)
                final_path_obj = dest_final
        elif dest_final.exists():
            final_path_obj = dest_final
        else:
            logging.warning(
                "[assemble] Final audio missing at %s and %s",
                str(final_path),
                str(dest_final),
            )
            if not dest_final.exists():
                _mark_episode_error(
                    session,
                    episode,
                    reason=f"Final audio missing after export: {final_path_str}",
                )
                raise RuntimeError(
                    f"Episode assembly completed without producing an audio file ({final_path_str})"
                )
    except Exception:
        logging.warning(
            "[assemble] Failed to ensure final audio resides in FINAL_DIR", exc_info=True
        )

    # Mirror into MEDIA_DIR so the API container can serve previews even if the worker
    # generated the file in a different workspace location.
    try:
        media_mirror = MEDIA_DIR / final_basename
        if final_path_obj.exists():
            try:
                if final_path_obj.resolve() != media_mirror.resolve():
                    media_mirror.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(final_path_obj, media_mirror)
            except Exception:
                media_mirror.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(final_path_obj, media_mirror)
    except Exception:
        logging.warning(
            "[assemble] Failed to mirror final audio into MEDIA_DIR", exc_info=True
        )

    # Initialize fallback_candidate BEFORE conditional usage (Python scoping fix)
    fallback_candidate = FINAL_DIR / final_basename
    
    if not final_path_obj.exists():
        if fallback_candidate.exists():
            final_path_obj = fallback_candidate
        else:
            _mark_episode_error(
                session,
                episode,
                reason=f"Final audio file not found after assembly: {final_basename}",
            )
            raise RuntimeError(
                f"Episode final audio file not found after assembly ({final_basename})"
            )

    try:
        from api.models.podcast import EpisodeStatus as EpStatus

        episode.status = EpStatus.processed  # type: ignore[attr-defined]
    except Exception:
        episode.status = "processed"  # type: ignore[assignment]

    if ai_note_additions:
        existing = episode.show_notes or ""
        combined = existing + ("\n\n" if existing else "") + "\n\n".join(ai_note_additions)
        episode.show_notes = combined
        logging.info(
            "[assemble] Added %s AI shownote additions", len(ai_note_additions)
        )

    episode.final_audio_path = final_basename
    
    # ========== CHARGE CREDITS FOR ASSEMBLY ==========
    try:
        from api.services.billing import credits
        
        # Get audio duration in SECONDS (convert from milliseconds)
        # charge_for_assembly expects seconds, not minutes!
        audio_duration_seconds = (episode.duration_ms / 1000.0) if episode.duration_ms else 0.0
        
        # Determine if Auphonic was used (doesn't affect assembly rate, but logged for transparency)
        use_auphonic_flag = bool(auphonic_processed)
        
        # Charge credits for assembly
        logging.info(
            "[assemble] 💳 Charging credits: episode_id=%s, duration=%.2f seconds (%.2f minutes), auphonic=%s",
            episode.id,
            audio_duration_seconds,
            audio_duration_seconds / 60.0,
            use_auphonic_flag
        )
        
        ledger_entry, cost_breakdown = credits.charge_for_assembly(
            session=session,
            user=session.get(User, episode.user_id),
            episode_id=episode.id,
            total_duration_seconds=audio_duration_seconds,
            use_auphonic=use_auphonic_flag,
            correlation_id=f"assembly_{episode.id}",
        )
        
        logging.info(
            "[assemble] ✅ Credits charged: %.2f credits (duration=%.2fs, rate=%.2f credits/sec)",
            cost_breakdown['total_credits'],
            cost_breakdown['duration_seconds'],
            cost_breakdown['assembly_rate_per_sec']
        )
        
    except Exception as credits_err:
        logging.error(
            "[assemble] ⚠️ Failed to charge credits for assembly (non-fatal): %s",
            credits_err,
            exc_info=True
        )
        # Rollback the session to recover from the failed transaction
        session.rollback()
        # Re-load the episode after rollback to ensure it's attached to the session
        session.refresh(episode)
        # Don't fail the entire assembly if credit charging fails
        # User still gets their episode, we just lose the billing record
    # ========== END CREDIT CHARGING ==========

    # Upload final audio to GCS - REQUIRED, NO FALLBACK
    # GCS is the sole source of truth for all media files
    user_id = str(episode.user_id)
    episode_id = str(episode.id)
    gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
    
    # Upload audio file
    audio_src = fallback_candidate if fallback_candidate and fallback_candidate.is_file() else None
    if not audio_src:
        raise RuntimeError(f"[assemble] Audio file not found at {fallback_candidate}. Cannot proceed without audio source.")
    
    # Get audio file size for RSS feed
    try:
        episode.audio_file_size = audio_src.stat().st_size
        logging.info("[assemble] Audio file size: %d bytes", episode.audio_file_size)
    except Exception as size_err:
        raise RuntimeError(f"[assemble] Could not get audio file size: {size_err}") from size_err
    
    # Get audio duration for RSS feed
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(str(audio_src))
        episode.duration_ms = len(audio)
        logging.info("[assemble] Audio duration: %d ms (%.1f minutes)", episode.duration_ms, episode.duration_ms / 1000 / 60)
    except Exception as dur_err:
        raise RuntimeError(f"[assemble] Could not get audio duration: {dur_err}") from dur_err

    # ========== CHARGE OVERLENGTH SURCHARGE (if applicable) ==========
    # Check if episode exceeds plan max_minutes limit and charge surcharge
    try:
        from api.services.billing.overlength import apply_overlength_surcharge
        
        # Get user for surcharge calculation
        user = session.get(User, episode.user_id)
        if user and episode.duration_ms:
            # Convert duration from milliseconds to minutes
            episode_duration_minutes = episode.duration_ms / 1000.0 / 60.0
            
            # Apply overlength surcharge (returns None if no surcharge applies)
            surcharge_credits = apply_overlength_surcharge(
                session=session,
                user=user,
                episode_id=episode.id,
                episode_duration_minutes=episode_duration_minutes,
                correlation_id=f"overlength_{episode.id}",
            )
            
            if surcharge_credits:
                logging.info(
                    "[assemble] 💳 Overlength surcharge applied: episode_id=%s, duration=%.2f minutes, surcharge=%.2f credits",
                    episode.id,
                    episode_duration_minutes,
                    surcharge_credits
                )
            else:
                logging.debug(
                    "[assemble] No overlength surcharge: episode_id=%s, duration=%.2f minutes (within plan limit)",
                    episode.id,
                    episode_duration_minutes
                )
    except Exception as surcharge_err:
        logging.error(
            "[assemble] ⚠️ Failed to apply overlength surcharge (non-fatal): %s",
            surcharge_err,
            exc_info=True
        )
        # Don't fail the entire assembly if surcharge fails
        # User still gets their episode, we just lose the surcharge billing record
    # ========== END OVERLENGTH SURCHARGE ==========

    # ========== AUDIO NORMALIZATION (Standard pipeline only) ==========
    # Apply program-loudness normalization when advanced mastering is disabled
    try:
        from api.core.config import settings
        from api.services.audio.normalizer import run_loudnorm_two_pass
        import tempfile
        
        # Check if normalization is enabled
        normalize_enabled = getattr(settings, 'AUDIO_NORMALIZE_ENABLED', True)
        
        # Determine if the user prefers advanced mastering
        user = session.get(User, episode.user_id)
        advanced_audio_enabled = bool(getattr(user, "use_advanced_audio_processing", False)) if user else False
        
        # Skip normalization if disabled, if the user prefers advanced mastering,
        # or if this episode already has advanced mastering artifacts.
        should_normalize = (
            normalize_enabled 
            and not advanced_audio_enabled
            and not auphonic_processed
        )
        
        if should_normalize:
            logging.info("[assemble] [AUDIO_NORM] Starting loudness normalization for standard pipeline")
            
            target_lufs = getattr(settings, 'AUDIO_NORMALIZE_TARGET_LUFS', -16.0)
            tp_ceil = getattr(settings, 'AUDIO_NORMALIZE_TP_CEILING_DBTP', -1.0)
            
            # Create temp file for normalized output
            with tempfile.NamedTemporaryFile(
                suffix='.mp3',
                delete=False,
                dir=str(audio_src.parent)
            ) as tmp_norm:
                normalized_path = Path(tmp_norm.name)
            
            try:
                # Run normalization
                norm_log: List[str] = []
                run_loudnorm_two_pass(
                    input_path=audio_src,
                    output_path=normalized_path,
                    target_lufs=target_lufs,
                    tp_ceil=tp_ceil,
                    log_lines=norm_log,
                )
                
                # Log normalization results
                for log_line in norm_log:
                    logging.info(f"[assemble] {log_line}")
                
                # Validate normalized file exists and has content
                if normalized_path.exists() and normalized_path.stat().st_size > 0:
                    # Replace audio_src with normalized file
                    old_audio_src = audio_src
                    audio_src = normalized_path
                    logging.info(
                        "[assemble] [AUDIO_NORM] ✅ Normalization complete: "
                        f"original={old_audio_src.name}, normalized={normalized_path.name}"
                    )
                    
                    # Clean up old file if it was a temp file
                    try:
                        if old_audio_src != final_path_obj and old_audio_src.name.startswith('._tmp_'):
                            old_audio_src.unlink()
                    except Exception:
                        pass
                else:
                    logging.warning(
                        "[assemble] [AUDIO_NORM] ⚠️ Normalized file invalid, using original audio"
                    )
                    try:
                        normalized_path.unlink()
                    except Exception:
                        pass
                    
            except Exception as norm_err:
                logging.error(
                    "[assemble] [AUDIO_NORM] ❌ Normalization failed (non-fatal): %s",
                    norm_err,
                    exc_info=True
                )
                # Clean up temp file on error
                try:
                    if normalized_path.exists():
                        normalized_path.unlink()
                except Exception:
                    pass
                # Continue with original audio - normalization failure should not block assembly
        else:
            skip_reason = []
            if not normalize_enabled:
                skip_reason.append("disabled in config")
            if advanced_audio_enabled:
                skip_reason.append("advanced mastering enabled")
            if auphonic_processed:
                skip_reason.append("already mastered")
            logging.info(
                f"[assemble] [AUDIO_NORM] Skipping normalization: {', '.join(skip_reason)}"
            )
    except Exception as norm_check_err:
        # If normalization check fails, log but don't block assembly
        logging.warning(
            "[assemble] [AUDIO_NORM] Failed to check normalization requirements (non-fatal): %s",
            norm_check_err,
            exc_info=True
        )
    # ========== END AUDIO NORMALIZATION ==========
    
    # Upload to cloud storage (GCS or R2) - if this fails, the entire assembly fails
    gcs_audio_key = f"{user_id}/episodes/{episode_id}/audio/{final_basename}"
    # If the orchestrator already uploaded and set gcs_audio_path, skip re-upload
    if getattr(episode, "gcs_audio_path", None):
        gcs_audio_url = episode.gcs_audio_path
        logging.info("[assemble] Skipping upload; gcs_audio_path already set: %s", gcs_audio_url)
    else:
        try:
            with open(audio_src, "rb") as f:
                gcs_audio_url = storage.upload_fileobj(gcs_bucket, gcs_audio_key, f, content_type="audio/mpeg")  # type: ignore[attr-defined]
        except Exception as storage_err:
            raise RuntimeError(f"[assemble] CRITICAL: Failed to upload audio to cloud storage. Episode assembly cannot complete. Error: {storage_err}") from storage_err
    
    # Validate URL format (GCS: gs://, R2: https://)
    url_str = str(gcs_audio_url) if gcs_audio_url else ""
    if not url_str or not (url_str.startswith("gs://") or url_str.startswith("https://")):
        raise RuntimeError(f"[assemble] CRITICAL: Cloud storage upload returned invalid URL: {gcs_audio_url}")
    
    episode.gcs_audio_path = gcs_audio_url
    logging.info("[assemble] ✅ Audio uploaded to cloud storage: %s", gcs_audio_url)
    
    # Mirror to local media directory for dev environment playback
    try:
        local_audio_mirror = MEDIA_DIR / gcs_audio_key
        local_audio_mirror.parent.mkdir(parents=True, exist_ok=True)
        if not local_audio_mirror.exists():
            shutil.copy2(audio_src, local_audio_mirror)
            logging.info("[assemble] 📋 Mirrored audio to local media for dev playback: %s", local_audio_mirror)
    except Exception as mirror_err:
        logging.warning("[assemble] Failed to mirror audio to local media (non-critical): %s", mirror_err)

    cover_value = media_context.cover_image_path
    if cover_value:
        cover_str = str(cover_value)
        if cover_str.lower().startswith(("http://", "https://")):
            # Cover is already a URL (likely R2) - store it in both fields
            episode.cover_path = cover_str
            episode.gcs_cover_path = cover_str  # Store R2 URL in gcs_cover_path as well
            logging.info("[assemble] ✅ Cover is already a URL (R2): %s", cover_str)
        else:
            try:
                cover_path = Path(cover_str)
                cover_name = cover_path.name
                if cover_path.exists():
                    dest_cover = MEDIA_DIR / cover_name
                    try:
                        if cover_path.resolve() != dest_cover.resolve():
                            dest_cover.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(cover_path, dest_cover)
                            cover_path = dest_cover
                    except Exception:
                        dest_cover.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(cover_path, dest_cover)
                        cover_path = dest_cover
                    media_context.cover_image_path = str(cover_path)
                episode.cover_path = cover_name
                
                # Upload cover to R2 (FINAL FILE - covers are not intermediate, they're final assets)
                # Covers should go directly to R2 since they're not part of the assembly process, just metadata
                user_id = str(episode.user_id)
                episode_id = str(episode.id)
                r2_bucket = os.getenv("R2_BUCKET", "ppp-media").strip()
                r2_cover_key = f"{user_id}/episodes/{episode_id}/cover/{cover_name}"
                
                try:
                    from infrastructure import r2 as r2_storage
                    with open(cover_path, "rb") as f:
                        cover_ext = cover_name.lower().split(".")[-1]
                        content_type = f"image/{cover_ext}" if cover_ext in ("jpg", "jpeg", "png", "gif", "webp") else "image/jpeg"
                        r2_cover_url = r2_storage.upload_fileobj(r2_bucket, r2_cover_key, f, content_type=content_type)
                        
                        # Validate R2 URL format (should be https://)
                        cover_url_str = str(r2_cover_url) if r2_cover_url else ""
                        if not cover_url_str or not cover_url_str.startswith("https://"):
                            raise RuntimeError(f"[assemble] CRITICAL: Cover R2 upload failed - returned invalid URL: {r2_cover_url}")
                        
                        # Store R2 URL in episode (covers go to R2, not GCS)
                        episode.gcs_cover_path = r2_cover_url  # Note: field name is gcs_cover_path but it stores R2 URL for final files
                        # Also keep the local filename in cover_path for backwards compatibility
                        episode.cover_path = cover_name
                        logging.info("[assemble] ✅ Cover uploaded to R2 (final storage): %s", r2_cover_url)
                        logging.info("[assemble] ✅ Cover saved to episode: gcs_cover_path='%s', cover_path='%s'", r2_cover_url, cover_name)
                except ImportError:
                    logging.error("[assemble] ❌ R2 storage not available - cannot upload cover to R2")
                    raise RuntimeError("[assemble] R2 storage is required for final cover upload but r2 module is not available")
                except Exception as r2_err:
                    logging.error("[assemble] ❌ Failed to upload cover to R2: %s", r2_err, exc_info=True)
                    raise RuntimeError(f"[assemble] Failed to upload cover to R2: {r2_err}") from r2_err
                
                # Mirror to local media directory for dev environment playback
                try:
                    local_cover_mirror = MEDIA_DIR / r2_cover_key
                    local_cover_mirror.parent.mkdir(parents=True, exist_ok=True)
                    if not local_cover_mirror.exists():
                        shutil.copy2(cover_path, local_cover_mirror)
                        logging.info("[assemble] 📋 Mirrored cover to local media for dev playback: %s", local_cover_mirror)
                except Exception as mirror_err:
                    logging.warning("[assemble] Failed to mirror cover to local media (non-critical): %s", mirror_err)
            except Exception:
                logging.warning(
                    "[assemble] Failed to persist cover image locally", exc_info=True
                )

    # Upload final transcripts to R2 (FINAL PRODUCTION-READY FILES)
    # Final transcripts are human-readable formatted versions, not the JSON used during construction
    # They should be in R2 with the rest of the final episode assets
    try:
        from api.core.paths import TRANSCRIPTS_DIR
        user_id_str = str(episode.user_id).replace("-", "")
        episode_id_str = str(episode.id).replace("-", "")
        r2_bucket = os.getenv("R2_BUCKET", "ppp-media").strip()
        
        # Look for final transcript files (.final.txt and .txt)
        # These are created by write_final_transcripts_and_cleanup()
        final_transcript_files = []
        if output_filename:
            stem = Path(output_filename).stem
            # Check for .final.txt (content-only transcript)
            final_txt = TRANSCRIPTS_DIR / f"{stem}.final.txt"
            if final_txt.exists():
                final_transcript_files.append(("final", final_txt))
            # Check for .txt (published transcript with intro/outro labels)
            published_txt = TRANSCRIPTS_DIR / f"{stem}.txt"
            if published_txt.exists():
                final_transcript_files.append(("published", published_txt))
        
        if final_transcript_files:
            from infrastructure import r2 as r2_storage
            transcript_urls = {}
            
            for transcript_type, transcript_path in final_transcript_files:
                try:
                    r2_transcript_key = f"{user_id_str}/episodes/{episode_id_str}/transcripts/{transcript_path.name}"
                    
                    with open(transcript_path, "rb") as f:
                        r2_transcript_url = r2_storage.upload_fileobj(
                            r2_bucket, 
                            r2_transcript_key, 
                            f, 
                            content_type="text/plain; charset=utf-8"
                        )
                    
                    if r2_transcript_url and r2_transcript_url.startswith("https://"):
                        transcript_urls[transcript_type] = r2_transcript_url
                        logging.info(
                            "[assemble] ✅ Final transcript (%s) uploaded to R2: %s", 
                            transcript_type, r2_transcript_url
                        )
                    else:
                        logging.warning(
                            "[assemble] ⚠️ Final transcript (%s) R2 upload returned invalid URL: %s",
                            transcript_type, r2_transcript_url
                        )
                except Exception as transcript_err:
                    logging.warning(
                        "[assemble] ⚠️ Failed to upload final transcript (%s) to R2: %s",
                        transcript_type, transcript_err, exc_info=True
                    )
            
            # Store transcript URLs in episode metadata
            if transcript_urls:
                try:
                    import json
                    meta = json.loads(episode.meta_json or "{}")
                    if "transcripts" not in meta:
                        meta["transcripts"] = {}
                    meta["transcripts"].update({
                        "final_r2_url": transcript_urls.get("final"),
                        "published_r2_url": transcript_urls.get("published"),
                    })
                    episode.meta_json = json.dumps(meta)
                    logging.info(
                        "[assemble] ✅ Stored final transcript URLs in episode metadata: %s",
                        transcript_urls
                    )
                except Exception as meta_err:
                    logging.warning(
                        "[assemble] ⚠️ Failed to store transcript URLs in metadata: %s",
                        meta_err, exc_info=True
                    )
    except Exception as transcript_upload_err:
        # Non-critical - episode can still complete without final transcript upload
        logging.warning(
            "[assemble] ⚠️ Failed to upload final transcripts to R2 (non-critical): %s",
            transcript_upload_err, exc_info=True
        )

    # CRITICAL: This commit marks episode as "processed" - MUST succeed or episode stuck forever
    # Verify cover image is set before committing
    logging.info("[assemble] 🔍 Pre-commit check: episode.gcs_cover_path='%s', episode.cover_path='%s'", 
                episode.gcs_cover_path, episode.cover_path)
    session.add(episode)
    if not _commit_with_retry(session, max_retries=5, backoff_seconds=2.0):
        logging.error(
            "[assemble] CRITICAL: Failed to commit final episode status (status=processed) after 5 retries! "
            "Episode %s will appear stuck in 'processing' state.", episode.id
        )
        # Last-ditch attempt: mark as error so user knows something went wrong
        try:
            from api.models.podcast import EpisodeStatus as _EpStatus
            episode.status = _EpStatus.error  # type: ignore[attr-defined]
        except Exception:
            episode.status = "error"  # type: ignore[assignment]
        try:
            episode.spreaker_publish_error = "Failed to persist completion status to database after multiple retries"
            session.commit()  # One final try without retry
        except Exception:
            logging.exception("[assemble] Even error status commit failed - episode truly stuck")
    
    # Refresh episode to verify values were saved (for debugging)
    try:
        session.refresh(episode)
        logging.info("[assemble] ✅ Post-commit verification: episode.gcs_cover_path='%s', episode.cover_path='%s', episode.status='%s'", 
                    episode.gcs_cover_path, episode.cover_path, episode.status)
    except Exception as refresh_err:
        logging.warning("[assemble] Failed to refresh episode after commit: %s", refresh_err)
    
    logging.info("[assemble] done. final=%s status_committed=True", final_path)

    # Send email notification to user
    try:
        user = session.get(User, episode.user_id)
        if user and user.email:
            episode_title = episode.title or "Untitled Episode"
            subject = "Your episode is ready! 🎉"
            
            # Generate magic link token for auto-login (24 hour expiry)
            from api.routers.auth.utils import create_access_token
            from datetime import timedelta
            magic_token = create_access_token(
                {"sub": user.email, "type": "magic_link"},
                expires_delta=timedelta(hours=24)
            )
            
            base_url = "https://app.podcastplusplus.com"
            episodes_url = f"{base_url}/dashboard?tab=episodes&token={magic_token}"
            dashboard_url = f"{base_url}/dashboard?token={magic_token}"
            
            # Plain text version
            body = (
                f"🎉🎊🎈 Congratulations! Your episode '{episode_title}' has finished processing! 🎈🎊🎉\n\n"
                f"Click here to see your newest and latest episodes:\n"
                f"{episodes_url}\n\n"
                f"Click here to go back to your dashboard to create your next masterpiece:\n"
                f"{dashboard_url}\n"
            )
            
            # HTML version with better formatting
            html_body = (
                f"<html><body style=\"font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;\">"
                f"<div style=\"text-align: center; margin-bottom: 30px;\">"
                f"<img src=\"{base_url}/MikeCzech.png\" alt=\"Podcast Plus Plus\" style=\"width: 80px; height: 80px; border-radius: 50%; object-fit: cover; margin-bottom: 20px;\" />"
                f"</div>"
                f"<h2 style=\"color: #2C3E50; text-align: center;\">🎉🎊🎈 Congratulations! Your episode '{episode_title}' has finished processing! 🎈🎊🎉</h2>"
                f"<p style=\"margin: 20px 0; text-align: center;\">"
                f"Your episode has been assembled with all your intro, outro, and music."
                f"</p>"
                f"<div style=\"margin: 30px 0;\">"
                f"<p style=\"font-weight: bold; margin-bottom: 10px;\">Next steps:</p>"
                f"<ol style=\"margin-left: 20px; padding-left: 10px;\">"
                f"<li style=\"margin-bottom: 8px;\">Preview the final audio to make sure it sounds perfect</li>"
                f"<li style=\"margin-bottom: 8px;\">Add episode details (title, description, show notes)</li>"
                f"<li style=\"margin-bottom: 8px;\">Publish to your podcast feed</li>"
                f"</ol>"
                f"</div>"
                f"<p style=\"margin: 20px 0; text-align: center;\">"
                f"Go to your dashboard to review and publish:"
                f"</p>"
                f"<p style=\"margin: 20px 0; text-align: center;\">"
                f"<a href=\"{episodes_url}\" style=\"display: inline-block; background-color: #2C3E50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; font-weight: bold; margin: 5px;\">"
                f"View Episodes</a>"
                f"<a href=\"{dashboard_url}\" style=\"display: inline-block; background-color: #2C3E50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; font-weight: bold; margin: 5px;\">"
                f"Go to Dashboard</a></p>"
                f"</body></html>"
            )
            
            try:
                sent = mailer.send(user.email, subject, body, html=html_body)
                if sent:
                    logging.info("[assemble] Email notification sent to %s for episode %s", user.email, episode.id)
                else:
                    logging.warning("[assemble] Email notification failed for %s", user.email)
            except Exception as mail_err:
                logging.warning("[assemble] Failed to send email notification: %s", mail_err, exc_info=True)
    except Exception as user_err:
        logging.warning("[assemble] Failed to fetch user for email notification: %s", user_err, exc_info=True)

    # Create in-app notification
    try:
        note = Notification(
            user_id=episode.user_id,
            type="assembly",
            title="Episode assembled",
            body=f"{episode.title}",
        )
        session.add(note)
        if not _commit_with_retry(session):
            logging.warning("[assemble] Failed to create notification after retries")
    except Exception:
        logging.warning("[assemble] Failed to create notification", exc_info=True)

    _persist_stream_log(episode, log_data)
    _cleanup_main_content(
        session=session, episode=episode, main_content_filename=main_content_filename
    )

    return {"message": "Episode assembled successfully!", "episode_id": episode.id}


def orchestrate_create_podcast_episode(
    *,
    episode_id: str,
    template_id: str,
    main_content_filename: str,
    output_filename: str,
    tts_values: dict,
    episode_details: dict,
    user_id: str,
    podcast_id: str,
    intents: dict | None = None,
    skip_charge: bool = False,
    use_auphonic: bool = False,
    force_auphonic: bool | None = None,
):
    logging.info("[assemble] CWD = %s", os.getcwd())
    cleanup_targets: list[Path] = []

    # Use dedicated session with proper context management and connection cleanup
    with session_scope() as session:
        # Load required entities up front; fail fast if any are missing
        try:
            episode_obj = crud.get_episode_by_id(session, UUID(episode_id))
            user_obj = crud.get_user_by_id(session, UUID(user_id))
            podcast_obj = crud.get_podcast_by_id(session, UUID(podcast_id))
        except Exception as lookup_err:
            logging.critical("[assemble] Failed to load core entities: %s", lookup_err, exc_info=True)
            raise

        if not episode_obj or not user_obj or not podcast_obj:
            missing_parts = []
            if not episode_obj:
                missing_parts.append("episode")
            if not user_obj:
                missing_parts.append("user")
            if not podcast_obj:
                missing_parts.append("podcast")

            logging.critical("[assemble] Missing required entities: %s", ",".join(missing_parts))

            try:
                not_found_status = getattr(EpisodeStatus, "not_found", None) or getattr(EpisodeStatus, "error", None) or "not_found"
                if episode_obj:
                    episode_obj.status = not_found_status  # type: ignore[assignment]
                    session.add(episode_obj)
                    _commit_with_retry(session)
            except Exception as not_found_err:
                logging.error("[assemble] Unable to persist not_found status: %s", not_found_err, exc_info=True)
                session.rollback()

            raise RuntimeError("Required entities missing for assembly")

        try:
            if force_auphonic is not None:
                final_use_auphonic = bool(force_auphonic)
                logging.info("[assemble] AQG resume path: force_auphonic=%s", final_use_auphonic)
            else:
                decision_result = asyncio.run(
                    _handle_audio_decision(
                        session=session,
                        episode=episode_obj,
                        main_content_filename=main_content_filename,
                        user=user_obj,
                    )
                )

                if decision_result.get("status") == "paused":
                    return decision_result

                final_use_auphonic = bool(decision_result.get("use_auphonic", False))

            media_context, words_json_path, early_result = media.resolve_media_context(
                session=session,
                episode_id=episode_id,
                template_id=template_id,
                main_content_filename=main_content_filename,
                output_filename=output_filename,
                episode_details=episode_details,
                user_id=user_id,
            )

            if early_result:
                return early_result

            assert media_context is not None  # for type checkers

            # ========== TRANSCRIPTION PIPELINE ==========
            transcribed_words_path: Path | None = None
            transcription_callable = None

            if callable(transcribe_episode):
                transcription_callable = transcribe_episode
            elif hasattr(transcript, "transcribe_episode") and callable(getattr(transcript, "transcribe_episode")):
                transcription_callable = getattr(transcript, "transcribe_episode")  # type: ignore[attr-defined]

            if transcription_callable:
                try:
                    transcribe_result = transcription_callable(
                        session=session,
                        episode=episode_obj,
                        user=user_obj,
                        podcast=podcast_obj,
                        media_context=media_context,
                        main_content_filename=main_content_filename,
                        output_filename=output_filename,
                        tts_values=tts_values,
                        episode_details=episode_details,
                    )

                    # Support async-ish return objects with `.wait()`
                    if hasattr(transcribe_result, "wait"):
                        transcribe_result = transcribe_result.wait()

                    # Normalize return value to a path
                    if isinstance(transcribe_result, dict):
                        candidate = transcribe_result.get("words_json_path") or transcribe_result.get("path")
                        if candidate:
                            transcribed_words_path = Path(candidate)
                    elif isinstance(transcribe_result, (str, Path)):
                        transcribed_words_path = Path(transcribe_result)

                    if transcribed_words_path:
                        logging.info("[assemble] ✅ Transcription completed at %s", transcribed_words_path)
                        words_json_path = str(transcribed_words_path)
                    else:
                        logging.warning("[assemble] ⚠️ Transcription returned no words_json_path; proceeding with media-resolved value")
                except Exception as transcribe_err:
                    logging.error("[assemble] ❌ Transcription failed: %s", transcribe_err, exc_info=True)
                    raise
            else:
                logging.info("[assemble] ℹ️ No transcribe_episode hook available; using media-resolved transcript context")

            # Placeholder for heavy audio processing service hook (now transcription-aware)
            final_mixed_path = None
            processing_service = None
            try:
                from api.services import audio_process_and_assemble_episode as audio_pipeline_service  # type: ignore
                processing_service = audio_pipeline_service
            except Exception:
                processing_service = getattr(audio_processor, "audio_process_and_assemble_episode", None)

            if callable(processing_service):
                try:
                    final_mixed_path = processing_service(
                        session=session,
                        episode=episode_obj,
                        user=user_obj,
                        podcast=podcast_obj,
                        main_content_filename=main_content_filename,
                        output_filename=output_filename,
                        tts_values=tts_values,
                        episode_details=episode_details,
                        words_json_path=str(transcribed_words_path or words_json_path or ""),
                    )
                    if final_mixed_path:
                        cleanup_targets.append(Path(str(final_mixed_path)))
                    logging.info("[assemble] audio_process_and_assemble_episode returned: %s", final_mixed_path)
                except Exception as svc_err:
                    logging.error("[assemble] audio_process_and_assemble_episode failed: %s", svc_err, exc_info=True)
                    raise

            # ========== DETERMINE ADVANCED AUDIO STATE ==========
            advanced_audio_requested = bool(final_use_auphonic)
            auphonic_processed = False
            
            if advanced_audio_requested:
                logging.info("[assemble] ✅ Advanced audio requested via toggle; verifying processed assets")
                try:
                    from api.models.podcast import MediaItem, MediaCategory
                    from sqlmodel import select
                    
                    filename_search = main_content_filename.split("/")[-1]
                    media_item = session.exec(
                        select(MediaItem)
                        .where(MediaItem.user_id == user_id)
                        .where(MediaItem.category == MediaCategory.main_content)
                        .where(MediaItem.filename.contains(filename_search))
                        .order_by(MediaItem.created_at.desc())
                    ).first()
                    
                    if media_item and media_item.auphonic_processed:
                        auphonic_processed = True
                        logging.info("[assemble] ✅ Advanced audio assets detected via MediaItem %s", media_item.id)
                    else:
                        logging.warning(
                            "[assemble] ⚠️ Advanced audio was requested but no processed MediaItem was found for '%s'",
                            filename_search,
                        )
                except Exception as e:
                    logging.error("[assemble] Failed advanced audio pre-check: %s", e, exc_info=True)
            else:
                logging.info("[assemble] Advanced audio disabled for this episode")

            transcript_context = transcript.prepare_transcript_context(
                session=session,
                media_context=media_context,
                words_json_path=Path(words_json_path) if words_json_path else None,
                main_content_filename=main_content_filename,
                output_filename=output_filename,
                tts_values=tts_values,
                user_id=user_id,
                intents=intents,
                auphonic_processed=auphonic_processed,  # Pass flag to skip processing
            )

            # Pre-upload final audio if available from assembly service
            final_upload_url = None
            if final_mixed_path:
                try:
                    gcs_bucket = os.getenv("GCS_BUCKET") or os.getenv("MEDIA_BUCKET") or os.getenv("TRANSCRIPTS_BUCKET")
                    if not gcs_bucket:
                        raise RuntimeError("No storage bucket configured for final upload")
                    final_basename = Path(final_mixed_path).name
                    gcs_key = f"{user_id}/episodes/{episode_id}/audio/{final_basename}"
                    with open(final_mixed_path, "rb") as f:
                        final_upload_url = storage.upload_file(gcs_bucket, gcs_key, f, content_type="audio/mpeg")  # type: ignore[attr-defined]
                    episode_obj.gcs_audio_path = final_upload_url
                    logging.info("[assemble] ✅ Uploaded final audio to storage: %s", final_upload_url)
                except Exception as upload_err:
                    logging.error("[assemble] ❌ Final upload failed: %s", upload_err, exc_info=True)
                    raise
            else:
                logging.warning("[assemble] ⚠️ No final_mixed_path returned; skipping pre-finalize upload")

            result = _finalize_episode(
                session=session,
                media_context=media_context,
                transcript_context=transcript_context,
                main_content_filename=main_content_filename,
                output_filename=output_filename,
                tts_values=tts_values,
                use_auphonic=advanced_audio_requested,
            )

            # Ensure final URL persists if _finalize skipped upload
            if final_upload_url and not getattr(episode_obj, "gcs_audio_path", None):
                episode_obj.gcs_audio_path = final_upload_url

            try:
                episode_obj.status = EpisodeStatus.completed  # type: ignore[attr-defined]
            except Exception:
                episode_obj.status = "completed"  # type: ignore[assignment]

            # Send final notification (optional service hook)
            try:
                from api.services import notification as notification_service  # type: ignore

                if hasattr(notification_service, "create_final_notification"):
                    notification_service.create_final_notification(user_id=user_id, episode_id=episode_id)
                else:
                    note = Notification(
                        user_id=user_id,
                        type="assembly",
                        title="Episode ready",
                        body=f"Your episode {episode_obj.title or episode_id} is ready.",
                    )
                    session.add(note)
                    _commit_with_retry(session)
            except Exception:
                logging.warning("[assemble] Failed to emit final notification", exc_info=True)

            return result
        except Exception as exc:
            session.rollback()
            try:
                episode_obj.status = EpisodeStatus.failed  # type: ignore[attr-defined]
                session.add(episode_obj)
            except Exception:
                logging.error("[assemble] Failed to set failure status on episode %s", episode_id, exc_info=True)

            logging.error(
                "Episode assembly failed for %s: %s", episode_id, exc, exc_info=True
            )

            try:
                from api.services import notification

                if hasattr(notification, "send_episode_failure_alert"):
                    notification.send_episode_failure_alert(episode_id, user_id, str(exc))
            except Exception as notify_err:
                logging.warning(
                    "[assemble] Failed to send failure notification: %s", notify_err, exc_info=True
                )

            raise
        finally:
            try:
                if episode_obj:
                    session.add(episode_obj)
                    session.commit()
            except Exception as commit_err:
                logging.error(
                    "[assemble] Failed to commit final status for episode %s: %s",
                    episode_id,
                    commit_err,
                    exc_info=True,
                )
                session.rollback()

            # Cleanup any temporary artifacts registered during processing
            try:
                for candidate in cleanup_targets:
                    if candidate and candidate.exists():
                        candidate.unlink(missing_ok=True)
            except Exception as cleanup_err:
                logging.warning("[assemble] Cleanup encountered issues: %s", cleanup_err, exc_info=True)


def orchestrate_resume_episode_assembly(
    *,
    episode_id: str,
    user_choice_is_advanced: bool,
    original_params: dict,
):
    episode_podcast_id = None

    with session_scope() as session:
        episode_obj = None
        try:
            episode_obj = session.get(Episode, UUID(episode_id))
        except Exception:
            episode_obj = session.get(Episode, episode_id)

        if not episode_obj:
            raise RuntimeError("Episode not found for resume")

        episode_user_id = getattr(episode_obj, "user_id", None)
        episode_podcast_id = getattr(episode_obj, "podcast_id", None)

        status_value = getattr(episode_obj, "status", None)
        expected_status = getattr(EpisodeStatus, "awaiting_audio_decision", "awaiting_audio_decision")
        if status_value not in {expected_status, str(expected_status)}:
            raise RuntimeError("Episode is not awaiting audio decision")

        try:
            episode_obj.status = EpisodeStatus.processing  # type: ignore[attr-defined]
        except Exception:
            episode_obj.status = "processing"  # type: ignore[assignment]

        session.add(episode_obj)
        if not _commit_with_retry(session):
            raise RuntimeError("Failed to mark episode as processing before resume")

    resume_params = dict(original_params or {})
    resume_params.pop("force_auphonic", None)

    resume_params.setdefault("episode_id", episode_id)
    resume_params.setdefault("template_id", "")
    resume_params.setdefault("main_content_filename", "")
    resume_params.setdefault("output_filename", "")
    resume_params.setdefault("tts_values", {})
    resume_params.setdefault("episode_details", {})
    resume_params.setdefault("user_id", episode_user_id or resume_params.get("user_id") or "")
    resume_params.setdefault("podcast_id", episode_podcast_id or "")
    resume_params.setdefault("intents", None)
    resume_params.setdefault("skip_charge", False)
    resume_params.setdefault("use_auphonic", resume_params.get("use_auphonic", False))

    logging.info("[assemble] Resuming episode %s with user choice advanced=%s", episode_id, user_choice_is_advanced)

    return orchestrate_create_podcast_episode(
        force_auphonic=bool(user_choice_is_advanced),
        **resume_params,
    )