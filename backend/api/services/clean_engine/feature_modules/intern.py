from __future__ import annotations

from typing import Callable, List, Optional
from pydub import AudioSegment

from ..models import Word, UserSettings, InternSettings
from .utils import to_ms, detect_silences_dbfs


def _collect_command_text(words: List[Word], start_idx: int, max_words: int = 60) -> str:
    cmd_tokens: List[str] = []
    for w in words[start_idx + 1 : start_idx + 1 + max_words]:
        tok = w.word or ""
        cmd_tokens.append(tok)
        if tok.endswith((".", "?", "!")):
            break
    return " ".join(cmd_tokens).strip()


def _find_break_after(audio: AudioSegment, from_ms: int, cfg: InternSettings) -> Optional[int]:
    scan_ms = to_ms(cfg.scan_window_s)
    min_ms = to_ms(cfg.min_break_s)
    max_ms = to_ms(cfg.max_break_s)
    end_scan = min(len(audio), from_ms + scan_ms)
    window_seg: AudioSegment = audio[from_ms:end_scan]  # type: ignore[assignment]
    silences = detect_silences_dbfs(window_seg, threshold_dbfs=-40, min_len_ms=min_ms)
    if not silences:
        return None
    for s0, s1 in silences:
        if min_ms <= (s1 - s0) <= max_ms:
            return from_ms + s0
    s0, s1 = silences[0]
    if (s1 - s0) >= min_ms:
        return from_ms + s0
    return None


def insert_intern_responses(
    audio: AudioSegment,
    words: List[Word],
    settings: UserSettings,
    intern_cfg: InternSettings,
    synth: Callable[[str], AudioSegment],
    add_show_note: Callable[[str], None],
) -> AudioSegment:
    out = audio
    trigger = (settings.intern_keyword or "").strip().lower()
    for idx in [i for i, w in enumerate(words) if (w.word or "").strip().lower() == trigger]:
        cmd_text = _collect_command_text(words, idx)
        if not cmd_text:
            continue

        cmd_token_count = len(cmd_text.split())
        cmd_end_index = min(idx + cmd_token_count, len(words) - 1)
        cmd_end_ms = to_ms(words[cmd_end_index].end)

        insert_ms = _find_break_after(out, cmd_end_ms, intern_cfg)
        if insert_ms is None:
            pad_ms = int(max(0, getattr(intern_cfg, "insert_pad_ms", 500)))
            insert_ms = cmd_end_ms
            out = out[:insert_ms] + AudioSegment.silent(duration=pad_ms) + out[insert_ms:]
            insert_ms += pad_ms

        lower = cmd_text.lower()
        if lower.startswith(("show notes:", "shownotes:", "note:", "notes:")):
            note = cmd_text.split(":", 1)[1].strip() if ":" in cmd_text else cmd_text
            add_show_note(note)
            try:
                spoken = synth(f"Adding to show notes: {note}")
            except Exception:
                spoken = AudioSegment.silent(duration=800)
        else:
            try:
                spoken = synth(cmd_text)
            except Exception:
                spoken = AudioSegment.silent(duration=800)

        if not isinstance(spoken, AudioSegment):
            spoken = AudioSegment.silent(duration=0)
        out = out[:insert_ms] + spoken + out[insert_ms:]

    return out
