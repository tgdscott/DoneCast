from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from .common import AudioSegment
from .ai_flubber import handle_flubber  # existing minimal behavior (abort or transcript rollback)


def build_flubber_contexts(words: List[Dict[str, Any]], cfg: Dict[str, Any], log: List[str]) -> List[Dict[str, Any]]:
    """Produce flubber contexts based on words and config.

    Current codebase has no explicit context-building logs in processor; to preserve
    behavior and log order, this returns a lightweight structure without emitting new logs.
    """
    contexts: List[Dict[str, Any]] = []
    # Minimal context: capture indices and times for candidate 'flubber' tokens
    try:
        for i, w in enumerate(words or []):
            wd = (w or {}).get('word')
            if isinstance(wd, str) and wd.lower().strip().strip('.,!?') == 'flubber':
                contexts.append({'index': i, 'time': float(w.get('start') or 0.0)})
    except Exception:
        pass
    return contexts


def compute_flubber_spans(
    words: List[Dict[str, Any]],
    contexts: List[Dict[str, Any]],
    cfg: Dict[str, Any],
    log: List[str],
) -> List[Tuple[int, int]]:
    """Compute token-index spans to rollback prior to the last 'flubber'.

    Mirrors the existing minimal behavior in ai_flubber: for a single flubber, blank up to
    max_lookback_words before it. Spans are returned as (start_idx, end_idx_exclusive).
    """
    spans: List[Tuple[int, int]] = []
    try:
        if not contexts:
            return spans
        # Use the last flubber occurrence for rollback
        last = max(contexts, key=lambda c: c.get('time', 0.0))
        idx = int(last.get('index', -1))
        if idx >= 0:
            max_lookback = int((cfg or {}).get('max_lookback_words', 100))
            s = max(0, idx - max_lookback)
            spans.append((s, idx + 1))  # include the flubber token itself
    except Exception:
        pass
    return spans


def normalize_and_merge_spans(
    spans: List[Tuple[int, int]],
    cfg: Dict[str, Any],
    log: List[str],
) -> List[Tuple[int, int]]:
    """Normalize and merge overlapping token-index spans.

    Current behavior is simple; keep pass-through with basic merging and no new logs to
    preserve ordering.
    """
    if not spans:
        return []
    spans = sorted(((int(s), int(e)) for s, e in spans if isinstance(s, int) and isinstance(e, int) and e > s), key=lambda x: x[0])
    merged: List[Tuple[int, int]] = []
    cs, ce = spans[0]
    for s, e in spans[1:]:
        if s <= ce:
            ce = max(ce, e)
        else:
            merged.append((cs, ce))
            cs, ce = s, e
    merged.append((cs, ce))
    return merged


def apply_flubber_audio(
    audio_in: Path,
    audio_out: Path,
    spans: List[Tuple[int, int]],
    cfg: Dict[str, Any],
    log: List[str],
) -> Dict[str, int]:
    """Apply flubber spans to audio.

    The current pipeline does not perform audio cuts for flubber; it either aborts or
    performs transcript-only rollback. To preserve behavior, copy input to output and
    return zeroed metrics; do not emit new logs.
    """
    try:
        seg = AudioSegment.from_file(audio_in)
        seg.export(audio_out, format=audio_out.suffix.lstrip('.').lower() or 'mp3')
        return {
            'spans_applied': 0,
            'removed_ms': 0,
            'final_ms': len(seg),
        }
    except Exception:
        # Best-effort fallback: leave metrics empty-ish
        return {
            'spans_applied': 0,
            'removed_ms': 0,
            'final_ms': 0,
        }


def retime_words_after_flubber(
    words: List[Dict[str, Any]],
    spans: List[Tuple[int, int]],
    cfg: Dict[str, Any],
    log: List[str],
) -> List[Dict[str, Any]]:
    """Retiming after flubber.

    Current behavior does not retime after flubber (transcript-only blanking). Preserve
    behavior by returning the input words unchanged.
    """
    return words


__all__ = [
    'build_flubber_contexts',
    'compute_flubber_spans',
    'normalize_and_merge_spans',
    'apply_flubber_audio',
    'retime_words_after_flubber',
]
