from __future__ import annotations

from typing import List, Dict, Any
import re

_NONWORD = re.compile(r'\W+')
def _norm(s: str) -> str:
    return _NONWORD.sub('', (s or '').lower())
def _words(s: str) -> List[str]:
    return re.findall(r'\w+', (s or '').lower())


def detect_and_mark_sfx_phrases(mutable_words: List[dict], phrase_variants: List[dict], log: List[str]) -> List[dict]:
    """Match phrases ignoring spaces/punct; accept multi-token and collapsed single-token forms."""
    sfx_events: List[dict] = []
    i, N = 0, len(mutable_words)
    while i < N:
        matched = False
        for pv in (phrase_variants or []):
            if pv.get('disabled'):
                continue
            pw = [w for w in (pv.get('words') or []) if w]
            if not pw:
                continue
            target = _norm(''.join(pw))
            strict = bool(pv.get('strict_spacing'))
            if strict:
                lens_to_try = [len(pw)]
            else:
                lens_to_try = [len(pw), 1]
                if len(pw) == 1:
                    lens_to_try.append(2)
            for L in lens_to_try:
                j = min(N, i + L)
                cand = _norm(''.join([str((mutable_words[k] or {}).get('word') or '') for k in range(i, j)]))
                # Accept exact, pluralized, or singularized forms (tolerate optional trailing 's')
                if cand and (cand == target or cand == (target + 's') or (target.endswith('s') and cand == target[:-1])):
                    try:
                        mutable_words[i]['_sfx_file'] = pv.get('file')
                        mutable_words[i]['word'] = ''
                        for k in range(i + 1, j):
                            mutable_words[k]['word'] = ''
                            mutable_words[k]['_sfx_consumed'] = True
                    except Exception:
                        pass
                    sfx_events.append({'time': float((mutable_words[i] or {}).get('start') or 0.0),
                                       'file': pv.get('file'), 'phrase': pv.get('key')})
                    if log is not None:
                        try:
                            log.append(f"[SFX_PHRASE] phrase='{pv.get('key')}' file='{pv.get('file')}' at={float((mutable_words[i] or {}).get('start') or 0.0):.3f}s")
                        except Exception:
                            pass
                    i = j; matched = True; break
            if matched:
                break
        if not matched:
            i += 1
    return sfx_events


__all__ = ["detect_and_mark_sfx_phrases"]
