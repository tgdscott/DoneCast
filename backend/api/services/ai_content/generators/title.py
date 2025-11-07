from __future__ import annotations

import logging
import re
import time
from ..prompts import BASE_TITLE_PROMPT
from ..history import get_recent_titles
from ..schemas import SuggestTitleIn, SuggestTitleOut
from ..client_router import generate


log = logging.getLogger(__name__)


def _compose_prompt(inp: SuggestTitleIn) -> str:
    # If current_text provided, we're refining an existing title
    if inp.current_text:
        parts = [
            "You are an expert podcast title editor. Refine and improve the following episode title to make it more engaging, SEO-friendly, and compelling.",
            f"\nCurrent title:\n{inp.current_text}",
        ]
        if inp.extra_instructions:
            parts.append("\nAdditional instructions:\n" + inp.extra_instructions)
        if inp.transcript_path:
            try:
                with open(inp.transcript_path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read(10000)  # Shorter excerpt for refinement
                parts.append("\nTranscript excerpt (for context):\n" + text)
            except Exception:
                pass
        parts.append("\nReturn only the refined title text (no explanations).")
        return "\n".join(parts)
    
    # Otherwise, generate a new title from scratch
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
        # If AI returns empty/near-empty response, retry with direct client call
        if len(title) < 10:
            log.warning("[ai_title] Primary call returned empty/short response, retrying")
            from ..client_gemini import generate as gemini_generate
            title = gemini_generate(prompt).strip().replace("\n", " ")
    except RuntimeError:
        # In tests without external SDKs/keys, return a deterministic fallback
        title = "Test Title"
    dur_ms = int((time.time() - t0) * 1000)
    if len(title) > 120:
        title = title[:120].rstrip()
    
    # Apply title case formatting (capitalize first letter of each major word)
    title = _apply_title_case(title)
    
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


def _apply_title_case(text: str) -> str:
    """
    Apply proper title case capitalization.
    Capitalizes first letter of each word except common articles/prepositions.
    """
    # Words that should stay lowercase unless they're the first word
    lowercase_words = {
        'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'from', 'in', 
        'into', 'nor', 'of', 'on', 'or', 'so', 'the', 'to', 'up', 'with', 'yet'
    }
    
    words = text.split()
    if not words:
        return text
    
    # Always capitalize first and last word
    result = []
    for i, word in enumerate(words):
        # Preserve existing acronyms/all-caps words (e.g., "AI", "SEO")
        if word.isupper() and len(word) > 1:
            result.append(word)
        # First or last word always capitalized
        elif i == 0 or i == len(words) - 1:
            result.append(word.capitalize())
        # Check if it's a lowercase word
        elif word.lower() in lowercase_words:
            result.append(word.lower())
        else:
            result.append(word.capitalize())
    
    return ' '.join(result)
