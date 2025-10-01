"""Transcript and cleanup helpers for episode assembly."""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from sqlmodel import select

from api.models.podcast import MediaCategory, MediaItem
from api.services import ai_enhancer, clean_engine, transcription as trans
from api.services.audio.common import sanitize_filename
from api.services.clean_engine.features import apply_flubber_cuts
from api.core.paths import MEDIA_DIR, WS_ROOT as PROJECT_ROOT

from .media import MediaContext, _resolve_media_file


@dataclass
class TranscriptContext:
    words_json_path: Optional[Path]
    cleaned_path: Optional[Path]
    engine_result: Optional[dict]
    mixer_only_options: dict[str, Any]
    flubber_intent: str
    intern_intent: str
    base_audio_name: str


def _snapshot_original_transcript(*, episode, session, words_json_path: Path | None, output_filename: str, base_audio_name: str) -> None:
    if not words_json_path or not words_json_path.is_file():
        return

    tr_dir = PROJECT_ROOT / "transcripts"
    tr_dir.mkdir(parents=True, exist_ok=True)
    try:
        preferred_raw = Path(output_filename).stem if output_filename else None
    except Exception:
        preferred_raw = None
    if not preferred_raw:
        try:
            preferred_raw = Path(base_audio_name).stem
        except Exception:
            preferred_raw = Path(words_json_path).stem
    preferred_stem = sanitize_filename(str(preferred_raw)) if preferred_raw else None
    orig_new = tr_dir / f"{preferred_stem}.original.json"
    orig_legacy = tr_dir / f"{preferred_stem}.original.words.json"
    if (not orig_new.exists()) and (not orig_legacy.exists()):
        try:
            shutil.copyfile(words_json_path, orig_new)
        except Exception:
            logging.warning("[assemble] Failed to snapshot original transcript", exc_info=True)
    try:
        meta = json.loads(getattr(episode, "meta_json", "{}") or "{}") if getattr(episode, "meta_json", None) else {}
        transcripts = meta.get("transcripts") or {}
        transcripts["original"] = (
            orig_new.name if orig_new.exists() else (orig_legacy.name if orig_legacy.exists() else None)
        )
        meta["transcripts"] = transcripts
        episode.meta_json = json.dumps(meta)
        session.add(episode)
        session.commit()
    except Exception:
        session.rollback()


def _load_flubber_cuts(*, episode) -> list[tuple[int, int]] | None:
    try:
        meta = json.loads(getattr(episode, "meta_json", "{}") or "{}")
        if isinstance(meta.get("flubber_cuts_ms"), list):
            cuts = []
            for start, end in meta["flubber_cuts_ms"]:
                if isinstance(start, int) and isinstance(end, int) and end > start:
                    cuts.append((int(start), int(end)))
            return cuts or None
    except Exception:
        return None
    return None


def _maybe_generate_transcript(
    *,
    session,
    episode,
    user_id: str,
    base_audio_name: str,
    output_filename: str,
) -> Optional[Path]:
    target_dir = PROJECT_ROOT / "transcripts"
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        preferred_raw = Path(output_filename).stem if output_filename else None
    except Exception:
        preferred_raw = None
    if not preferred_raw:
        try:
            preferred_raw = Path(base_audio_name).stem
        except Exception:
            preferred_raw = None

    basename = Path(str(base_audio_name)).name
    local_candidate = MEDIA_DIR / basename
    if not local_candidate.exists():
        gcs_uri = None
        try:
            query = select(MediaItem).where(MediaItem.user_id == UUID(user_id)).where(
                MediaItem.category == MediaCategory.main_content
            )
            for item in session.exec(query).all():
                filename = str(getattr(item, "filename", "") or "")
                if filename.startswith("gs://") and filename.rstrip().lower().endswith("/" + basename.lower()):
                    gcs_uri = filename
                    break
        except Exception:
            gcs_uri = None
        if gcs_uri:
            try:
                logging.info(
                    "[assemble] prepping transcript: downloading %s -> %s",
                    gcs_uri,
                    local_candidate,
                )
                download = _resolve_media_file(gcs_uri)
                if download and Path(str(download)).exists():
                    local_candidate = Path(str(download))
            except Exception:
                logging.warning(
                    "[assemble] failed GCS download prior to transcription", exc_info=True
                )

    words_list = None
    try:
        words_list = trans.get_word_timestamps(basename)
    except Exception:
        try:
            gcs_uri = None
            query = select(MediaItem).where(MediaItem.user_id == UUID(user_id)).where(
                MediaItem.category == MediaCategory.main_content
            )
            for item in session.exec(query).all():
                filename = str(getattr(item, "filename", "") or "")
                if filename.startswith("gs://") and filename.rstrip().lower().endswith("/" + basename.lower()):
                    gcs_uri = filename
                    break
            if gcs_uri:
                words_list = trans.transcribe_media_file(gcs_uri)
        except Exception as exc:
            logging.warning(
                "[assemble] transcript fallback failed for %s: %s", basename, exc
            )

    if words_list is None:
        raise RuntimeError("transcription failed: no source media available")

    out_stem = sanitize_filename(f"{preferred_raw or Path(str(basename)).stem}")
    out_path = target_dir / f"{out_stem}.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(words_list, fh)

    if os.getenv("TRANSCRIPTS_LEGACY_MIRROR", "").strip().lower() in {"1", "true", "yes", "on"}:
        try:
            legacy = target_dir / f"{out_stem}.words.json"
            if not legacy.exists():
                shutil.copyfile(out_path, legacy)
        except Exception:
            pass

    logging.info("[assemble] generated words_json via transcription: %s", out_path)
    return out_path


