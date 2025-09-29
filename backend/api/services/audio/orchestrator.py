from __future__ import annotations

"""
Canonical entry-point for audio assembly.

Use run_episode_pipeline(paths, cfg, log) directly from callers.
processor.process_and_assemble_episode is a temporary façade kept for compatibility
and will be removed after 2025-10-15.
"""

from pathlib import Path
from typing import Any, Dict, List
import time
from datetime import datetime

from pydub import AudioSegment

from api.services.audio.common import MEDIA_DIR, sanitize_filename
from api.core.paths import (
    FINAL_DIR as _FINAL_DIR,
    CLEANED_DIR as _CLEANED_DIR,
    TRANSCRIPTS_DIR as _TRANSCRIPTS_DIR,
    AI_SEGMENTS_DIR as _AI_SEGMENTS_DIR,
)
from api.services.audio.orchestrator_steps import (
    do_transcript_io,
    do_intern_sfx,
    do_flubber,
    do_fillers,
    do_silence,
    do_tts,
    do_export,
)


# Export/IO dirs (centralized under workspace root)
OUTPUT_DIR = _FINAL_DIR
AI_SEGMENTS_DIR = _AI_SEGMENTS_DIR
CLEANED_DIR = _CLEANED_DIR
TRANSCRIPTS_DIR = _TRANSCRIPTS_DIR


def run_episode_pipeline(paths: Dict[str, Any], cfg: Dict[str, Any], log: List[str]) -> Dict[str, Any]:
    """Orchestrate the entire pipeline in the same order as the monolith.

    This function mirrors processor.process_and_assemble_episode behavior,
    preserving filenames and log text/order.
    """
    # Unpack inputs
    template = paths.get("template")
    main_content_filename = str(paths.get("audio_in") or "")
    output_filename = str(paths.get("output_name") or Path(main_content_filename).stem or "episode")
    words_json_path = str(paths.get("words_json") or "") or None
    cover_image_path = str(paths.get("cover_art") or "") or None

    cleanup_options = cfg.get("cleanup_options", {}) or {}
    tts_overrides = cfg.get("tts_overrides", {}) or {}
    tts_provider = str(cfg.get("tts_provider") or "elevenlabs")
    elevenlabs_api_key = cfg.get("elevenlabs_api_key")
    mix_only = bool(cfg.get("mix_only") or False)

    total_start_time = time.time()
    log.append(f"Workflow started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if cover_image_path:
        log.append(f"Cover image path: {cover_image_path}")

    # 1) Load content & words + initial transcripts
    _out = do_transcript_io(paths, cfg, log)
    content_path = _out.get('content_path') or (MEDIA_DIR / main_content_filename)
    main_content_audio = _out.get('main_content_audio') or AudioSegment.from_file(content_path)
    words = _out.get('words') or []
    sanitized_output_filename = _out.get('sanitized_output_filename') or sanitize_filename(output_filename)

    # 2) Commands config & extraction
    # 2) Commands config & extraction (intern/flubber) -> SFX markers and ai_cmds
    _ai = do_intern_sfx(paths, cfg, log, words=words)
    mutable_words = _ai.get('mutable_words', [dict(w) for w in words])
    commands_cfg = _ai.get('commands_cfg', {})
    ai_cmds = _ai.get('ai_cmds', [])
    intern_count = _ai.get('intern_count', 0)
    flubber_count = _ai.get('flubber_count', 0)

    # Optional explicit flubber phase (no-op; already handled in do_intern_sfx)
    _ = do_flubber(paths, cfg, log, mutable_words=mutable_words, commands_cfg=commands_cfg)

    # 3) Primary cleanup and rebuild (fillers)
    _f = do_fillers(paths, cfg, log, content_path=content_path, mutable_words=mutable_words)
    cleaned_audio = _f.get('cleaned_audio', AudioSegment.from_file(content_path))
    mutable_words = _f.get('mutable_words', mutable_words)
    filler_freq_map = _f.get('filler_freq_map', {})
    filler_removed_count = _f.get('filler_removed_count', 0)

    # 4) Execute Intern commands (may synthesize TTS)
    _tts = do_tts(paths, cfg, log, ai_cmds=ai_cmds, cleaned_audio=cleaned_audio, content_path=content_path, mutable_words=mutable_words)
    cleaned_audio = _tts.get('cleaned_audio', cleaned_audio)
    ai_note_additions: List[str] = _tts.get('ai_note_additions', [])

    # 5) Optional pause compression
    log.append("[ORDER_CHECK] before_pause_compress")
    _sil = do_silence(paths, cfg, log, cleaned_audio=cleaned_audio, mutable_words=mutable_words)
    cleaned_audio = _sil.get('cleaned_audio', cleaned_audio)
    mutable_words = _sil.get('mutable_words', mutable_words)

    # 6) Export cleaned + template/final mix, transcripts, cleanup
    _exp = do_export(
        paths,
        cfg,
        log,
        template=template,
        cleaned_audio=cleaned_audio,
        main_content_filename=main_content_filename,
        output_filename=output_filename,
        cover_image_path=cover_image_path,
        mutable_words=mutable_words,
        sanitized_output_filename=sanitized_output_filename,
    )
    final_path = _exp.get('final_path')
    cleaned_filename = _exp.get('cleaned_filename')
    cleaned_path = _exp.get('cleaned_path')

    # 6b) Prepare template segments & build final mix
    # The rest of template/mix/export/transcripts are handled in do_export

    log.append(f"[TIMING] Workflow completed in {time.time() - total_start_time:.2f}s")
    return {
        "final_path": final_path,
        "log": log,
        "ai_note_additions": ai_note_additions,
    }


__all__ = ["run_episode_pipeline"]
