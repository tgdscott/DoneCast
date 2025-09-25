from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple
import re

from pydub import AudioSegment

from .utils import to_ms


def replace_keywords_with_sfx(
    audio: AudioSegment,
    words: List[Any],
    sfx_map: Dict[str, Path],
    gain_db: float = 0.0,
) -> AudioSegment:
    out = AudioSegment.silent(duration=0)
    cursor = 0

    phrase_list: List[Tuple[List[str], AudioSegment]] = []
    for key, p in sfx_map.items():
        try:
            seg = AudioSegment.from_file(p)
        except Exception:
            continue
        if gain_db:
            seg = seg + gain_db  # type: ignore[assignment]

        toks: List[str] = []
        for t in (key or "").strip().lower().split():
            norm = re.sub(r"^[^\w]+|[^\w]+$", "", t)
            if norm:
                toks.append(norm)
        if toks:
            phrase_list.append((toks, seg))

    def _tok(i: int) -> str:
        w = words[i]
        t = getattr(w, "word", None)
        if t is None:
            t = getattr(w, "text", None)
        if t is None and isinstance(w, dict):
            t = w.get("word") or w.get("text")
        return (t or "").strip().lower()

    i = 0
    n = len(words)
    while i < n:
        matched = False
        for toks, seg in sorted(phrase_list, key=lambda x: -len(x[0])):
            L = len(toks)
            if i + L <= n:
                ok = True
                for k in range(L):
                    raw = _tok(i + k)
                    cand = re.sub(r"^[^\w]+|[^\w]+$", "", raw)
                    if cand != toks[k]:
                        ok = False
                        break
                if not ok:
                    continue

                wi = words[i]
                wj = words[i + L - 1]
                s_ms = to_ms(getattr(wi, "start", None))
                e_ms = to_ms(getattr(wj, "end", None))

                out += audio[cursor:s_ms] + seg
                cursor = e_ms

                display = " ".join(toks)
                w0 = words[i]
                if isinstance(w0, dict):
                    w0["word"] = f"{{{display}}}"
                else:
                    setattr(w0, "word", f"{{{display}}}")

                for k in range(1, L):
                    wk = words[i + k]
                    if isinstance(wk, dict):
                        wk["word"] = ""
                    else:
                        setattr(wk, "word", "")

                i += L
                matched = True
                break

        if not matched:
            i += 1

    out += audio[cursor:]
    return out
