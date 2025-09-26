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
    """Parse the LLM output into description + bullet list.

    Robust against formats like:
      Description:\nActual first sentence...\nMore sentences...\nBullets:\n- point
    and single‑line forms: Description: A summary sentence here.\nBullets: ...
    """
    desc_lines: List[str] = []
    bullets: List[str] = []
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    mode = "scan"  # scan | desc | bullets
    for raw in lines:
        ln = raw.strip()
        low = ln.lower()
        # Header detection
        if low.startswith("description:"):
            after = ln.split(":", 1)[1].strip()
            if after:
                desc_lines.append(after)
            mode = "desc"
            continue
        if low.startswith("bullets:"):
            mode = "bullets"
            continue
        # Mode handling
        if mode == "scan":
            # First non-empty line before any headers acts as description seed
            desc_lines.append(ln)
            mode = "desc"
            continue
        if mode == "desc":
            if ln.startswith("- ") or ln.startswith("• "):
                # Implicit start of bullets section
                mode = "bullets"
            else:
                desc_lines.append(ln)
                continue  # stay in desc until bullets header or bullet marker
        if mode == "bullets":
            if ln.startswith("- ") or ln.startswith("• "):
                bullets.append(ln[2:].strip())
            else:
                # tolerate stray lines by appending as additional bullet text
                if bullets:
                    bullets[-1] = (bullets[-1] + " " + ln).strip()
                else:
                    # No bullet yet: treat as description tail fallback
                    desc_lines.append(ln)

    # Join description; collapse excessive whitespace
    desc = " ".join(x.strip() for x in desc_lines if x.strip()).strip()
    if not desc and text.strip():
        # Fallback: first non-empty line
        first = next((l.strip() for l in lines if l.strip()), "")
        desc = _strip_desc_prefix(first)
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
        if not out.description:
            import logging as _logging
            _logging.getLogger(__name__).debug("[ai_notes] empty description after parse; raw_len=%s", len(text))
    dur_ms = int((time.time() - t0) * 1000)
    est_in = len(prompt) // 4
    est_out = len(text) // 4
    logging.getLogger(__name__).info("[ai_notes] dur_ms=%s in_tok~%s out_tok~%s", dur_ms, est_in, est_out)
    return out
