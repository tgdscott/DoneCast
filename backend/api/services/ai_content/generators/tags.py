from __future__ import annotations

import json
import re
from typing import List

import time
import logging
from ..prompts import BASE_TAGS_PROMPT
from ..schemas import SuggestTagsIn, SuggestTagsOut
from ..client_router import generate, generate_json


log = logging.getLogger(__name__)
_PUNCT_RE = re.compile(r"[^a-z0-9\- ]+")


def _sanitize(tag: str) -> str:
    t = str(tag or "").strip().lower()
    t = _PUNCT_RE.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:30]


def _compose_prompt(inp: SuggestTagsIn) -> str:
    parts = [inp.base_prompt or BASE_TAGS_PROMPT]
    if inp.extra_instructions:
        parts.append("Extra instructions:\n" + inp.extra_instructions)
    if inp.transcript_path:
        try:
            with open(inp.transcript_path, "r", encoding="utf-8", errors="ignore") as f:
                parts.append("Transcript excerpt:\n" + f.read(15000))
        except Exception:
            pass
    parts.append("Return only a JSON array of tags, example: [\"tag-one\", \"ai\"].")
    return "\n\n".join(parts)


def _post_process(raw_tags: List[str], always: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    # include always first
    for t in always:
        s = _sanitize(t)
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    # then model tags
    for t in raw_tags:
        s = _sanitize(t)
        if s and s not in seen:
            seen.add(s)
            out.append(s)
            if len(out) >= 20:
                break
    return out


def suggest_tags(inp: SuggestTagsIn) -> SuggestTagsOut:
    t0 = time.time()
    prompt = _compose_prompt(inp)
    # ✅ FIXED: generate_json() doesn't accept max_tokens/temp (Gemini-only params)
    # Those params only apply to the fallback generate() call
    data = generate_json(prompt)
    tags: List[str] = []
    if isinstance(data, list):
        tags = [str(x) for x in data]
    elif isinstance(data, dict) and "tags" in data:
        tags = [str(x) for x in data.get("tags", [])]
    else:
        # fallback: try parsing lines if model ignored JSON
        # ✅ max_tokens/temperature params for text generation fallback
        text = generate(prompt, max_tokens=512, temperature=0.7)
        for ln in text.splitlines():
            ln = ln.strip("- •\t ")
            if ln:
                tags.append(ln)
    
    # If we got very few tags (< 2), retry with direct JSON call
    if len(tags) < 2:
        log.warning(f"[ai_tags] Got only {len(tags)} tags, retrying with direct call")
        try:
            from ..client_gemini import generate_json as gemini_generate_json
            data = gemini_generate_json(prompt)
            if isinstance(data, list):
                tags = [str(x) for x in data]
            elif isinstance(data, dict) and "tags" in data:
                tags = [str(x) for x in data.get("tags", [])]
        except Exception as e:
            log.error(f"[ai_tags] Retry also failed: {e}")
    final = _post_process(tags, inp.tags_always_include)
    dur_ms = int((time.time() - t0) * 1000)
    est_in = len(prompt) // 4
    est_out = sum(len(t) for t in final) // 4
    logging.getLogger(__name__).info("[ai_tags] dur_ms=%s in_tok~%s out_tok~%s count=%s", dur_ms, est_in, est_out, len(final))
    return SuggestTagsOut(tags=final)
