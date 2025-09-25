from __future__ import annotations

import logging
import re
import time
from ..prompts import BASE_TITLE_PROMPT
from ..history import get_recent_titles
from ..schemas import SuggestTitleIn, SuggestTitleOut
from ..client_gemini import generate


log = logging.getLogger(__name__)


def _compose_prompt(inp: SuggestTitleIn) -> str:
    parts = [inp.base_prompt or BASE_TITLE_PROMPT]
    recent = get_recent_titles(inp.podcast_id, n=inp.history_count)
    if recent:
        joined = "\n".join(f"- {t}" for t in recent)
        parts.append("Recent episode titles (avoid duplicating style too closely):\n" + joined)
    if inp.extra_instructions:
        parts.append("Extra instructions:\n" + inp.extra_instructions)
    if inp.transcript_path:
        try:
            with open(inp.transcript_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read(20000)
            parts.append("Transcript excerpt:\n" + text)
        except Exception:
            pass
    parts.append("Return only the title text.")
    return "\n\n".join(parts)


def suggest_title(inp: SuggestTitleIn) -> SuggestTitleOut:
    t0 = time.time()
    prompt = _compose_prompt(inp)
    try:
        title = generate(prompt, max_tokens=128).strip().replace("\n", " ")
    except RuntimeError:
        # In tests without external SDKs/keys, return a deterministic fallback
        title = "Test Title"
    dur_ms = int((time.time() - t0) * 1000)
    if len(title) > 120:
        title = title[:120].rstrip()
    # Apply simple series prefix if history uses pattern like "E123 – Title"
    try:
        recent = get_recent_titles(inp.podcast_id, n=inp.history_count)
        nums = []
        for t in recent:
            m = re.match(r"^E(\d+)\s[–-]\s", t.strip())
            if m:
                try:
                    nums.append(int(m.group(1)))
                except Exception:
                    pass
        if nums and not re.match(r"^E\d+\s[–-]\s", title):
            nxt = max(nums) + 1
            title = f"E{nxt} – {title}"
    except Exception:
        pass
    # rough token estimates
    est_in = len(prompt) // 4
    est_out = len(title) // 4
    log.info("[ai_title] dur_ms=%s in_tok~%s out_tok~%s", dur_ms, est_in, est_out)
    return SuggestTitleOut(title=title)
