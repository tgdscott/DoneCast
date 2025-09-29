from __future__ import annotations

from typing import Any, List, Tuple
from difflib import SequenceMatcher
try:
    from pydub import AudioSegment  # type: ignore
except Exception:  # pragma: no cover - optional in tests
    class AudioSegment:  # minimal stub for typing; tests provide richer stubs
        dBFS: float = -20.0
        def __len__(self) -> int:
            return 0
        def __getitem__(self, _s):  # type: ignore
            return self
        @classmethod
        def empty(cls):
            return cls()
        @classmethod
        def silent(cls, duration=0):  # type: ignore[no-untyped-def]
            return cls()
        @classmethod
        def from_file(cls, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            return cls()

try:
    from pydub.silence import detect_silence  # type: ignore
except Exception:  # pragma: no cover - optional in tests
    def detect_silence(_audio, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        return []


def to_ms(v: float | int | None) -> int:
    """Convert seconds (float) or milliseconds (>=1000) to int ms. None -> 0."""
    if v is None:
        return 0
    try:
        f = float(v)
    except Exception:
        return 0
    # Heuristic: treat fractional <= 60s as seconds
    if (isinstance(v, float) and not f.is_integer()) or (isinstance(v, str) and ('.' in v or 'e' in v.lower())):
        if 0 <= f <= 60:
            return max(0, int(round(f * 1000)))
    return max(0, int(round(f)))


def slice_ms(seg: AudioSegment, start_ms: int, end_ms: int) -> AudioSegment:
    start_ms = max(0, start_ms)
    end_ms = min(len(seg), end_ms)
    return seg[start_ms:end_ms]  # type: ignore[return-value]


def detect_silences_dbfs(audio: AudioSegment, threshold_dbfs: int, min_len_ms: int) -> List[Tuple[int, int]]:
    """Return [ (start_ms, end_ms), ... ] where audio is below (audio.dBFS + threshold_dbfs) at least min_len_ms."""
    silence_thresh = int(audio.dBFS + threshold_dbfs)
    spans = detect_silence(audio, min_silence_len=min_len_ms, silence_thresh=silence_thresh)
    return [(int(s), int(e)) for s, e in spans]


def find_phrase(words: List[Any], keyword: str, *, fuzzy: bool = True, threshold: float = 0.86) -> List[int]:
    import re as _re

    def _norm(s: str) -> str:
        return _re.sub(r"[^a-z]+", "", (s or "").lower())

    def _strip_suffixes(s: str) -> str:
        for suf in ("ing", "in", "ers", "er", "ed", "'s", "s"):
            if s.endswith(suf) and len(s) > len(suf) + 1:
                return s[: -len(suf)]
        return s

    knorm = _norm(keyword)
    if not knorm:
        return []

    hits: List[int] = []
    n = len(words)
    for i in range(n):
        t0 = _norm(getattr(words[i], "word", ""))
        if not t0:
            continue
        if t0 == knorm or _strip_suffixes(t0) == knorm or t0.startswith(knorm):
            hits.append(i)
            continue
        if fuzzy and SequenceMatcher(None, t0, knorm).ratio() >= threshold:
            hits.append(i)
            continue
        if i + 1 < n:
            t1 = _norm(getattr(words[i + 1], "word", ""))
            if t1:
                comb = t0 + t1
                if comb == knorm or SequenceMatcher(None, comb, knorm).ratio() >= threshold:
                    hits.append(i)
                    continue
    return hits
