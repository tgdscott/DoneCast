from __future__ import annotations

from pathlib import Path
from api.core.paths import MEDIA_DIR
from typing import Any, Dict, List, Optional, Tuple, cast
import re
from difflib import SequenceMatcher

from pydub import AudioSegment
from pydub.generators import Sine

from .utils import to_ms


_LEET_MAP = str.maketrans({
    "@": "a", "$": "s", "0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "+": "t"
})


def _normalize_token(s: str) -> str:
    s = (s or "").lower()
    # Treat bang-as-letter forms like "sh!t" while avoiding trailing punctuation like "shit!".
    s = re.sub(r"(?<=[a-z0-9])[!]+(?=[a-z0-9])", "i", s)
    s = s.translate(_LEET_MAP)
    s = re.sub(r"[^a-z]+", "", s)
    s = re.sub(r"([a-z])\1{2,}", r"\1\1", s)
    return s


def _strip_suffixes(token: str) -> str:
    s = token
    for suf in ("ing", "in", "ers", "er", "ed", "'s", "s", "y", "ty"):
        if s.endswith(suf) and len(s) > len(suf) + 1:
            return s[: -len(suf)]
    return s


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(a=a, b=b).ratio()


def _matches_token(tok_norm: str, term_norm: str, fuzzy: bool, threshold: float) -> bool:
    if not tok_norm or not term_norm:
        return False
    if not fuzzy:
        base = _strip_suffixes(tok_norm)
        if base == term_norm or tok_norm == term_norm:
            return True
        if tok_norm.startswith(term_norm):
            tail = tok_norm[len(term_norm):]
            if tail in {"ing", "in", "er", "ers", "ed", "s", "y", "ty"}:
                return True
        return False
    sim1 = _sim(tok_norm, term_norm)
    base = _strip_suffixes(tok_norm)
    sim2 = _sim(base, term_norm) if base != tok_norm else sim1
    if max(sim1, sim2) >= threshold:
        return True
    if tok_norm.startswith(term_norm):
        tail = tok_norm[len(term_norm):]
        if tail in {"ing", "in", "er", "ers", "ed", "s", "y", "ty"}:
            return True
    return False


def _load_or_gen_beep(base: Optional[AudioSegment], duration_ms: int, freq_hz: int, gain_db: float) -> AudioSegment:
    duration_ms = max(10, int(duration_ms))
    if base is not None:
        acc = AudioSegment.silent(duration=0)
        if len(base) <= 0:
            seg = AudioSegment.silent(duration=duration_ms)
        else:
            while len(acc) < duration_ms:
                acc = acc + base  # type: ignore[assignment]
            seg = acc[:duration_ms]  # type: ignore[assignment]
    else:
        seg = Sine(freq_hz).to_audio_segment(duration=duration_ms)  # type: ignore[assignment]

    if gain_db:
        seg = seg + gain_db  # type: ignore[assignment]
    try:
        seg = seg.fade_in(5).fade_out(8)  # type: ignore[assignment]
    except Exception:
        pass
    return seg  # type: ignore[return-value]


