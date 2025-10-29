from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pydub import AudioSegment

from api.services.audio.cleanup import rebuild_audio_from_words
from api.services.audio.filler_pipeline import remove_fillers as remove_fillers_from_pipeline
from api.services.audio.silence_pipeline import (
    compress_long_pauses_guarded,
    detect_pauses as detect_silence_pauses,
    guard_and_pad as guard_and_pad_pauses,
    retime_words as retime_words_for_pauses,
)


def primary_cleanup_and_rebuild(
    content_path: Path,
    mutable_words: List[Dict[str, Any]],
    cleanup_options: Dict[str, Any],
    mix_only: bool,
    log: List[str],
) -> Tuple[AudioSegment, List[Dict[str, Any]], Dict[str, int], int]:
    if mix_only:
        log.append("[FILLERS] Skipping filler removal (mix_only=True)")
        placeholder_audio = AudioSegment.silent(duration=1)
        return placeholder_audio, mutable_words, {}, 0

    auphonic_processed = bool(cleanup_options.get("auphonic_processed", False))
    if auphonic_processed:
        log.append("[FILLERS] Skipping filler removal (auphonic_processed=True)")

        has_flubber_markers = any(str(w.get("word", "")).strip() == "" for w in mutable_words)
        if has_flubber_markers:
            log.append("[FLUBBER_AUPHONIC] Applying Flubber cuts to Auphonic audio")
            actual_audio = AudioSegment.from_file(content_path)
            flubber_cut_audio = apply_flubber_cuts_to_audio(actual_audio, mutable_words, log)
            return flubber_cut_audio, mutable_words, {}, 0

        log.append("[FILLERS] No Flubber markers, returning placeholder")
        placeholder_audio = AudioSegment.silent(duration=1)
        return placeholder_audio, mutable_words, {}, 0

    raw_filler_list = (
        (cleanup_options.get("fillerWords", []) or [])
        if isinstance(cleanup_options, dict)
        else []
    )
    filler_words = {
        str(w).strip().lower() for w in raw_filler_list if str(w).strip()
    }
    remove_fillers_flag = (
        bool((cleanup_options or {}).get("removeFillers", True))
        if isinstance(cleanup_options, dict)
        else True
    )
    remove_fillers = bool(filler_words) and remove_fillers_flag and (not mix_only)
    try:
        reason: List[str] = []
        if not filler_words:
            reason.append("no_filler_words")
        if not remove_fillers_flag:
            reason.append("flag_off")
        if mix_only:
            reason.append("mix_only")
        log.append(
            f"[FILLERS_CFG] remove_fillers={remove_fillers} "
            f"filler_count={len(filler_words)} reasons={','.join(reason) if reason else 'ok'}"
        )
        try:
            log.append(
                f"[FILLERS_NORM_LIST] {sorted(list(filler_words))[:12]}"
            )
        except Exception:
            pass
    except Exception:
        pass
    result_audio, filler_freq_map, filler_removed_count = rebuild_audio_from_words(
        AudioSegment.from_file(content_path),
        mutable_words,
        filler_words=filler_words,
        remove_fillers=remove_fillers,
        filler_lead_trim_ms=int(cleanup_options.get("fillerLeadTrimMs", 60))
        if isinstance(cleanup_options, dict)
        else 60,
        log=log,
    )
    cleaned_audio = result_audio
    try:
        if remove_fillers:
            total_fills = int(filler_removed_count)
            top_k = sorted(
                ((v, k) for k, v in (filler_freq_map or {}).items()), reverse=True
            )[:8]
            log.append(
                f"[FILLERS_AUDIO_STATS] removed_count={total_fills} "
                f"kinds={len(filler_freq_map or {})} top={[(k, v) for v, k in top_k]}"
            )
    except Exception:
        pass
    if remove_fillers and filler_words:
        try:
            mutable_words, _ = remove_fillers_from_pipeline(
                mutable_words, list(filler_words), log
            )
        except Exception:
            pass
    return cleaned_audio, mutable_words, filler_freq_map, int(filler_removed_count)


