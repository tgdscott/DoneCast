from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import re

from .models import Word


def _coerce_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip()
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def _to_seconds(obj: Dict[str, Any], start_key: str, end_key: str, scale: float = 1.0) -> Tuple[Optional[float], Optional[float]]:
    s = _coerce_float(obj.get(start_key))
    e = _coerce_float(obj.get(end_key))
    if s is None or e is None:
        return None, None
    return s / scale, e / scale


def parse_words(words_raw: List[Dict[str, Any]]) -> List[Word]:
    parsed: List[Word] = []
    for w in words_raw or []:
        tok = (
            (w.get('word') if isinstance(w, dict) else None)
            or (w.get('text') if isinstance(w, dict) else None)
            or (w.get('token') if isinstance(w, dict) else None)
            or (w.get('value') if isinstance(w, dict) else None)
        )
        if not tok:
            continue
        start_end: Tuple[Optional[float], Optional[float]] = (None, None)
        if isinstance(w, dict) and ('start_ms' in w or 'end_ms' in w):
            start_end = _to_seconds(w, 'start_ms', 'end_ms', scale=1000.0)
        if start_end == (None, None) and isinstance(w, dict) and ('start' in w and 'end' in w):
            start_end = _to_seconds(w, 'start', 'end', scale=1.0)
        if start_end == (None, None) and isinstance(w, dict) and ('start_time' in w and 'end_time' in w):
            start_end = _to_seconds(w, 'start_time', 'end_time', scale=1.0)
        if start_end == (None, None) and isinstance(w, dict) and ('startTime' in w and 'endTime' in w):
            start_end = _to_seconds(w, 'startTime', 'endTime', scale=1.0)
        s, e = start_end
        if s is None or e is None or e <= s:
            continue
        parsed.append(Word(word=str(tok), start=float(s), end=float(e)))
    parsed.sort(key=lambda x: x.start)
    return parsed


def merge_ranges(ranges: List[Tuple[int,int]], gap_ms: int = 0) -> List[Tuple[int,int]]:
    if not ranges:
        return []
    ranges = sorted(ranges)
    merged = [list(ranges[0])]
    for s, e in ranges[1:]:
        ls, le = merged[-1]
        if s <= le + gap_ms:
            merged[-1][1] = max(le, e)
        else:
            merged.append([s, e])
    return [tuple(x) for x in merged]


def build_filler_cuts(words: List[Word], filler_set) -> List[Tuple[int, int]]:
    """Return merged (start_ms, end_ms) spans for tokens that are in filler_set.

    - Normalizes tokens by lowercasing and stripping leading/trailing non-word chars.
    - Converts Word.start/end seconds to integer milliseconds.
    - Merges adjacent/overlapping filler spans (gap_ms=0).
    """
    if not words or not filler_set:
        return []

    def _norm(s: str) -> str:
        return re.sub(r"^[\W_]+|[\W_]+$", "", (s or "").strip().lower())

    fillers = { _norm(x) for x in filler_set if isinstance(x, str) and x.strip() }
    if not fillers:
        return []

    ranges: List[Tuple[int, int]] = []
    for w in words:
        tok = _norm(getattr(w, "word", ""))
        if tok and tok in fillers:
            s_ms = int(round(float(getattr(w, "start", 0.0)) * 1000))
            e_ms = int(round(float(getattr(w, "end", 0.0)) * 1000))
            if e_ms > s_ms:
                ranges.append((s_ms, e_ms))

    return merge_ranges(ranges, gap_ms=0)


def remap_words_after_cuts(
    words: List[Word],
    cuts_ms: List[Tuple[int, int]],
    drop_if_overlap_ratio: float = 0.5,
) -> List[Word]:
    if not cuts_ms:
        return list(words)
    cuts = sorted((max(0, int(s)), max(0, int(e))) for s, e in cuts_ms if e > s)
    merged: List[List[int]] = []
    for s, e in cuts:
        if not merged or s > merged[-1][1]:
            merged.append([s, e])
        else:
            merged[-1][1] = max(merged[-1][1], e)
    cuts = [(s, e) for s, e in merged]

    def removed_before(t_ms: int) -> int:
        total = 0
        for cs, ce in cuts:
            if ce <= t_ms:
                total += (ce - cs)
            else:
                break
        return total

    out: List[Word] = []
    i = 0
    for w in sorted(words, key=lambda w: w.start):
        ws_ms = int(round(w.start * 1000)); we_ms = int(round(w.end * 1000))
        if we_ms <= ws_ms:
            continue
        while i < len(cuts) and cuts[i][1] <= ws_ms:
            i += 1
        overlaps = []
        j = i
        while j < len(cuts) and cuts[j][0] < we_ms:
            cs, ce = cuts[j]
            if ce > ws_ms and cs < we_ms:
                overlaps.append((max(ws_ms, cs), min(we_ms, ce)))
            j += 1
        if not overlaps:
            ns = ws_ms - removed_before(ws_ms)
            ne = we_ms - removed_before(we_ms)
            if ne > ns:
                out.append(Word(word=w.word, start=ns/1000.0, end=ne/1000.0))
            continue
        ov_s = min(o[0] for o in overlaps); ov_e = max(o[1] for o in overlaps)
        overlap_len = ov_e - ov_s; word_len = we_ms - ws_ms
        if overlap_len >= drop_if_overlap_ratio * word_len:
            continue
        left_len = max(0, ov_s - ws_ms); right_len = max(0, we_ms - ov_e)
        if left_len >= right_len and left_len > 0:
            seg_s, seg_e = ws_ms, ov_s
        elif right_len > 0:
            seg_s, seg_e = ov_e, we_ms
        else:
            continue
        ns = seg_s - removed_before(seg_s); ne = seg_e - removed_before(seg_e)
        if ne > ns:
            out.append(Word(word=w.word, start=ns/1000.0, end=ne/1000.0))
    out.sort(key=lambda w: (w.start, w.end))
    return out

__all__ = [
    "parse_words",
    "merge_ranges",
    "build_filler_cuts",
    "remap_words_after_cuts",
]
