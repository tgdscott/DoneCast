from __future__ import annotations

import time
import logging
from typing import List
from ..schemas import SuggestSectionIn, SuggestSectionOut
from ..history import get_recent_sections
from ..client_gemini import generate


log = logging.getLogger(__name__)


BASE_SECTION_PROMPT = (
    "You write concise, friendly podcast intro/outro scripts."
    " Match the established style for this section without copying wording."
    " Aim for 1-3 sentences, conversational tone."
)


def _load_transcript(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(12000)
    except Exception:
        return ""


def _compose_prompt(inp: SuggestSectionIn) -> str:
    parts: List[str] = [inp.base_prompt or BASE_SECTION_PROMPT]
    history = get_recent_sections(inp.podcast_id, tag=inp.tag, section_type=inp.section_type, n=inp.history_count)
    if history:
        examples = "\n\n".join(f"Example {inp.section_type} script:\n" + h for h in history[:3])
        parts.append(f"Recent {inp.section_type} examples for tag '{inp.tag}':\n" + examples)
    if inp.transcript_path:
        tx = _load_transcript(inp.transcript_path)
        if tx:
            parts.append("Transcript excerpt (for topical references, optional):\n" + tx)
    if inp.extra_instructions:
        parts.append("Extra instructions:\n" + inp.extra_instructions)
    parts.append("Return only the script text (no markdown, no labels).")
    return "\n\n".join(parts)


def suggest_section(inp: SuggestSectionIn) -> SuggestSectionOut:
    t0 = time.time()
    prompt = _compose_prompt(inp)
    try:
        text = generate(prompt, max_tokens=256)
    except RuntimeError:
        text = "Welcome back to the show—let's jump right in."
    script = text.strip()
    dur_ms = int((time.time() - t0) * 1000)
    est_in = len(prompt) // 4
    est_out = len(script) // 4
    log.info("[ai_section] type=%s tag=%s dur_ms=%s in_tok~%s out_tok~%s", inp.section_type, inp.tag, dur_ms, est_in, est_out)
    return SuggestSectionOut(script=script)
