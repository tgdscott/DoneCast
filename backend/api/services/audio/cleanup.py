from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple, cast

try:
    from pydub.silence import detect_silence  # type: ignore
except Exception:  # pragma: no cover - optional in tests
    def detect_silence(_audio, *_args, **_kwargs):  # type: ignore
        # Fallback: no detected silence
        return []
import re
# Normalize by removing ALL non-word characters and lowercasing to ignore punctuation and case.
_NONWORD = re.compile(r'\W+')
def _norm(w: str) -> str:
    return _NONWORD.sub('', (w or '').lower())
from .common import AudioSegment, FILLER_LEAD_TRIM_DEFAULT_MS
from .ai_fillers import compute_filler_spans


def rebuild_audio_from_words(
    main_content_audio: AudioSegment,
    mutable_words: List[Dict[str, Any]],
    filler_words: Optional[set] = None,
    remove_fillers: bool = True,
    filler_lead_trim_ms: int = FILLER_LEAD_TRIM_DEFAULT_MS,
    log: Optional[List[str]] = None,
) -> Tuple[AudioSegment, Dict[str, int], int]:
    """Rebuild audio by stitching inter-word gaps and words, with optional filler removal.
    Returns (result_audio, filler_freq_map, filler_removed_count).
    """
    if log is None:
        log = []
    result_audio: AudioSegment = AudioSegment.empty()
    cursor_ms = 0
    last_appended_segment_ms = 0
    filler_removed_count = 0
    filler_freq: Dict[str, int] = {}
    # Precompute which indices are fillers using the same phrase-aware logic as transcripts
    filler_idx = compute_filler_spans(mutable_words, filler_words or set()) if (remove_fillers and filler_words) else set()
    if log is not None:
        try:
            norm_list = [ _norm(str(x)) for x in (filler_words or set()) ]
            sample_spans = [(i, (mutable_words[i] or {}).get('word')) for i in sorted(list(filler_idx))[:12]]
            log.append(f"[FILLERS_NORM_LIST] {norm_list}")
            log.append(f"[FILLER_SPANS] count={len(filler_idx)} sample={sample_spans}")
        except Exception:
            pass
    normalized_fillers = {_norm(x) for x in (filler_words or set())} if filler_words else set()
    for idx, w in enumerate(mutable_words):
        start_ms = int(w['start'] * 1000)
        end_ms = int(w['end'] * 1000)
        if start_ms > cursor_ms:
            gap_ms = start_ms - cursor_ms
            gap_seg: AudioSegment = cast(AudioSegment, main_content_audio[cursor_ms:cursor_ms + gap_ms])
            result_audio += gap_seg
            cursor_ms += gap_ms
        sfx_file = w.get('_sfx_file')
        if sfx_file:
            # SFX handling is done upstream; here we only stitch voice content.
            # Keep the placeholder as zero-length; caller inserts SFX audio directly.
            pass
        else:
            # Always keep the original audio segment unless it's a filler to remove
            # (word text may be blanked for command tokens; audio must still pass through)
            word_text = w.get('word') or ''
            lw = _norm(word_text or '') if isinstance(word_text, str) else ''
            # Remove if this index is marked as filler by phrase-aware spans, otherwise fall back to token match
            is_filler_here = (idx in filler_idx) or (word_text and remove_fillers and normalized_fillers and lw in normalized_fillers)
            if is_filler_here:
                if filler_lead_trim_ms > 0 and last_appended_segment_ms > 0:
                    trim_amt = min(filler_lead_trim_ms, last_appended_segment_ms, len(result_audio))
                    if trim_amt > 0:
                        result_audio = cast(AudioSegment, result_audio[:-trim_amt])
                        last_appended_segment_ms -= trim_amt
                        if log is not None:
                            log.append(f"[FILLER_LEAD_TRIM] word='{lw}' trim_ms={trim_amt} at={w['start']:.3f}s")
                filler_removed_count += 1
                filler_freq[lw] = filler_freq.get(lw, 0) + 1
                # Remove from transcript text as well
                try:
                    w['word'] = ''
                except Exception:
                    pass
                if log is not None:
                    log.append(f"[FILLER_REMOVE] word='{lw}' start={w['start']:.3f}s end={w['end']:.3f}s index={idx}")
            else:
                seg: AudioSegment = cast(AudioSegment, main_content_audio[start_ms:end_ms])
                result_audio += seg
                last_appended_segment_ms = len(seg)
        cursor_ms = end_ms
    if cursor_ms < len(main_content_audio):
        tail_seg: AudioSegment = cast(AudioSegment, main_content_audio[cursor_ms:])
        result_audio += tail_seg
    return result_audio, filler_freq, filler_removed_count


