"""Final orchestration for episode assembly."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from uuid import UUID

from sqlmodel import select

from api.core.database import get_session
from api.models.notification import Notification
from api.models.podcast import MediaCategory, MediaItem
from api.services import audio_processor
from api.core.paths import WS_ROOT as PROJECT_ROOT

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
        if media_item and media_item.category == MediaCategory.main_content:
            media_path = Path("media_uploads") / media_item.filename
            if media_path.is_file():
                try:
                    media_path.unlink()
                except Exception:
                    logging.warning("[cleanup] Unable to unlink file %s", media_path)
            session.delete(media_item)
            session.commit()
            logging.info(
                "[cleanup] Removed main content source %s after assembly",
                media_item.filename,
            )
    except Exception:
        logging.warning("[cleanup] Failed to remove main content media item", exc_info=True)


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

    episode.final_audio_path = os.path.basename(str(final_path))
    if media_context.cover_image_path and not getattr(episode, "cover_path", None):
        try:
            episode.cover_path = Path(str(media_context.cover_image_path)).name
        except Exception:
            episode.cover_path = Path(media_context.cover_image_path).name

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

