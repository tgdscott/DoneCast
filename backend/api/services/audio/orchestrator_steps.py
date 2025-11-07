from __future__ import annotations

"""Compatibility shim exposing orchestrator step helpers as a module."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from pydub import AudioSegment

from .orchestrator_steps_lib.content import load_content_and_init_transcripts
from .orchestrator_steps_lib.ai_commands import (
    detect_and_prepare_ai_commands,
    execute_intern_commands_step,
)
from .orchestrator_steps_lib.cleanup import (
    primary_cleanup_and_rebuild,
    compress_pauses_step,
)
from .orchestrator_steps_lib.export import (
    export_cleaned_audio_step,
    build_template_and_final_mix_step,
)
from .orchestrator_steps_lib.transcripts import write_final_transcripts_and_cleanup


# Public orchestrator step wrappers -------------------------------------------------

def do_transcript_io(
    paths: Dict[str, Any],
    cfg: Dict[str, Any],
    log: List[str],
) -> Dict[str, Any]:
    template = paths.get("template")
    main_content_filename = str(paths.get("audio_in") or "")
    output_filename = str(paths.get("output_name") or Path(main_content_filename).stem or "episode")
    words_json_path = str(paths.get("words_json") or "") or None
    forbid_transcribe = bool(
        cfg.get("forbid_transcribe")
        or cfg.get("forbidTranscribe")
        or False
    )
    content_path, main_content_audio, words, sanitized_output_filename = (
        load_content_and_init_transcripts(
            main_content_filename,
            words_json_path,
            output_filename,
            log,
            forbid_transcribe=forbid_transcribe,
        )
    )
    return {
        "template": template,
        "content_path": content_path,
        "main_content_audio": main_content_audio,
        "words": words,
        "sanitized_output_filename": sanitized_output_filename,
        "output_filename": output_filename,
        "cover_image_path": str(paths.get("cover_art") or "") or None,
        "main_content_filename": main_content_filename,
    }


def do_intern_sfx(
    paths: Dict[str, Any],
    cfg: Dict[str, Any],
    log: List[str],
    *,
    words: List[Dict[str, Any]],
) -> Dict[str, Any]:
    cleanup_options = cfg.get("cleanup_options", {}) or {}
    mix_only = bool(cfg.get("mix_only") or cfg.get("mixOnly") or False)
    words_json_path = str(paths.get("words_json") or "") or None
    mutable_words, commands_cfg, ai_cmds, intern_count, flubber_count = (
        detect_and_prepare_ai_commands(
            words,
            cleanup_options,
            words_json_path,
            mix_only,
            log,
        )
    )
    return {
        "mutable_words": mutable_words,
        "commands_cfg": commands_cfg,
        "ai_cmds": ai_cmds,
        "intern_count": intern_count,
        "flubber_count": flubber_count,
    }


def do_flubber(
    paths: Dict[str, Any],
    cfg: Dict[str, Any],
    log: List[str],
    *,
    mutable_words: List[Dict[str, Any]],
    commands_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    return {}


def do_fillers(
    paths: Dict[str, Any],
    cfg: Dict[str, Any],
    log: List[str],
    *,
    content_path: Path,
    mutable_words: List[Dict[str, Any]],
) -> Dict[str, Any]:
    cleanup_options = cfg.get("cleanup_options", {}) or {}
    mix_only = bool(cfg.get("mix_only") or cfg.get("mixOnly") or False)
    cleaned_audio, mutable_words2, filler_freq_map, filler_removed_count = (
        primary_cleanup_and_rebuild(
            content_path,
            mutable_words,
            cleanup_options,
            mix_only,
            log,
        )
    )
    return {
        "cleaned_audio": cleaned_audio,
        "mutable_words": mutable_words2,
        "filler_freq_map": filler_freq_map,
        "filler_removed_count": filler_removed_count,
    }


def do_silence(
    paths: Dict[str, Any],
    cfg: Dict[str, Any],
    log: List[str],
    *,
    cleaned_audio: AudioSegment,
    mutable_words: List[Dict[str, Any]],
) -> Dict[str, Any]:
    cleanup_options = cfg.get("cleanup_options", {}) or {}
    mix_only = bool(cfg.get("mix_only") or cfg.get("mixOnly") or False)
    cleaned_audio2, mutable_words2 = compress_pauses_step(
        cleaned_audio,
        cleanup_options,
        mix_only,
        mutable_words,
        log,
    )
    return {
        "cleaned_audio": cleaned_audio2,
        "mutable_words": mutable_words2,
    }


def do_tts(
    paths: Dict[str, Any],
    cfg: Dict[str, Any],
    log: List[str],
    *,
    ai_cmds: List[Dict[str, Any]],
    cleaned_audio: AudioSegment,
    content_path: Path,
    mutable_words: List[Dict[str, Any]],
) -> Dict[str, Any]:
    tts_provider = str(cfg.get("tts_provider") or "elevenlabs")
    elevenlabs_api_key = cfg.get("elevenlabs_api_key")
    mix_only = bool(cfg.get("mix_only") or cfg.get("mixOnly") or False)
    cleanup_options = cfg.get("cleanup_options", {}) or {}
    insane_verbose = bool(
        cleanup_options.get("insaneVerbose")
        or cleanup_options.get("debugCommands")
    )

    ai_note_additions: List[str] = []
    # CRITICAL: Log to Python logging for visibility (not just log list)
    import logging as _py_logging
    _py_log = _py_logging.getLogger(__name__)
    _py_log.info(f"[DO_TTS] Called with ai_cmds count: {len(ai_cmds) if ai_cmds else 0}")
    if ai_cmds:
        _py_log.info(f"[DO_TTS] Processing {len(ai_cmds)} intern commands")
        cleaned_audio, ai_note_additions = execute_intern_commands_step(
            ai_cmds,
            cleaned_audio,
            content_path,
            tts_provider,
            elevenlabs_api_key,
            mix_only,
            mutable_words,
            log,
            insane_verbose=insane_verbose,
        )
    return {
        "cleaned_audio": cleaned_audio,
        "ai_note_additions": ai_note_additions,
    }


def do_export(
    paths: Dict[str, Any],
    cfg: Dict[str, Any],
    log: List[str],
    *,
    template: Any,
    cleaned_audio: AudioSegment,
    main_content_filename: str,
    output_filename: str,
    cover_image_path: Optional[str],
    mutable_words: List[Dict[str, Any]],
    sanitized_output_filename: str,
) -> Dict[str, Any]:
    cleaned_filename, cleaned_path = export_cleaned_audio_step(
        main_content_filename,
        cleaned_audio,
        log,
    )

    final_path, placements = build_template_and_final_mix_step(
        template,
        cleaned_audio,
        cleaned_filename,
        cleaned_path,
        main_content_filename,
        cfg.get("tts_overrides", {}) or {},
        str(cfg.get("tts_provider") or "elevenlabs"),
        cfg.get("elevenlabs_api_key"),
        output_filename,
        str(paths.get("cover_art") or "")
        or None
        if cover_image_path is None
        else cover_image_path,
        log,
    )
    write_final_transcripts_and_cleanup(
        sanitized_output_filename,
        mutable_words,
        placements,
        template,
        main_content_filename,
        log,
    )
    return {
        "final_path": final_path,
        "placements": placements,
        "cleaned_filename": cleaned_filename,
        "cleaned_path": cleaned_path,
    }


__all__ = [
    "do_transcript_io",
    "do_intern_sfx",
    "do_flubber",
    "do_fillers",
    "do_silence",
    "do_tts",
    "do_export",
    "load_content_and_init_transcripts",
    "detect_and_prepare_ai_commands",
    "execute_intern_commands_step",
    "primary_cleanup_and_rebuild",
    "compress_pauses_step",
    "export_cleaned_audio_step",
    "build_template_and_final_mix_step",
    "write_final_transcripts_and_cleanup",
]