def compress_long_pauses_guarded(
    audio: AudioSegment,
    max_pause_s: float,
    min_target_s: float,
    ratio: float,
    rel_db: float,
    removal_guard_pct: float,
    similarity_guard: float,
    log: List[str],
) -> AudioSegment:
    """Compress long low-energy pauses while protecting natural rhythm.

    - Detects silence regions >= max_pause_s using a relative dB threshold (dBFS - rel_db)
    - Shortens each to max(min_target_s, current_len * ratio)
    - Rolls back if too much audio is removed or envelope similarity drops too low
    """
    try:
        if max_pause_s <= 0:
            return audio
        orig_len = len(audio)
        if orig_len == 0:
            return audio

        # Envelope before
        env_before = _energy_envelope(audio)

        # Silence threshold relative to average; guard for -inf
        try:
            base_dbfs = audio.dBFS
            if math.isinf(base_dbfs):
                base_dbfs = -50.0
        except Exception:
            base_dbfs = -50.0
        silence_thresh = int(base_dbfs - abs(rel_db))

        pauses = detect_silence(
            audio,
            min_silence_len=int(max_pause_s * 1000),
            silence_thresh=silence_thresh,
            seek_step=10,
        )
        if not pauses:
            return audio

        # Build a compressed output by truncating long pauses to target length
        out = AudioSegment.empty()
        prev = 0
        removed_ms_total = 0
        compressed_count = 0
        for start, end in pauses:
            # Append content before the pause
            if start > prev:
                out += audio[prev:start]

            gap = end - start
            target_len_ms = max(int(min_target_s * 1000), int(gap * max(0.0, min(1.0, ratio))))
            target_len_ms = min(gap, target_len_ms)
            # Keep the first portion of the pause up to target length
            out += audio[start:start + target_len_ms]
            if gap > target_len_ms:
                removed_ms_total += (gap - target_len_ms)
                compressed_count += 1
            prev = end

        # Tail after the last pause
        if prev < len(audio):
            out += audio[prev:]

        removal_pct = removed_ms_total / orig_len if orig_len else 0.0
        env_after = _energy_envelope(out)
        sim = _cosine(env_before, env_after)
        guard_limit = removal_guard_pct or 0.1
        if removal_pct > guard_limit or sim < similarity_guard:
            log.append(f"[PAUSE_GUARD_ROLLBACK] removal_pct={removal_pct:.3f} sim={sim:.3f} limit={guard_limit:.3f} sim_guard={similarity_guard}")
            return audio

        # Attach stats for upstream logging
        out._compressed_pauses = compressed_count  # type: ignore[attr-defined]
        out._pause_removed_ms = removed_ms_total  # type: ignore[attr-defined]
        out._pause_removed_pct = removal_pct  # type: ignore[attr-defined]
        out._pause_env_sim = sim  # type: ignore[attr-defined]
        return out
    except Exception as e:
        log.append(f"[PAUSE_COMPRESS_ERROR] {e}")
        return audio


def _energy_envelope(a: AudioSegment, frame_ms: int = 50) -> List[float]:
    """Compute a simple RMS envelope over fixed-size frames."""
    if frame_ms <= 0:
        frame_ms = 50
    vals: List[float] = []
    n = len(a)
    step = max(1, frame_ms)
    for i in range(0, n, step):
        chunk: AudioSegment = cast(AudioSegment, a[i:i + frame_ms])
        try:
            v = float(chunk.rms)
        except Exception:
            v = 0.0
        vals.append(v)
    return vals or [0.0]


def _cosine(v1: List[float], v2: List[float]) -> float:
    """Cosine similarity between two envelopes (robust to different lengths)."""
    if not v1 or not v2:
        return 1.0
    L = min(len(v1), len(v2))
    if L == 0:
        return 1.0
    a = v1[:L]
    b = v2[:L]
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 1.0
    return max(0.0, min(1.0, dot / (na * nb)))


__all__ = [
    "rebuild_audio_from_words",
    "compress_long_pauses_guarded",
]