def _build_engine_configs(cleanup_settings: dict):
    us = clean_engine.UserSettings(
        flubber_keyword=str((cleanup_settings or {}).get("flubberKeyword", "flubber") or "flubber"),
        intern_keyword=str((cleanup_settings or {}).get("internKeyword", "intern") or "intern"),
        filler_words=(cleanup_settings or {}).get(
            "fillerWords", ["um", "uh", "like", "you know", "sort of", "kind of"]
        ),
        aggressive_fillers=(cleanup_settings or {}).get("aggressiveFillersList", []),
        filler_phrases=(cleanup_settings or {}).get("fillerPhrases", []),
        strict_filler_removal=bool((cleanup_settings or {}).get("strictFillerRemoval", True)),
    )
    ss = clean_engine.SilenceSettings(
        detect_threshold_dbfs=int((cleanup_settings or {}).get("silenceThreshDb", -40)),
        min_silence_ms=int(float((cleanup_settings or {}).get("maxPauseSeconds", 1.5)) * 1000),
        target_silence_ms=int(float((cleanup_settings or {}).get("targetPauseSeconds", 0.5)) * 1000),
        edge_keep_ratio=float((cleanup_settings or {}).get("pauseEdgeKeepRatio", 0.5)),
        max_removal_pct=float((cleanup_settings or {}).get("maxPauseRemovalPct", 0.9)),
    )
    ins = clean_engine.InternSettings(
        min_break_s=float((cleanup_settings or {}).get("internMinBreak", 2.0)),
        max_break_s=float((cleanup_settings or {}).get("internMaxBreak", 3.0)),
        scan_window_s=float((cleanup_settings or {}).get("internScanWindow", 12.0)),
    )
    raw_beep = (cleanup_settings or {}).get("censorBeepFile")
    if raw_beep is not None and not isinstance(raw_beep, (str, Path)):
        raw_beep = str(raw_beep)
    censor_cfg = clean_engine.CensorSettings(
        enabled=bool((cleanup_settings or {}).get("censorEnabled", False)),
        words=list((cleanup_settings or {}).get("censorWords", ["fuck", "shit"]))
        if isinstance((cleanup_settings or {}).get("censorWords", None), list)
        else ["fuck", "shit"],
        fuzzy=bool((cleanup_settings or {}).get("censorFuzzy", True)),
        match_threshold=float((cleanup_settings or {}).get("censorMatchThreshold", 0.8)),
        beep_ms=int((cleanup_settings or {}).get("censorBeepMs", 250)),
        beep_freq_hz=int((cleanup_settings or {}).get("censorBeepFreq", 1000)),
        beep_gain_db=float((cleanup_settings or {}).get("censorBeepGainDb", 0.0)),
        beep_file=(
            Path(raw_beep)
            if isinstance(raw_beep, (str, Path)) and str(raw_beep).strip()
            else None
        ),
    )
    try:
        beep_file = getattr(censor_cfg, "beep_file", None)
        if isinstance(beep_file, (str, Path)):
            candidate = Path(str(beep_file))
            if not candidate.is_absolute() and not candidate.exists():
                alt1 = PROJECT_ROOT / "media_uploads" / candidate.name
                alt2 = PROJECT_ROOT / candidate
                if alt1.exists():
                    censor_cfg.beep_file = alt1
                elif alt2.exists():
                    censor_cfg.beep_file = alt2
    except Exception:
        pass
    return us, ss, ins, censor_cfg


