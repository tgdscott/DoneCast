from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, List, Tuple

from pydub import AudioSegment
from pydub.generators import Sine


def censor_audio(audio: AudioSegment, words: List[Any], cfg: Any) -> Tuple[AudioSegment, List[Tuple[int, int]]]:
    """
    Simple, type-safe profanity beeper used by legacy paths.
    - Returns a NEW AudioSegment and a list of (start_ms, end_ms) beep spans.
    - Never returns generators; avoids '+' with floats; uses AudioSegment APIs only.
    """
    def _get(obj: Any, name: str, default=None):
        return getattr(obj, name, default)

    taboo_list = _get(cfg, "censorWords", []) or []
    taboo = [str(t).strip().lower() for t in taboo_list if t]
    use_fuzzy = bool(_get(cfg, "censorFuzzy", False))
    threshold = float(_get(cfg, "censorMatchThreshold", 0.85) or 0.85)

    beep_ms = int(_get(cfg, "censorBeepMs", 250) or 250)
    beep_hz = int(_get(cfg, "censorBeepFreq", 1000) or 1000)
    beep_gain = float(_get(cfg, "censorBeepGainDb", 0.0) or 0.0)
    beep_file = _get(cfg, "censorBeepFile", None)

    # whitelist: never censor command triggers; always allow 'intern'
    whitelist = set([w.lower() for w in (_get(cfg, "censorWhitelist", []) or []) if isinstance(w, str)])
    try:
        cmds = _get(cfg, "commands", {}) or {}
        if isinstance(cmds, dict):
            for cmd in cmds.values():
                trig = cmd.get("trigger_keyword") if isinstance(cmd, dict) else getattr(cmd, "trigger_keyword", None)
                if trig:
                    whitelist.add(str(trig).lower())
    except Exception:
        pass
    whitelist.add("intern")

    punct = re.compile(r"^[\W_]+|[\W_]+$")

    def tok_at(i: int) -> str:
        w = words[i]
        t = getattr(w, "word", None)
        if t is None:
            t = getattr(w, "text", None)
        if t is None and isinstance(w, dict):
            t = w.get("word") or w.get("text")
        return (t or "").strip()

    def norm(s: str) -> str:
        return punct.sub("", (s or "")).lower()

    def bounds_ms(i: int) -> Tuple[int, int]:
        w = words[i]
        s = getattr(w, "start", None)
        e = getattr(w, "end", None)
        if isinstance(w, dict):
            s = w.get("start", s)
            e = w.get("end", e)

        def to_ms(v):
            if v is None:
                return 0
            try:
                v = float(v)
            except Exception:
                return 0
            return int(v * 1000.0) if v < 1000.0 else int(v)

        return to_ms(s), to_ms(e)

    def morph_match(tok: str, base: str) -> bool:
        return tok.startswith(base) or (len(tok) >= 3 and base.startswith(tok))

    def should_beep(token: str):
        n = norm(token)
        if not n or n in whitelist:
            return False, None, None
        for base in taboo:
            if n == base or morph_match(n, base):
                return True, base, 1.0
        if use_fuzzy:
            best_score, best_base = 0.0, None
            for base in taboo:
                sc = SequenceMatcher(None, n, base).ratio()
                if sc > best_score:
                    best_score, best_base = sc, base
            if best_score >= threshold:
                return True, best_base, best_score
        return False, None, None

    def make_beep(ms: int) -> AudioSegment:
        if beep_file:
            try:
                seg = AudioSegment.from_file(beep_file)[:ms]
                if beep_gain:
                    seg = seg.apply_gain(beep_gain)
                return seg
            except Exception:
                pass
        seg = Sine(beep_hz).to_audio_segment(duration=ms)
        if beep_gain:
            seg = seg.apply_gain(beep_gain)
        return seg

    print(f"[CENSOR_MODE] fuzzy={use_fuzzy} thr={threshold} taboo={sorted(set(taboo))} whitelist={sorted(whitelist)}")

    BEEP = make_beep(beep_ms)
    spans: List[Tuple[int, int]] = []

    for i in range(len(words)):
        token = tok_at(i)
        matched, base, score = should_beep(token)
        if not matched:
            continue
        s, e = bounds_ms(i)
        audio = audio.overlay(BEEP, position=s)
        spans.append((s, min(e, s + beep_ms)))
        try:
            print(f"[CENSOR_HIT] term='{base}' word='{token}' score={score if score is not None else 1.0:.2f} {s}->{e}ms")
        except Exception:
            pass

    if spans:
        s0, e0 = spans[0]
        print(f"[CENSOR_APPLIED] {s0}->{e0}ms +{len(spans)-1} more")
    else:
        print("[CENSOR_APPLIED] 0 spans")

    return audio, spans

