from __future__ import annotations

from typing import List, Dict, Tuple
from pathlib import Path

from pydub import AudioSegment
from pydub.silence import detect_silence

# Delegate core compression to the existing implementation to preserve behavior/logs
from api.services.audio.cleanup import compress_long_pauses_guarded as _compress_pauses_core


def _get_cfg_float(cfg: Dict, key: str, default: float) -> float:
    try:
        v = cfg.get(key, default)
        return float(v if v is not None else default)
    except Exception:
        return default


def detect_pauses(words: List[Dict], cfg: Dict, log: List[str]) -> List[Tuple[float, float]]:
    """Return (start_s, end_s) gaps from word timestamps >= threshold, before guards/padding.

    This mirrors a simple gap-based detection using the words timeline. The actual audio-based
    compression continues to rely on the core implementation when compressing.
    """
    spans: List[Tuple[float, float]] = []
    if not words:
        return spans
    thr = _get_cfg_float(cfg, 'maxPauseSeconds', 1.5)
    prev_end = None
    for w in words:
        try:
            st = float((w or {}).get('start') or 0.0)
            en = float((w or {}).get('end') or st)
        except Exception:
            continue
        if prev_end is not None:
            gap = st - prev_end
            if gap >= thr:
                spans.append((prev_end, st))
        prev_end = en
    # No logging here to preserve current processor log shape (none for detection step)
    return spans


def guard_and_pad(spans: List[Tuple[float, float]], cfg: Dict, log: List[str]) -> List[Tuple[float, float]]:
    """Apply basic pre/post padding; guards can be added here if present in cfg.

    Preserves current behavior/logs (processor emits none specific to padding today).
    """
    pre_ms = _get_cfg_float(cfg, 'pausePadPreMs', 0.0)
    post_ms = _get_cfg_float(cfg, 'pausePadPostMs', 0.0)
    pre_s = max(0.0, pre_ms / 1000.0)
    post_s = max(0.0, post_ms / 1000.0)
    out: List[Tuple[float, float]] = []
    for s, e in spans:
        out.append((max(0.0, s - pre_s), max(s, e + post_s)))
    return out


def compress_long_pauses_guarded(
    audio,
    max_pause_s: float,
    min_target_s: float,
    ratio: float,
    rel_db: float,
    removal_guard_pct: float,
    similarity_guard: float,
    log,
):
    """Thin pass-through to core pause compression; preserves logs and behavior.

    This signature mirrors the orchestrator call-site exactly.
    """
    return _compress_pauses_core(
        audio,
        max_pause_s=max_pause_s,
        min_target_s=min_target_s,
        ratio=ratio,
        rel_db=rel_db,
        removal_guard_pct=removal_guard_pct,
        similarity_guard=similarity_guard,
        log=log,
    )


def retime_words(words: List[Dict], spans: List[Tuple[float, float]], cfg: Dict, log: List[str]) -> List[Dict]:
    """Return retimed words for compressed audio.

    Current processor path does not retime transcript after pause compression,
    so preserve behavior by returning the input words unchanged.
    """
    return [dict(w) for w in (words or [])]


__all__ = [
    'detect_pauses',
    'guard_and_pad',
    'compress_long_pauses_guarded',
    'retime_words',
]
