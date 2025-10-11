"""Final orchestration for episode assembly."""

from __future__ import annotations

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
# Import the audio package and alias it to the expected name. The orchestrator
# calls audio_processor.process_and_assemble_episode(...), and api.services.audio
# re-exports process_and_assemble_episode from its __init__.py.
from api.services import audio as audio_processor
from api.core.paths import WS_ROOT as PROJECT_ROOT, FINAL_DIR, MEDIA_DIR
from infrastructure import gcs
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
            return

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

        query = select(MediaItem).where(
            MediaItem.user_id == episode.user_id,
            MediaItem.category == MediaCategory.main_content,
        )
        media_item = None
        for item in session.exec(query).all():
            stored = str(getattr(item, "filename", "") or "").strip()
            if not stored:
                continue
            if stored in candidates:
                media_item = item
                break
            # Fallback: match when either value endswith the other to support
            # cases like gs://bucket/path/<name> vs <name>.
            for candidate in candidates:
                if stored.endswith(candidate) or candidate.endswith(stored):
                    media_item = item
                    break
            if media_item:
                break
        if not media_item or media_item.category != MediaCategory.main_content:
            return

        filename = str(media_item.filename or "").strip()
        removed_file = False

        if filename.startswith("gs://"):
            try:
                without_scheme = filename[len("gs://") :]
                bucket_name, key = without_scheme.split("/", 1)
                if bucket_name and key:
                    from google.cloud import storage  # type: ignore

                    client = storage.Client()
                    client.bucket(bucket_name).blob(key).delete()
                    removed_file = True
            except Exception:
                logging.warning(
                    "[cleanup] Failed to delete gs object %s", filename, exc_info=True
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

        try:
            session.delete(media_item)
            if not _commit_with_retry(session):
                logging.warning("[cleanup] Failed to delete media_item after retries")
        except Exception:
            session.rollback()
            raise

        logging.info(
            "[cleanup] Removed main content source %s after assembly (file_removed=%s)",
            media_item.filename,
            removed_file,
        )
    except Exception:
        logging.warning("[cleanup] Failed to remove main content media item", exc_info=True)


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

    # NEW: Check if we should use chunked processing for long files
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
            max_wait_seconds = 900  # 15 minutes
            poll_interval = 5  # 5 seconds
            start_time = time.time()
            
            logging.info("[assemble] Waiting for %d chunks to complete...", len(chunks))
            
            while time.time() - start_time < max_wait_seconds:
                # Check if all chunks have cleaned URIs in GCS
                import infrastructure.gcs as gcs
                
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
                            bucket_name, blob_path = parts
                            exists = gcs.blob_exists(bucket_name, blob_path)
                            
                            if exists:
                                chunk.cleaned_path = f"/tmp/{chunk.chunk_id}_cleaned.mp3"
                                chunk.gcs_cleaned_uri = cleaned_uri
                                chunk.status = "completed"
                            else:
                                all_complete = False
                
                if all_complete:
                    logging.info("[assemble] All %d chunks completed in %.1f seconds",
                               len(chunks), time.time() - start_time)
                    break
                
                time.sleep(poll_interval)
            
            if not all_complete:
                raise RuntimeError(f"Chunk processing timed out after {max_wait_seconds}s")
            
            # Download and reassemble chunks
            logging.info("[assemble] Reassembling %d chunks...", len(chunks))
            
            # Download cleaned chunks
            for chunk in chunks:
                if chunk.gcs_cleaned_uri:
                    gcs_uri = chunk.gcs_cleaned_uri
                    if gcs_uri.startswith("gs://"):
                        parts = gcs_uri[5:].split("/", 1)
                        if len(parts) == 2:
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
    # If chunking was used successfully, use the reassembled file
    # Otherwise, use the original cleaned audio
    if use_chunking:
        audio_input_path = main_content_filename  # This is the reassembled path
    else:
        audio_input_path = episode.working_audio_name or main_content_filename
    
    # Prepare cleanup options - skip all cleaning if chunking was used
    if use_chunking:
        # Audio is already fully cleaned and reassembled - just mix it
        cleanup_opts = {
            **transcript_context.mixer_only_options,
            "internIntent": "skip",  # Skip intern processing
            "flubberIntent": "skip",  # Skip filler removal
            "removePauses": False,  # Skip silence removal
            "removeFillers": False,  # Skip filler word removal
            "internEnabled": False,  # Disable intern feature
        }
    else:
        # Normal cleanup options
        cleanup_opts = {
            **transcript_context.mixer_only_options,
            "internIntent": transcript_context.intern_intent,
            "flubberIntent": transcript_context.flubber_intent,
        }
    
    # Standard audio processing (for short files or chunking fallback)
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

    if not final_path_obj.exists():
        fallback_candidate = FINAL_DIR / final_basename
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

    # Upload final audio to GCS for 7-day retention (survives container restarts)
    try:
        user_id = str(episode.user_id)
        episode_id = str(episode.id)
        gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
        
        # Upload audio file
        audio_src = fallback_candidate if fallback_candidate and fallback_candidate.is_file() else None
        if audio_src:
            # Get audio file size for RSS feed
            try:
                episode.audio_file_size = audio_src.stat().st_size
                logging.info("[assemble] Audio file size: %d bytes", episode.audio_file_size)
            except Exception as size_err:
                logging.warning("[assemble] Could not get audio file size: %s", size_err)
            
            # Get audio duration for RSS feed
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_file(str(audio_src))
                episode.duration_ms = len(audio)
                logging.info("[assemble] Audio duration: %d ms (%.1f minutes)", episode.duration_ms, episode.duration_ms / 1000 / 60)
            except Exception as dur_err:
                logging.warning("[assemble] Could not get audio duration: %s", dur_err)
            
            gcs_audio_key = f"{user_id}/episodes/{episode_id}/audio/{final_basename}"
            with open(audio_src, "rb") as f:
                gcs_audio_url = gcs.upload_fileobj(gcs_bucket, gcs_audio_key, f, content_type="audio/mpeg")  # type: ignore[attr-defined]
            episode.gcs_audio_path = gcs_audio_url
            logging.info("[assemble] Uploaded audio to %s", gcs_audio_url)
    except Exception:
        logging.warning("[assemble] Failed to upload audio to GCS (will rely on local files)", exc_info=True)

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
                
                # Upload cover to GCS for 7-day retention
                try:
                    user_id = str(episode.user_id)
                    episode_id = str(episode.id)
                    gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
                    gcs_cover_key = f"{user_id}/episodes/{episode_id}/cover/{cover_name}"
                    
                    with open(cover_path, "rb") as f:
                        cover_ext = cover_name.lower().split(".")[-1]
                        content_type = f"image/{cover_ext}" if cover_ext in ("jpg", "jpeg", "png", "gif") else "image/jpeg"
                        gcs_cover_url = gcs.upload_fileobj(gcs_bucket, gcs_cover_key, f, content_type=content_type)  # type: ignore[attr-defined]
                    episode.gcs_cover_path = gcs_cover_url
                    logging.info("[assemble] Uploaded cover to %s", gcs_cover_url)
                except Exception:
                    logging.warning("[assemble] Failed to upload cover to GCS (will rely on local files)", exc_info=True)
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

            transcript_context = transcript.prepare_transcript_context(
                session=session,
                media_context=media_context,
                words_json_path=Path(words_json_path) if words_json_path else None,
                main_content_filename=main_content_filename,
                output_filename=output_filename,
                tts_values=tts_values,
                user_id=user_id,
                intents=intents,
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

