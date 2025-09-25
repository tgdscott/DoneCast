from __future__ import annotations

from typing import List, Optional, Tuple
from pydub import AudioSegment

from ..models import Word
from ..words import merge_ranges
from .utils import to_ms
from .flubber import apply_flubber_cuts


def remove_fillers(
    audio: AudioSegment,
    words: List[Word],
    fillers: List[str],
    *,
    filler_phrases: Optional[List[str]] = None,
    lead_trim_ms: int = 40,
    tail_trim_ms: int = 40,
) -> Tuple[AudioSegment, List[Tuple[int, int]]]:
    filler_set = {f.strip().lower() for f in fillers if f and f.strip()}
    phrase_tokens: List[List[str]] = []
    for ph in (filler_phrases or []):
        toks = [t for t in ph.strip().lower().split() if t]
        if len(toks) > 1:
            phrase_tokens.append(toks)

    cuts: List[Tuple[int, int]] = []
    i = 0
    n = len(words)
    while i < n:
        matched = False
        for ptoks in sorted(phrase_tokens, key=len, reverse=True):
            L = len(ptoks)
            if i + L <= n and all(((words[i + k].word or "").strip().lower() == ptoks[k]) for k in range(L)):
                start_ms = to_ms(words[i].start)
                end_ms = to_ms(words[i + L - 1].end)
                s = max(0, start_ms - lead_trim_ms)
                e = min(len(audio), end_ms + tail_trim_ms)
                cuts.append((s, e))
                i += L
                matched = True
                break
        if matched:
            continue

        tok = (words[i].word or "").strip().lower()
        if tok in filler_set:
            s = max(0, to_ms(words[i].start) - lead_trim_ms)
            e = min(len(audio), to_ms(words[i].end) + tail_trim_ms)
            cuts.append((s, e))
        i += 1

    if not cuts:
        return audio, []

    merged = merge_ranges(cuts, gap_ms=10)
    new_audio = apply_flubber_cuts(audio, merged)
    return new_audio, merged
