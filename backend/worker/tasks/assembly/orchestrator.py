"""Final orchestration for episode assembly."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from uuid import UUID

from sqlmodel import select

from api.core.database import get_session
from api.models.notification import Notification
from api.models.podcast import MediaCategory, MediaItem
from api.models.user import User
# Import the audio package and alias it to the expected name. The orchestrator
# calls audio_processor.process_and_assemble_episode(...), and api.services.audio
# re-exports process_and_assemble_episode from its __init__.py.
from api.services import audio as audio_processor
from api.services.mailer import mailer
from api.core.paths import WS_ROOT as PROJECT_ROOT, FINAL_DIR, MEDIA_DIR
from infrastructure import storage
from infrastructure.tasks_client import enqueue_http_task

from . import billing, media, transcript
from .transcript import _commit_with_retry


ASSEMBLY_LOG_DIR = PROJECT_ROOT / "assembly_logs"
ASSEMBLY_LOG_DIR.mkdir(exist_ok=True)


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
):
    episode = media_context.episode
    stream_log_path = str(ASSEMBLY_LOG_DIR / f"{episode.id}.log")
    
    # ========== CHECK IF AUDIO WAS AUPHONIC-PROCESSED DURING UPLOAD ==========
    # For Pro tier users, audio is processed by Auphonic DURING UPLOAD (not assembly)
    # We need to check if the MediaItem has auphonic_processed=True and use cleaned audio
    auphonic_processed = False
    use_auphonic = False  # For backward compatibility with existing code
    auphonic_cleaned_audio_path = None
    auphonic_processed_path = None  # For backward compatibility
    
    try:
        from api.models.podcast import MediaItem, MediaCategory
        from sqlmodel import select
        
        # Find MediaItem for this episode's main content
        # CRITICAL: Use main_content_filename (original upload), NOT episode.working_audio_name (cleaned)
        # working_audio_name gets updated to "cleaned_*.mp3" but MediaItem.filename is original upload
        filename_search = main_content_filename.split("/")[-1]
        
        logging.info("[assemble] 🔍 Searching for MediaItem: user=%s, filename_contains='%s'", episode.user_id, filename_search)
        
        # Try to find by filename match
        media_item = session.exec(
            select(MediaItem)
            .where(MediaItem.user_id == episode.user_id)
            .where(MediaItem.category == MediaCategory.main_content)
            .where(MediaItem.filename.contains(filename_search))
            .order_by(MediaItem.created_at.desc())
        ).first()
        
        if media_item:
            logging.info(
                "[assemble] 🔍 Found MediaItem id=%s, filename='%s', auphonic_processed=%s",
                media_item.id,
                media_item.filename,
                media_item.auphonic_processed
            )
        else:
            logging.warning("[assemble] ⚠️ No MediaItem found for filename search '%s'", filename_search)
        
        if media_item and media_item.auphonic_processed:
            auphonic_processed = True
            use_auphonic = True  # Set for backward compatibility
            logging.info(
                "[assemble] ✅ Audio was Auphonic-processed during upload (MediaItem %s)",
                media_item.id
            )
            
            # Use cleaned audio URL if available
            if media_item.auphonic_cleaned_audio_url:
                # Download cleaned audio from GCS
                gcs_url = media_item.auphonic_cleaned_audio_url
                if gcs_url.startswith("gs://"):
                    from pathlib import Path as PathLib
                    # tempfile already imported at module level
                    
                    # Download to temp location
                    temp_dir = PathLib(tempfile.gettempdir()) / f"auphonic_{episode.id}"
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    
                    temp_audio_path = temp_dir / f"auphonic_cleaned_{episode.id}.mp3"
                    
                    try:
                        parts = gcs_url[5:].split("/", 1)
                        bucket_name = parts[0]
                        key = parts[1] if len(parts) > 1 else ""
                        
                        file_bytes = storage.download_bytes(bucket_name, key)
                        temp_audio_path.write_bytes(file_bytes)
                        
                        auphonic_cleaned_audio_path = temp_audio_path
                        auphonic_processed_path = temp_audio_path  # For backward compatibility
                        main_content_filename = str(temp_audio_path)
                        
                        logging.info(
                            "[assemble] Downloaded Auphonic cleaned audio: %s (%d bytes)",
                            temp_audio_path,
                            len(file_bytes)
                        )
                    except Exception as e:
                        logging.error("[assemble] Failed to download Auphonic cleaned audio: %s", e)
                        auphonic_processed = False
            
            # Load Auphonic metadata (show notes, chapters)
            if media_item.auphonic_metadata:
                try:
                    import json
                    auphonic_meta = json.loads(media_item.auphonic_metadata)
                    logging.info("[assemble] ✅ Auphonic metadata available: %s", list(auphonic_meta.keys()))
                    
                    # Save AI-generated metadata to Episode
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
                    logging.warning("[assemble] Failed to parse Auphonic metadata: %s", e)
        else:
            logging.info("[assemble] Audio not Auphonic-processed, using standard pipeline")
    
    except Exception as e:
        logging.error("[assemble] Failed to check Auphonic processing status: %s", e, exc_info=True)
        auphonic_processed = False
    
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
        audio_name = episode.working_audio_name or main_content_filename
        main_audio_path = MEDIA_DIR / audio_name if not PathLib(audio_name).is_absolute() else PathLib(audio_name)
        
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
                chunk_payload = {
                    "episode_id": str(episode.id),
                    "chunk_id": chunk.chunk_id,
                    "chunk_index": chunk.index,
                    "total_chunks": len(chunks),  # Used to detect last chunk for trailing silence trim
                    "gcs_audio_uri": chunk.gcs_audio_uri,
                    "gcs_transcript_uri": chunk.gcs_transcript_uri,
                    "cleanup_options": cleanup_options,
                    "user_id": str(media_context.user_id),
                }
                
                try:
                    task_info = enqueue_http_task("/api/tasks/process-chunk", chunk_payload)
                    logging.info("[assemble] Dispatched chunk %d task: %s", chunk.index, task_info)
                except Exception as e:
                    logging.error("[assemble] Failed to dispatch chunk %d: %s", chunk.index, e)
                    # Mark chunk as failed
                    chunk.status = "failed"
            
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
    # Priority: Auphonic processed > chunked reassembled > original
    if use_auphonic and auphonic_processed_path:
        audio_input_path = str(auphonic_processed_path)
    elif use_chunking:
        audio_input_path = main_content_filename  # This is the reassembled path
    else:
        audio_input_path = episode.working_audio_name or main_content_filename
    
    # Prepare cleanup options - respect existing cleanup_opts from Auphonic if set
    # Otherwise, skip all cleaning if chunking was used, or use normal options
    if use_auphonic:
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
        logging.info("[assemble] Starting audio processor with audio_input_path=%s, mix_only=True", audio_input_path)
        
        final_path, log_data, ai_note_additions = audio_processor.process_and_assemble_episode(
            template=media_context.template,
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
        logging.error("[assemble] audio_input_path=%s, use_auphonic=%s, use_chunking=%s", 
                     audio_input_path, use_auphonic, use_chunking)
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
        
        # Get audio duration in minutes (convert from milliseconds)
        audio_duration_minutes = (episode.duration_ms / 1000 / 60) if episode.duration_ms else 0
        
        # Determine if Auphonic was used (costs more)
        use_auphonic_flag = bool(auphonic_processed)
        
        # Charge credits for assembly
        logging.info(
            "[assemble] 💳 Charging credits: episode_id=%s, duration=%.2f minutes, auphonic=%s",
            episode.id,
            audio_duration_minutes,
            use_auphonic_flag
        )
        
        ledger_entry, cost_breakdown = credits.charge_for_assembly(
            session=session,
            user=session.get(User, episode.user_id),
            episode_id=episode.id,
            total_duration_minutes=audio_duration_minutes,
            use_auphonic=use_auphonic_flag,
            correlation_id=f"assembly_{episode.id}",
        )
        
        logging.info(
            "[assemble] ✅ Credits charged: %.2f credits (base=%.2f, pipeline=%s, multiplier=%.2fx)",
            cost_breakdown['total_credits'],
            cost_breakdown['base_cost'],
            cost_breakdown['pipeline'],
            cost_breakdown['multiplier']
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
    
    # Upload to cloud storage (GCS or R2) - if this fails, the entire assembly fails
    gcs_audio_key = f"{user_id}/episodes/{episode_id}/audio/{final_basename}"
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
            episode.cover_path = cover_str
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
                
                # Upload cover to GCS (REQUIRED - ephemeral storage cannot rely on local files)
                user_id = str(episode.user_id)
                episode_id = str(episode.id)
                gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
                gcs_cover_key = f"{user_id}/episodes/{episode_id}/cover/{cover_name}"
                
                with open(cover_path, "rb") as f:
                    cover_ext = cover_name.lower().split(".")[-1]
                    content_type = f"image/{cover_ext}" if cover_ext in ("jpg", "jpeg", "png", "gif") else "image/jpeg"
                    gcs_cover_url = storage.upload_fileobj(gcs_bucket, gcs_cover_key, f, content_type=content_type)  # type: ignore[attr-defined]
                
                # Validate URL format (GCS: gs://, R2: https://)
                cover_url_str = str(gcs_cover_url) if gcs_cover_url else ""
                if not cover_url_str or not (cover_url_str.startswith("gs://") or cover_url_str.startswith("https://")):
                    raise RuntimeError(f"[assemble] CRITICAL: Cover cloud storage upload failed - returned invalid URL: {gcs_cover_url}")
                
                episode.gcs_cover_path = gcs_cover_url
                logging.info("[assemble] ✅ Cover uploaded to cloud storage: %s", gcs_cover_url)
                
                # Mirror to local media directory for dev environment playback
                try:
                    local_cover_mirror = MEDIA_DIR / gcs_cover_key
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

    # CRITICAL: This commit marks episode as "processed" - MUST succeed or episode stuck forever
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
    
    logging.info("[assemble] done. final=%s status_committed=True", final_path)

    # Send email notification to user
    try:
        user = session.get(User, episode.user_id)
        if user and user.email:
            episode_title = episode.title or "Untitled Episode"
            subject = "Your episode is ready to publish!"
            body = (
                f"Great news! Your episode '{episode_title}' has finished processing and is ready to publish.\n\n"
                f"🎧 Your episode has been assembled with all your intro, outro, and music.\n\n"
                f"Next steps:\n"
                f"1. Preview the final audio to make sure it sounds perfect\n"
                f"2. Add episode details (title, description, show notes)\n"
                f"3. Publish to your podcast feed\n\n"
                f"Go to your dashboard to review and publish:\n"
                f"https://app.podcastplusplus.com/dashboard\n\n"
                f"Happy podcasting!"
            )
            try:
                sent = mailer.send(user.email, subject, body)
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
):
    logging.info("[assemble] CWD = %s", os.getcwd())
    
    # Use dedicated session with proper context management and connection cleanup
    # This prevents connection pool corruption during long-running assembly tasks
    from api.core.database import session_scope
    
    with session_scope() as session:
        try:
            billing.debit_usage_at_start(
                session=session,
                user_id=user_id,
                episode_id=episode_id,
                main_content_filename=main_content_filename,
                skip_charge=skip_charge,
            )

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

            # ========== DETERMINE AUPHONIC USAGE ==========
            # Priority:
            # 1. User's explicit toggle (use_auphonic parameter from frontend)
            # 2. Fallback to checking if audio was already Auphonic-processed during upload
            
            # Start with user's explicit choice
            auphonic_processed = use_auphonic
            
            # If user didn't explicitly request Auphonic, check if it was processed during upload
            if not auphonic_processed:
                try:
                    from api.models.podcast import MediaItem, MediaCategory
                    from sqlmodel import select
                    
                    # Use main_content_filename (original upload), NOT episode.working_audio_name (cleaned)
                    filename_search = main_content_filename.split("/")[-1]
                    
                    logging.info("[assemble] 🔍 PRE-CHECK: Searching for MediaItem: user=%s, filename='%s'", user_id, filename_search)
                    
                    media_item = session.exec(
                        select(MediaItem)
                        .where(MediaItem.user_id == user_id)
                        .where(MediaItem.category == MediaCategory.main_content)
                        .where(MediaItem.filename.contains(filename_search))
                        .order_by(MediaItem.created_at.desc())
                    ).first()
                    
                    if media_item:
                        logging.info(
                            "[assemble] 🔍 PRE-CHECK: Found MediaItem id=%s, auphonic_processed=%s",
                            media_item.id,
                            media_item.auphonic_processed
                        )
                        if media_item.auphonic_processed:
                            auphonic_processed = True
                            logging.info("[assemble] ⚠️ Auphonic-processed audio detected - will skip redundant processing")
                    else:
                        logging.info("[assemble] 🔍 PRE-CHECK: No MediaItem found")
                except Exception as e:
                    logging.error("[assemble] Failed Auphonic pre-check: %s", e, exc_info=True)
            else:
                logging.info("[assemble] ✅ User explicitly requested Auphonic processing via toggle")

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

            return _finalize_episode(
                session=session,
                media_context=media_context,
                transcript_context=transcript_context,
                main_content_filename=main_content_filename,
                output_filename=output_filename,
                tts_values=tts_values,
            )
        except Exception as exc:
            logging.exception(
                "Error during episode assembly for %s: %s", output_filename, exc
            )
            try:
                from api.core import crud

                episode = crud.get_episode_by_id(session, UUID(episode_id))
                if episode:
                    try:
                        from api.models.podcast import EpisodeStatus as EpStatus

                        episode.status = EpStatus.error  # type: ignore[attr-defined]
                    except Exception:
                        episode.status = "error"  # type: ignore[assignment]
                    session.add(episode)
                    if not _commit_with_retry(session):
                        logging.error("[orchestrate] Failed to commit error status in exception handler")
            except Exception:
                pass
            raise

