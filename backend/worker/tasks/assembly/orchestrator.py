"""Final orchestration for episode assembly."""

from __future__ import annotations

import logging
import os
import shutil
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

from . import billing, media, transcript


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
        main_fn = os.path.basename(str(main_content_filename))
        query = select(MediaItem).where(
            MediaItem.filename == main_fn, MediaItem.user_id == episode.user_id
        )
        media_item = session.exec(query).first()
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

            candidates = []
            for root in {MEDIA_DIR, PROJECT_ROOT / "media_uploads", Path("media_uploads")}:
                try:
                    candidates.append((root / base_name).resolve(strict=False))
                except Exception:
                    continue

            seen: set[str] = set()
            for candidate in candidates:
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
            session.commit()
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
        session.commit()
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

    final_path, log_data, ai_note_additions = audio_processor.process_and_assemble_episode(
        template=media_context.template,
        main_content_filename=episode.working_audio_name or main_content_filename,
        output_filename=output_filename,
        cleanup_options={
            **transcript_context.mixer_only_options,
            "internIntent": transcript_context.intern_intent,
            "flubberIntent": transcript_context.flubber_intent,
        },
        tts_overrides=tts_values or {},
        cover_image_path=media_context.cover_image_path,
        elevenlabs_api_key=getattr(media_context.user, "elevenlabs_api_key", None),
        tts_provider=media_context.preferred_tts_provider,
        mix_only=True,
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
            except Exception:
                logging.warning(
                    "[assemble] Failed to persist cover image locally", exc_info=True
                )

    session.add(episode)
    session.commit()
    logging.info("[assemble] done. final=%s", final_path)

    try:
        note = Notification(
            user_id=episode.user_id,
            type="assembly",
            title="Episode assembled",
            body=f"{episode.title}",
        )
        session.add(note)
        session.commit()
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
    session = next(get_session())
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
                session.commit()
        except Exception:
            pass
        raise
    finally:
        session.close()

