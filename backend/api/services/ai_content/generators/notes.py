from __future__ import annotations

from typing import List

import logging
import time
import re
from ..prompts import BASE_NOTES_PROMPT
from ..history import get_recent_notes
from ..schemas import SuggestNotesIn, SuggestNotesOut
from ..client_gemini import generate


def _load_transcript(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(40000)
    except Exception:
        return ""


def _compose_prompt(inp: SuggestNotesIn) -> str:
    parts: List[str] = [inp.base_prompt or BASE_NOTES_PROMPT]
    recent = get_recent_notes(inp.podcast_id, n=inp.history_count)
    if recent:
        examples = "\n\n".join(f"Example notes:\n{n}" for n in recent[:3])
        parts.append("Recent notes examples (style reference, do not copy):\n" + examples)
    if inp.transcript_path:
        tx = _load_transcript(inp.transcript_path)
        if tx:
            parts.append("Transcript excerpt:\n" + tx)
    if inp.extra_instructions:
        parts.append("Extra instructions:\n" + inp.extra_instructions)
    parts.append("Return a short description (2-4 sentences) followed by bullet highlights.")
    parts.append("Format:\nDescription: <text>\nBullets:\n- <point>\n- <point>")
    return "\n\n".join(parts)


def _parse_notes(text: str) -> SuggestNotesOut:
    desc = ""
    bullets: List[str] = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    mode = "desc"
    for ln in lines:
        low = ln.lower()
        if low.startswith("description:"):
            desc = ln.split(":", 1)[1].strip()
            mode = "bul"
            continue
        if low.startswith("bullets:"):
            mode = "bul"
            continue
        if mode == "bul" and (ln.startswith("- ") or ln.startswith("• ")):
            bullets.append(ln[2:].strip())
        elif mode == "desc" and not desc:
            desc = ln
    return SuggestNotesOut(description=_strip_desc_prefix(desc), bullets=bullets)


def _strip_desc_prefix(s: str) -> str:
    s = s.strip()
    s = re.sub(r'^(?:\*\*?)?description:?(\*\*)?\s*', '', s, flags=re.I)
    s = re.sub(r'^#+\s*description\s*', '', s, flags=re.I)
    return s.strip()


def suggest_notes(inp: SuggestNotesIn) -> SuggestNotesOut:
    t0 = time.time()
    prompt = _compose_prompt(inp)
    text = generate(prompt, max_tokens=768)
    out = _parse_notes(text)
    if not out.description:
        out.description = _strip_desc_prefix(text.strip().splitlines()[0]) if text.strip() else ""
    dur_ms = int((time.time() - t0) * 1000)
    est_in = len(prompt) // 4
    est_out = len(text) // 4
    logging.getLogger(__name__).info("[ai_notes] dur_ms=%s in_tok~%s out_tok~%s", dur_ms, est_in, est_out)
    return out
