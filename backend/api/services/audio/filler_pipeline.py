from __future__ import annotations

from typing import List, Dict, Iterable, Set, Tuple
import copy

# Delegate phrase-aware, punctuation- and case-insensitive matching to existing helper
from api.services.audio import ai_fillers


def compute_filler_spans(words: List[Dict], filler_words: Iterable[str]) -> Set[int]:
    """Return the set of word indexes that match filler tokens/phrases.

    Behavior mirrors current logic: punctuation- and case-insensitive, phrase-aware
    matching (single and multi-word). Implementation delegates to ai_fillers.
    """
    return ai_fillers.compute_filler_spans(words, filler_words)


def apply_blank_spans(words: List[Dict], spans: Set[int], log: List[str]) -> List[Dict]:
    """Return a NEW list where words at indices in spans are blanked (word == "").

    Preserves all other fields and list length (timestamps remain stable).
    Emits the exact transcript stats log as in the monolith.
    """
    # Count non-empty tokens before
    try:
        before_ct = sum(1 for w in (words or []) if (w or {}).get('word'))
    except Exception:
        before_ct = 0

    out: List[Dict] = []
    for idx, w in enumerate(words or []):
        if idx in spans and isinstance((w or {}).get('word'), str):
            nw = dict(w)
            nw['word'] = ''
            out.append(nw)
        else:
            out.append(dict(w))

    try:
        after_ct = sum(1 for w in (out or []) if (w or {}).get('word'))
    except Exception:
        after_ct = 0

    # Preserve exact log string used in processor.py
    try:
        log.append(f"[FILLERS_TRANSCRIPT_STATS] before={before_ct} after={after_ct} blanked={before_ct - after_ct}")
    except Exception:
        pass

    return out


def remove_fillers(words: List[Dict], filler_words: Iterable[str], log: List[str]) -> Tuple[List[Dict], Dict]:
    """Blank matched filler tokens and return a new words list and optional metrics.

    Wrapper that computes spans and applies blanking, preserving the monolith's
    logging and shapes. Metrics are empty unless the monolith tracked them.
    """
    spans = compute_filler_spans(words, filler_words)
    cleaned = apply_blank_spans(words, spans, log)
    # Monolith doesn't expose metrics at transcript stage; return empty dict
    return cleaned, {}


__all__ = [
    'compute_filler_spans',
    'apply_blank_spans',
    'remove_fillers',
]