def apply_censor_beep(
    audio: AudioSegment,
    words: List[Dict[str, Any]] | List[Any],
    cfg: Any,
    mutate_words: bool = True,
) -> Tuple[AudioSegment, List[Tuple[int, int]]]:
    def _get(obj: Any, name: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    taboo_list = (_get(cfg, "censorWords", []) or _get(cfg, "words", []) or [])
    taboo = [str(t).strip().lower() for t in taboo_list if t]
    use_fuzzy = bool(_get(cfg, "censorFuzzy", _get(cfg, "fuzzy", False)))
    threshold = float(_get(cfg, "censorMatchThreshold", _get(cfg, "match_threshold", 0.85)) or 0.85)

    beep_ms = int(_get(cfg, "censorBeepMs", _get(cfg, "beep_ms", 250)) or 250)
    beep_hz = int(_get(cfg, "censorBeepFreq", _get(cfg, "beep_freq_hz", 1000)) or 1000)
    beep_gain = float(_get(cfg, "censorBeepGainDb", _get(cfg, "beep_gain_db", 0.0)) or 0.0)
    beep_file = _get(cfg, "censorBeepFile", _get(cfg, "beep_file", None))

    end_token = str(_get(cfg, "commandEndWord", "stop") or "stop").lower()

    whitelist: set[str] = set([w.lower() for w in (_get(cfg, "censorWhitelist", []) or []) if isinstance(w, str)])
    try:
        commands = _get(cfg, "commands", {}) or {}
        if isinstance(commands, dict):
            for cmd in commands.values():
                trig = cmd.get("trigger_keyword") if isinstance(cmd, dict) else getattr(cmd, "trigger_keyword", None)
                if trig:
                    whitelist.add(str(trig).lower())
    except Exception:
        pass
    whitelist.add("intern")

    print(f"[CENSOR_MODE] fuzzy={use_fuzzy} thr={threshold} taboo={sorted(set(taboo))} "
          f"whitelist={sorted(whitelist)} end='{end_token}'")

    def _tok(i: int) -> str:
        w = words[i]
        t = getattr(w, "word", None)
        if t is None:
            t = getattr(w, "text", None)
        if t is None and isinstance(w, dict):
            t = w.get("word") or w.get("text")
        return (t or "").strip()

    def _bounds_ms(i: int) -> Tuple[int, int]:
        w = words[i]
        s = getattr(w, "start", None)
        e = getattr(w, "end", None)
        if isinstance(w, dict):
            s = w.get("start", s)
            e = w.get("end", e)
        return to_ms(s), to_ms(e)

    def _set_tok(i: int, v: str) -> None:
        w = words[i]
        if isinstance(w, dict):
            if "word" in w:
                w["word"] = v
            elif "text" in w:
                w["text"] = v
        else:
            if hasattr(w, "word"):
                setattr(w, "word", v)
            elif hasattr(w, "text"):
                setattr(w, "text", v)

    ops: List[Dict[str, Any]] = []
    i = 0
    n = len(words)
    while i < n:
        t0 = _normalize_token(_tok(i))
        if i + 1 < n:
            t1 = _normalize_token(_tok(i + 1))
            if (t0, t1) == (end_token, "intern"):
                s0, _ = _bounds_ms(i)
                _, e1 = _bounds_ms(i + 1)
                if e1 > s0:
                    ops.append({"type": "cut", "s": s0, "e": e1, "repl": None})
                    _set_tok(i, "")
                    _set_tok(i + 1, "")
                    print(f"[COMMAND_PRUNE] phrase='{end_token} intern' {s0}->{e1}ms")
                    i += 2
                    continue

        if t0 == end_token:
            s0, e0 = _bounds_ms(i)
            if e0 > s0:
                ops.append({"type": "cut", "s": s0, "e": e0, "repl": None})
                _set_tok(i, "")
                print(f"[COMMAND_PRUNE] token='{end_token}' {s0}->{e0}ms")
        i += 1

    taboo_phrases: List[List[str]] = []
    for term in taboo:
        toks = [t for t in (term or "").split() if t]
        if not toks:
            continue
        taboo_phrases.append([_normalize_token(t) for t in toks])
    taboo_phrases.sort(key=lambda x: -len(x))

    idx = 0
    while idx < n:
        raw0 = _tok(idx)
        norm0 = _normalize_token(raw0)
        if not norm0 or norm0 in whitelist:
            idx += 1
            continue

        matched_any = False
        for phrase in taboo_phrases:
            L = len(phrase)
            if idx + L > n:
                continue
            ok = True
            for k in range(L):
                cand = _normalize_token(_tok(idx + k))
                if not cand or (_normalize_token(_tok(idx + k)) in whitelist):
                    ok = False
                    break
                if not _matches_token(cand, phrase[k], use_fuzzy, threshold):
                    ok = False
                    break
            if not ok:
                continue

            s, _ = _bounds_ms(idx)
            _, e = _bounds_ms(idx + L - 1)
            if e <= s:
                continue

            base_seg: Optional[AudioSegment] = None
            if isinstance(beep_file, (str, Path)) and str(beep_file).strip():
                try:
                    p = Path(str(beep_file))
                    if not p.exists():
                        for cand in [Path.cwd() / p, Path.cwd() / str(beep_file), MEDIA_DIR / p.name]:
                            if cand.is_file():
                                p = cand
                                break
                    if p.is_file():
                        base_seg = AudioSegment.from_file(str(p))
                except Exception as ex:
                    print(f"[CENSOR_BEEP_FILE_ERROR] {beep_file}: {ex}")

            target_len = (e - s) if mutate_words else beep_ms
            if base_seg is not None:
                beep_seg = _load_or_gen_beep(base_seg, target_len, beep_hz, beep_gain)
            else:
                beep_seg = _load_or_gen_beep(None, target_len, beep_hz, beep_gain)

            ops.append({"type": "replace", "s": s, "e": e, "repl": beep_seg})

            if mutate_words:
                w0 = words[idx]
                if isinstance(w0, dict):
                    w0["word"] = "{beep}"
                else:
                    setattr(w0, "word", "{beep}")
                for k in range(1, L):
                    wk = words[idx + k]
                    if isinstance(wk, dict):
                        wk["word"] = ""
                    else:
                        setattr(wk, "word", "")

            try:
                print(f"[CENSOR_HIT] phrase='{ ' '.join(phrase) }' span={s}->{e}ms")
            except Exception:
                pass
            idx += L
            matched_any = True
            break

        if not matched_any:
            base = None
            single_hit = False
            for single in [p[0] for p in taboo_phrases if len(p) == 1]:
                if _matches_token(norm0, single, use_fuzzy, threshold):
                    base = single
                    single_hit = True
                    break
            if single_hit:
                s, e = _bounds_ms(idx)
                if e > s:
                    base_seg: Optional[AudioSegment] = None
                    if isinstance(beep_file, (str, Path)) and str(beep_file).strip():
                        try:
                            p = Path(str(beep_file))
                            if not p.exists():
                                for cand in [Path.cwd() / p, Path.cwd() / str(beep_file), MEDIA_DIR / p.name]:
                                    if cand.is_file():
                                        p = cand
                                        break
                            if p.is_file():
                                base_seg = AudioSegment.from_file(str(p))
                        except Exception as ex:
                            print(f"[CENSOR_BEEP_FILE_ERROR] {beep_file}: {ex}")

                    target_len = (e - s) if mutate_words else beep_ms
                    if base_seg is not None:
                        beep_seg = _load_or_gen_beep(base_seg, target_len, beep_hz, beep_gain)
                    else:
                        beep_seg = _load_or_gen_beep(None, target_len, beep_hz, beep_gain)
                    ops.append({"type": "replace", "s": s, "e": e, "repl": beep_seg})

                    if mutate_words:
                        w0 = words[idx]
                        if isinstance(w0, dict):
                            w0["word"] = "{beep}"
                        else:
                            setattr(w0, "word", "{beep}")
                    try:
                        print(f"[CENSOR_HIT] term='{base}' word='{raw0}' {s}->{e}ms")
                    except Exception:
                        pass
                idx += 1
            else:
                idx += 1

    if not ops:
        return audio, []

    ops.sort(key=lambda d: int(d["s"]))
    new_audio = AudioSegment.silent(duration=0)
    cursor = 0
    deltas: List[Tuple[int, int]] = []

    for op in ops:
        s = int(op["s"])
        e = int(op["e"])
        new_audio += audio[cursor:s]
        if op["type"] == "cut":
            repl_len = 0
        else:
            repl = op["repl"]  # type: ignore[assignment]
            new_audio += repl
            repl_len = len(repl)
        cursor = e
        delta = repl_len - (e - s)
        if delta:
            deltas.append((s, delta))

    new_audio += audio[cursor:]
    audio = new_audio

    deltas.sort(key=lambda x: x[0])
    k = 0
    cum = 0
    for i in range(len(words)):
        s, e = _bounds_ms(i)
        while k < len(deltas) and deltas[k][0] <= s:
            cum += deltas[k][1]
            k += 1
        if s or e:
            ns = max(0, s + cum)
            ne = max(0, e + cum)
            w = words[i]
            if isinstance(w, dict):
                if "start" in w:
                    w["start"] = ns
                if "end" in w:
                    w["end"] = ne
            else:
                if hasattr(w, "start"):
                    setattr(w, "start", ns)
                if hasattr(w, "end"):
                    setattr(w, "end", ne)

    def _shift_at(t: int) -> int:
        sft = 0
        for pos, d in deltas:
            if pos <= t:
                sft += d
            else:
                break
        return sft

    beep_spans: List[Tuple[int, int]] = []
    for op in ops:
        if op["type"] != "replace":
            continue
        s = int(op["s"])
        repl = op["repl"]  # type: ignore[assignment]
        fs = s + _shift_at(s)
        beep_spans.append((fs, fs + len(repl)))

    if beep_spans:
        s0, e0 = beep_spans[0]
        print(f"[CENSOR_APPLIED] {s0}->{e0}ms +{len(beep_spans) - 1} more")
    else:
        print("[CENSOR_APPLIED] 0 spans")

    return audio, beep_spans