def compress_pauses_step(
    cleaned_audio: AudioSegment,
    cleanup_options: Dict[str, Any],
    mix_only: bool,
    mutable_words: List[Dict[str, Any]],
    log: List[str],
) -> Tuple[AudioSegment, List[Dict[str, Any]]]:
    auphonic_processed = bool(cleanup_options.get("auphonic_processed", False))
    remove_pauses = (
        bool(cleanup_options.get("removePauses", True))
        if not (mix_only or auphonic_processed)
        else False
    )

    if auphonic_processed:
        log.append("[SILENCE] Skipping pause compression (auphonic_processed=True)")
        return cleaned_audio, mutable_words

    if remove_pauses:
        silence_cfg = {
            "maxPauseSeconds": float(cleanup_options.get("maxPauseSeconds", 1.5)),
            "targetPauseSeconds": float(cleanup_options.get("targetPauseSeconds", 0.5)),
            "pauseCompressionRatio": float(
                cleanup_options.get("pauseCompressionRatio", 0.4)
            ),
            "pauseRelDb": 16.0,
            "maxPauseRemovalPct": float(
                cleanup_options.get("maxPauseRemovalPct", 0.1)
            ),
            "pauseSimilarityGuard": float(
                cleanup_options.get("pauseSimilarityGuard", 0.85)
            ),
            "pausePadPreMs": float(cleanup_options.get("pausePadPreMs", 0.0)),
            "pausePadPostMs": float(cleanup_options.get("pausePadPostMs", 0.0)),
        }
        raw_spans = detect_silence_pauses(mutable_words, silence_cfg, log)
        spans = guard_and_pad_pauses(raw_spans, silence_cfg, log)

        cleaned_audio = compress_long_pauses_guarded(
            cleaned_audio,
            max_pause_s=float(cleanup_options.get("maxPauseSeconds", 1.5)),
            min_target_s=float(cleanup_options.get("targetPauseSeconds", 0.5)),
            ratio=float(cleanup_options.get("pauseCompressionRatio", 0.4)),
            rel_db=16.0,
            removal_guard_pct=float(
                cleanup_options.get("maxPauseRemovalPct", 0.1)
            ),
            similarity_guard=float(
                cleanup_options.get("pauseSimilarityGuard", 0.85)
            ),
            log=log,
        )
        mutable_words = retime_words_for_pauses(mutable_words, spans, silence_cfg, log)
    return cleaned_audio, mutable_words


def apply_flubber_cuts_to_audio(
    audio: AudioSegment,
    mutable_words: List[Dict[str, Any]],
    log: List[str],
) -> AudioSegment:
    delete_spans = []
    in_delete = False
    start_ms: Optional[int] = None

    for word in mutable_words:
        word_text = str(word.get("word", "")).strip()
        start_s = float(word.get("start", 0.0))
        end_s = float(word.get("end", start_s))

        if word_text == "":
            if not in_delete:
                start_ms = int(start_s * 1000)
                in_delete = True
        else:
            if in_delete:
                end_ms = int(start_s * 1000)
                delete_spans.append((start_ms, end_ms))
                in_delete = False

    if in_delete and mutable_words:
        last_end = float(mutable_words[-1].get("end", 0.0))
        end_ms = int(last_end * 1000)
        delete_spans.append((start_ms, end_ms))

    if not delete_spans:
        log.append("[FLUBBER_AUDIO_CUTS] No Flubber markers found, audio unchanged")
        return audio

    log.append(f"[FLUBBER_AUDIO_CUTS] Applying {len(delete_spans)} cuts to Auphonic audio")

    segments: List[AudioSegment] = []
    last_end = 0

    for start_ms, end_ms in delete_spans:
        if start_ms > last_end:
            segments.append(audio[last_end:start_ms])
            log.append(f"[FLUBBER_CUT] Removed {end_ms - start_ms}ms at {start_ms}ms")
        last_end = end_ms

    if last_end < len(audio):
        segments.append(audio[last_end:])

    if not segments:
        log.append("[FLUBBER_AUDIO_CUTS] All audio removed by Flubber, returning silence")
        return AudioSegment.silent(duration=0)

    result = segments[0]
    for seg in segments[1:]:
        result += seg

    original_duration_ms = len(audio)
    new_duration_ms = len(result)
    removed_ms = original_duration_ms - new_duration_ms
    log.append(
        f"[FLUBBER_AUDIO_CUTS] Complete: removed {removed_ms}ms total ({removed_ms / 1000.0:.2f}s)"
    )

    return result


__all__ = [
    "primary_cleanup_and_rebuild",
    "compress_pauses_step",
    "apply_flubber_cuts_to_audio",
]