def _build_sfx_map(*, session, episode) -> dict[str, Path]:
    try:
        query = select(MediaItem).where(MediaItem.user_id == episode.user_id)
        items = session.exec(query).all()
        mapping = {}
        for item in items:
            key = (item.trigger_keyword or "").strip().lower()
            if key:
                mapping[key] = PROJECT_ROOT / "media_uploads" / item.filename
        return mapping
    except Exception:
        return {}


def prepare_transcript_context(
    *,
    session,
    media_context: MediaContext,
    words_json_path: Optional[Path],
    main_content_filename: str,
    output_filename: str,
    tts_values: dict,
    user_id: str,
    intents: dict | None,
) -> TranscriptContext:
    episode = media_context.episode
    base_audio_name = media_context.base_audio_name
    source_audio_path = media_context.source_audio_path

    _snapshot_original_transcript(
        episode=episode,
        session=session,
        words_json_path=Path(words_json_path) if words_json_path else None,
        output_filename=output_filename,
        base_audio_name=base_audio_name,
    )

    cuts_ms = _load_flubber_cuts(episode=episode)

    if not words_json_path:
        try:
            words_json_path = _maybe_generate_transcript(
                session=session,
                episode=episode,
                user_id=user_id,
                base_audio_name=base_audio_name,
                output_filename=output_filename,
            )
        except Exception as exc:
            logging.warning(
                "[assemble] failed to generate words_json: %s; will skip clean_engine and continue to mixer-only",
                exc,
            )
            words_json_path = None

    us, ss, ins, censor_cfg = _build_engine_configs(media_context.cleanup_settings)
    sfx_map = _build_sfx_map(session=session, episode=episode)

    def _synth(text: str):
        try:
            return ai_enhancer.generate_speech_from_text(
                text,
                voice_id=str((tts_values or {}).get("intern_voice_id") or ""),
                api_key=getattr(media_context.user, "elevenlabs_api_key", None),
                provider=media_context.preferred_tts_provider,
            )
        except Exception:
            from pydub import AudioSegment

            return AudioSegment.silent(duration=800)

    intents = intents or {}
    flubber_intent = str((intents.get("flubber") if isinstance(intents, dict) else "") or "").lower()
    intern_intent = str((intents.get("intern") if isinstance(intents, dict) else "") or "").lower()
    sfx_intent = str((intents.get("sfx") if isinstance(intents, dict) else "") or "").lower()
    censor_intent = str((intents.get("censor") if isinstance(intents, dict) else "") or "").lower()
    logging.info(
        "[assemble] intents: flubber=%s intern=%s sfx=%s censor=%s",
        flubber_intent or "unset",
        intern_intent or "unset",
        sfx_intent or "unset",
        censor_intent or "unset",
    )

    if flubber_intent == "no":
        cuts_ms = None
    if intern_intent == "no":
        try:
            ins = clean_engine.InternSettings(
                min_break_s=ins.min_break_s,
                max_break_s=ins.max_break_s,
                scan_window_s=0.0,
            )
        except Exception:
            pass
    if sfx_intent == "no":
        sfx_map = None
    try:
        if censor_intent == "no":
            setattr(censor_cfg, "enabled", False)
        elif censor_intent == "yes":
            setattr(censor_cfg, "enabled", True)
    except Exception:
        pass

    engine_result = None
    cleaned_path: Optional[Path] = None
    if words_json_path and Path(words_json_path).is_file():
        try:
            stem = Path(base_audio_name).stem
            out_stem = stem if stem.startswith("cleaned_") else f"cleaned_{stem}"
            engine_output = f"{out_stem}.mp3"
        except Exception:
            engine_output = f"cleaned_{Path(base_audio_name).stem}.mp3"
        engine_result = clean_engine.run_all(
            audio_path=source_audio_path,
            words_json_path=words_json_path,
            work_dir=PROJECT_ROOT,
            user_settings=us,
            silence_cfg=ss,
            intern_cfg=ins,
            censor_cfg=censor_cfg,
            sfx_map=sfx_map if sfx_map else None,
            synth=_synth,
            flubber_cuts_ms=cuts_ms,
            output_name=engine_output,
            disable_intern_insertion=True,
        )
        cleaned_path = (
            Path(engine_result.get("final_path"))
            if isinstance(engine_result, dict) and engine_result.get("final_path")
            else None
        )
        try:
            edits = (((engine_result or {}).get("summary", {}) or {}).get("edits", {}) or {})
            spans = edits.get("censor_spans_ms", [])
            mode = edits.get("censor_mode", {})
            logging.info(
                "[assemble] engine censor_enabled=%s spans=%s mode=%s final=%s",
                bool(getattr(censor_cfg, "enabled", False)),
                len(spans),
                mode,
                cleaned_path,
            )
        except Exception:
            pass
    else:
        try:
            logging.warning(
                "[assemble] words.json not found for stems=%s; skipping clean_engine.",
                media_context.base_stems,
            )
            if cuts_ms and isinstance(cuts_ms, list) and len(cuts_ms) > 0:
                src_path = (
                    _resolve_media_file(base_audio_name)
                    or (PROJECT_ROOT / "media_uploads" / Path(str(base_audio_name)).name)
                ).resolve()
                if src_path.is_file():
                    from pydub import AudioSegment

                    audio = AudioSegment.from_file(src_path)
                    precut = apply_flubber_cuts(audio, cuts_ms)
                    out_dir = PROJECT_ROOT / "cleaned_audio"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    precut_name = f"precut_{Path(base_audio_name).stem}.mp3"
                    precut_path = out_dir / precut_name
                    precut.export(precut_path, format="mp3")
                    dest = MEDIA_DIR / precut_path.name
                    try:
                        shutil.copyfile(precut_path, dest)
                    except Exception:
                        logging.warning(
                            "[assemble] Failed to copy precut audio to MEDIA_DIR; mixer may not find it",
                            exc_info=True,
                        )
                    try:
                        episode.working_audio_name = dest.name if dest.exists() else precut_path.name
                        session.add(episode)
                        session.commit()
                    except Exception:
                        session.rollback()
                    base_audio_name = episode.working_audio_name or precut_path.name
                    logging.info(
                        "[assemble] applied %s flubber cuts without words.json; working_audio_name=%s",
                        len(cuts_ms),
                        episode.working_audio_name,
                    )
                else:
                    logging.warning("[assemble] base audio not found for precut: %s", src_path)
        except Exception:
            logging.warning(
                "[assemble] precut stage failed; proceeding with original audio (no flubber cuts)",
                exc_info=True,
            )

    try:
        final_words = None
        if engine_result:
            try:
                final_words = (
                    (engine_result or {}).get("summary", {})
                    .get("edits", {})
                    .get("words_json")
                )
            except Exception:
                final_words = None
        if not final_words and (episode.working_audio_name or "").startswith("precut_"):
            try:
                filename = str(episode.working_audio_name or "")
                if filename:
                    words_list = trans.get_word_timestamps(filename)
                    tr_dir = PROJECT_ROOT / "transcripts"
                    tr_dir.mkdir(parents=True, exist_ok=True)
                    out_path = tr_dir / f"{Path(filename).stem}.json"
                    with open(out_path, "w", encoding="utf-8") as fh:
                        json.dump(words_list, fh)
                    legacy = tr_dir / f"{Path(filename).stem}.words.json"
                    if not legacy.exists():
                        shutil.copyfile(out_path, legacy)
                    final_words = str(out_path)
                    logging.info(
                        "[assemble] generated final transcript for precut audio: %s",
                        out_path,
                    )
            except Exception:
                logging.warning(
                    "[assemble] Failed to generate final transcript for precut audio",
                    exc_info=True,
                )
        if final_words:
            meta = json.loads(getattr(episode, "meta_json", "{}") or "{}") if getattr(episode, "meta_json", None) else {}
            transcripts = meta.get("transcripts") or {}
            transcripts["final"] = os.path.basename(final_words)
            meta["transcripts"] = transcripts
            episode.meta_json = json.dumps(meta)
            session.add(episode)
            session.commit()
    except Exception:
        session.rollback()
        logging.warning(
            "[assemble] Failed final transcript persist block", exc_info=True
        )

    if cleaned_path:
        try:
            src = Path(cleaned_path)
            dest = MEDIA_DIR / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copyfile(src, dest)
                logging.info("[assemble] Copied cleaned audio to MEDIA_DIR: %s", dest)
            except Exception:
                logging.warning(
                    "[assemble] Failed to copy cleaned audio to MEDIA_DIR; mixer may not find it",
                    exc_info=True,
                )

            # Ensure downstream components that expect files under MEDIA_DIR/media_uploads
            # (e.g., the API assembly pipeline) can resolve the cleaned audio. Some
            # environments configure ``MEDIA_DIR`` to a generic writable temp directory
            # while the mixer looks specifically under a ``media_uploads`` child. Mirror
            # the cleaned audio there when needed so lookups succeed regardless of the
            # configured MEDIA_ROOT.
            try:
                uploads_dir = MEDIA_DIR / "media_uploads"
                if MEDIA_DIR.name == "media_uploads":
                    uploads_dir = MEDIA_DIR
                uploads_dir.mkdir(parents=True, exist_ok=True)
                mirror_dest = uploads_dir / src.name
                if dest.exists() and mirror_dest.resolve() != dest.resolve():
                    shutil.copyfile(dest, mirror_dest)
                    logging.info(
                        "[assemble] Mirrored cleaned audio into MEDIA_DIR/media_uploads: %s",
                        mirror_dest,
                    )
            except Exception:
                logging.warning(
                    "[assemble] Failed to mirror cleaned audio into MEDIA_DIR/media_uploads",
                    exc_info=True,
                )

            episode.working_audio_name = dest.name
            session.add(episode)
            session.commit()
        except Exception:
            session.rollback()

    try:
        if source_audio_path and source_audio_path.exists():
            target = MEDIA_DIR / source_audio_path.name
            if not target.exists():
                shutil.copyfile(source_audio_path, target)
                logging.info(
                    "[assemble] mirrored base audio into MEDIA_DIR: %s", target
                )
    except Exception:
        logging.warning(
            "[assemble] Failed to mirror base audio into MEDIA_DIR", exc_info=True
        )

    try:
        raw_settings = getattr(media_context.user, "audio_cleanup_settings_json", None)
        parsed_settings = json.loads(raw_settings) if raw_settings else {}
    except Exception:
        parsed_settings = {}

    user_commands = (parsed_settings or {}).get("commands") or {}
    try:
        defaults = {
            "flubber": {"action": "rollback_restart", "trigger_keyword": "flubber"},
            "intern": {
                "action": "ai_command",
                "trigger_keyword": str((parsed_settings or {}).get("internKeyword") or "intern"),
                "end_markers": ["stop", "stop intern"],
                "remove_end_marker": True,
                "keep_command_token_in_transcript": True,
            },
        }
        if isinstance(user_commands, dict):
            user_commands = {**defaults, **user_commands}
        else:
            user_commands = defaults
    except Exception:
        pass

    user_filler_words = (parsed_settings or {}).get("fillerWords") or []
    mixer_only_opts = {
        "removeFillers": False,
        "removePauses": False,
        "fillerWords": user_filler_words if isinstance(user_filler_words, list) else [],
        "commands": user_commands if isinstance(user_commands, dict) else {},
    }
    try:
        logging.info(
            "[assemble] mix-only commands keys=%s",
            list((mixer_only_opts.get("commands") or {}).keys()),
        )
    except Exception:
        pass

    base_audio_name = episode.working_audio_name or base_audio_name

    if words_json_path and not isinstance(words_json_path, Path):
        words_json_path = Path(str(words_json_path))

    try:
        candidate_stems = []
        try:
            out_stem_raw = Path(output_filename).stem
            candidate_stems.append(out_stem_raw)
            candidate_stems.append(sanitize_filename(out_stem_raw))
        except Exception:
            pass
        try:
            candidate_stems.append(Path(base_audio_name).stem)
        except Exception:
            pass
        try:
            candidate_stems.append(sanitize_filename(Path(base_audio_name).stem))
        except Exception:
            pass
        candidate_stems = [s for s in dict.fromkeys([s for s in candidate_stems if s])]
        words_json_for_mixer = None
        for directory in media_context.search_dirs:
            for stem in candidate_stems:
                candidate = directory / f"{stem}.original.json"
                if candidate.is_file():
                    words_json_for_mixer = candidate
                    break
            if words_json_for_mixer:
                break
        if not words_json_for_mixer:
            if engine_result and engine_result.get("summary", {}).get("edits", {}).get("words_json"):
                candidate = Path(engine_result["summary"]["edits"]["words_json"])
                if candidate.is_file():
                    words_json_for_mixer = candidate
            elif words_json_path and Path(words_json_path).is_file():
                words_json_for_mixer = Path(words_json_path)
        words_json_path = words_json_for_mixer
        logging.info(
            "[assemble] mixer words selected: %s",
            str(words_json_path) if words_json_path else "None",
        )
    except Exception:
        pass

    return TranscriptContext(
        words_json_path=words_json_path if isinstance(words_json_path, Path) else None,
        cleaned_path=cleaned_path,
        engine_result=engine_result,
        mixer_only_options=mixer_only_opts,
        flubber_intent=flubber_intent,
        intern_intent=intern_intent,
        base_audio_name=base_audio_name,
    )

