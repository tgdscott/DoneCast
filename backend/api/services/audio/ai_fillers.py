from __future__ import annotations
from typing import List, Iterable, Set
import re

# Normalize: remove ALL non-word characters and lowercase so matching ignores punctuation and case.
_NONWORD = re.compile(r"\W+")

def _norm(s: str) -> str:
    return _NONWORD.sub("", (s or "").lower())

def _norm_tokens(words: List[dict]) -> List[str]:
    out: List[str] = []
    for w in (words or []):
        tok = _norm(str((w or {}).get("word") or ""))
        out.append(tok)
    return out

def _phrase_norm_tokens(phrase: str) -> List[str]:
    # Split on word boundaries before normalizing each piece,
    # so "you know" => ["you","know"]
    return [_norm(t) for t in re.findall(r"\w+", (phrase or "").lower()) if _norm(t)]

def _compile_phrases(filler_words: Iterable[str]) -> List[List[str]]:
    uniq: List[List[str]] = []
    seen = set()
    for p in (filler_words or []):
        ntoks = tuple(_phrase_norm_tokens(str(p)))
        if not ntoks:
            continue
        if ntoks in seen:
            continue
        seen.add(ntoks)
        uniq.append(list(ntoks))
    # Sort by descending length so we always match the longest phrase first
    uniq.sort(key=len, reverse=True)
    return uniq

def _match_window(norms: List[str], i: int, phrase: List[str]) -> bool:
    L = len(phrase)
    if L == 0:
        return False
    if i + L > len(norms):
        return False
    # Exact token-by-token match over normalized tokens
    for k in range(L):
        if norms[i + k] != phrase[k]:
            return False
    return True

def compute_filler_spans(words: List[dict], filler_words: Iterable[str]) -> Set[int]:
    """
    Return a set of word indexes to remove, matching both single-token and multi-token
    filler phrases. Matching is punctuation- and case-insensitive.

    Example:
        words = [{"word": "Uh,"}, {"word": "I"}, {"word": "mean—"}]
        filler_words = ["uh", "i mean"]
        => indexes {0,1,2}
    """
    norms = _norm_tokens(words)
    phrases = _compile_phrases(filler_words)
    to_remove: Set[int] = set()
    i = 0
    while i < len(norms):
        if norms[i] == "":
            i += 1
            continue
        matched = False
        for ph in phrases:
            L = len(ph)
            if _match_window(norms, i, ph):
                for k in range(L):
                    to_remove.add(i + k)
                i += L
                matched = True
                break
        if not matched:
            i += 1
    return to_remove

def filter_fillers(words: List[dict], filler_words: Iterable[str]) -> List[dict]:
    """
    Blank tokens that are fillers (case- and punctuation-insensitive, phrase-aware).
    Does not drop entries (so timestamps remain stable); sets word -> '' for matches.
    """
    to_remove = compute_filler_spans(words, filler_words)
    out: List[dict] = []
    for idx, w in enumerate(words or []):
        if idx in to_remove and isinstance((w or {}).get("word"), str):
            nw = dict(w)
            nw["word"] = ""
            out.append(nw)
        else:
            out.append(dict(w))
    return out

__all__ = ["filter_fillers", "compute_filler_spans"]
