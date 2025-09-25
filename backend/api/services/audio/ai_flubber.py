from __future__ import annotations

from typing import Any, Dict, List, Tuple
import re

_LEADTRAIL_PUNCT = re.compile(r'^[^\w]+|[^\w]+$')
def _norm_token(s: str) -> str:
    return _LEADTRAIL_PUNCT.sub('', (s or '').lower())


def handle_flubber(mutable_words: List[Dict[str, Any]], cfg: Dict[str, Any], log: List[str]) -> None:
    """Minimal flubber behaviors for tests:
    - If two 'flubber' tokens occur within 15s, raise via RuntimeError("FLUBBER_ABORT")
    - For single 'flubber' with action rollback_restart: blank up to max_lookback_words before it
    """
    token = 'flubber'
    hits: List[Tuple[int, float]] = []
    for idx, w in enumerate(mutable_words):
        if _norm_token(str(w.get('word',''))) == token:
            hits.append((idx, float(w.get('start', 0.0))))
    if len(hits) >= 2:
        hits = sorted(hits, key=lambda x: x[1])
        first_t = hits[0][1]
        second_t = hits[1][1]
        if second_t - first_t < 15.0:
            log.append(f"[FLUBBER_ABORT] second within {second_t-first_t:.2f}s")
            raise RuntimeError("FLUBBER_ABORT")
    if hits:
        idx, t = hits[-1]
        max_lookback = int(cfg.get('max_lookback_words', 50))
        start_idx = max(0, idx - max_lookback)
        for j in range(start_idx, idx):
            if isinstance(mutable_words[j].get('word'), str):
                mutable_words[j]['word'] = ''
        try:
            mutable_words[idx]['word'] = ''
        except Exception:
            pass
        log.append(f"[FLUBBER] rollback {idx-start_idx} words at t={t:.2f}s")


__all__ = ["handle_flubber"]
