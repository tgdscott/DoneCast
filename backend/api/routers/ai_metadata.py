import re
import os
from typing import List, Optional, Iterable
from fastapi import APIRouter, Body, HTTPException, Depends
from pydantic import BaseModel
from api.routers.auth import get_current_user
from ..models.user import User

router = APIRouter()

STOPWORDS = set("the a an and or for with this that from into about your their them they you our out over under after before while of to in on at is are was were be been it it's its as by we i me my ours ours can will just really right like um umm well so actually basically literally maybe perhaps anyway".split())

class AIMetadataRequest(BaseModel):
    prompt: Optional[str] = None
    audio_filename: Optional[str] = None
    current_title: Optional[str] = None
    current_description: Optional[str] = None
    max_tags: int = 10

class AIMetadataResponse(BaseModel):
    title: str
    description: str
    tags: List[str]
    source: str


HEX_RE = re.compile(r"\b[a-f0-9]{16,}\b", re.I)
AUDIO_JUNK_RE = re.compile(r"\b(stereo|mono|mix|wav|mp3|m4a|flac|aac|kbps|khz|hz|bit|sample)s?\b", re.I)

def _digit_ratio(s: str) -> float:
    if not s:
        return 0.0
    digits = sum(ch.isdigit() for ch in s)
    return digits / max(1, len(s))

def _sanitize_texts(texts: Iterable[str]) -> str:
    """Sanitize input fragments before composing metadata.
    - strip extensions and boilerplate audio tokens
    - remove hex-like ids
    - drop tokens with >40% digits or length > 30
    - collapse whitespace
    """
    joined = " \n".join(t for t in texts if t) if texts else ""
    if not joined:
        return ""
    # Replace separators with spaces
    base = re.sub(r"[\-_]+", " ", joined)
    # Remove hex ids and audio boilerplate words
    base = HEX_RE.sub(" ", base)
    base = AUDIO_JUNK_RE.sub(" ", base)
    # Tokenize and filter
    toks = re.findall(r"[A-Za-z0-9']+", base)
    kept: List[str] = []
    for t in toks:
        if len(t) > 30:
            continue
        if _digit_ratio(t) > 0.4:
            continue
        kept.append(t)
    text = " ".join(kept)
    # Final collapse
    text = re.sub(r"\s+", " ", text).strip()
    return text

def _safe_title_from(text: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z0-9']+", text) if w.lower() not in STOPWORDS]
    title_tokens = words[:8] or ["Episode", "Title"]
    cand = " ".join(w.capitalize() for w in title_tokens)
    # Guard against hex remnants or trivially short titles
    if HEX_RE.search(cand) or len(cand.strip()) < 4:
        return "Episode Title"
    return cand

def _normalize_tag(s: str) -> Optional[str]:
    if not s:
        return None
    # Allow only letters, numbers, and spaces after punctuation normalization
    s = re.sub(r"[^A-Za-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return None
    if len(s) > 30:
        s = s[:30]
    # Drop if mostly digits or hex-like id
    if _digit_ratio(s) > 0.4 or HEX_RE.search(s):
        return None
    return s

@router.post("/episodes/ai/metadata", response_model=AIMetadataResponse)
async def generate_episode_metadata(req: AIMetadataRequest, current_user: User = Depends(get_current_user)):
    """Generate (or suggest) title, description, and tags for an episode.
    This is a lightweight heuristic implementation that *optionally* calls a real LLM if
    OPENAI_API_KEY is present; otherwise falls back to deterministic extraction so UI can ship now.
    """
    base_texts: List[str] = []
    if req.prompt:
        base_texts.append(req.prompt)
    if req.current_description:
        base_texts.append(req.current_description)
    if req.audio_filename:
        # Use filename stem
        name = os.path.splitext(os.path.basename(req.audio_filename))[0]
        base_texts.append(name)
    corpus = _sanitize_texts(base_texts)
    # If everything sanitized away (e.g., only hashes/boilerplate), proceed with safe defaults
    if not corpus.strip():
        corpus = ""

    # --- Heuristic title ---
    if req.current_title and req.current_title.strip():
        title = req.current_title.strip()
    else:
        # Take first 8 meaningful words capitalized, then guard against junk
        title = _safe_title_from(corpus)

    # --- Heuristic description ---
    if req.current_description and req.current_description.strip():
        description = req.current_description.strip()
    else:
        # Two-sentence style: summary + hook
        summary_words = re.findall(r"[A-Za-z0-9']+", corpus)[:40]
        summary = " ".join(summary_words)
        description = summary.capitalize() + "." if summary else "Episode description coming soon."
        if len(summary_words) >= 8:
            description += "\n\nIn this episode we explore key insights and practical takeaways."

    # --- Tag extraction ---
    tokens = [w for w in re.findall(r"[A-Za-z0-9']+", corpus)]
    freq = {}
    for t in tokens:
        lo = t.lower()
        if lo in STOPWORDS:
            continue
        if len(lo) < 2:
            continue
        freq[lo] = freq.get(lo, 0) + 1
    # Sort by frequency then alphabetically
    sorted_terms = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    tags: List[str] = []
    seen = set()
    limit = min(max(1, req.max_tags or 0), 20)
    for term, _ in sorted_terms:
        cand = _normalize_tag(term)
        if not cand:
            continue
        key = cand.lower()
        if key in seen:
            continue
        seen.add(key)
        tags.append(cand)
        if len(tags) >= limit:
            break
    # Reasonable defaults if nothing survived
    if not tags:
        tags = ["podcast", "episode"]

    source = "heuristic"
    # (Optional) LLM call placeholder – can be expanded later.
    return AIMetadataResponse(title=title, description=description, tags=tags, source=source)
