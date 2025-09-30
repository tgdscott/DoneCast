from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from api.core.paths import TRANSCRIPTS_DIR

_TRANSCRIPT_SUFFIXES = [
    ".json",
    ".final.json",
    ".original.json",
    ".words.json",
    ".final.words.json",
    ".original.words.json",
    ".txt",
    ".final.txt",
    ".original.txt",
]


def _safe_stem(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return Path(str(value)).stem
    except Exception:
        text = str(value).strip()
        return text or None


def _candidate_stems_from_episode(episode: Any) -> list[str]:
    stems: list[str] = []
    for attr in ("working_audio_name", "final_audio_path", "source_media_url", "original_guid"):
        candidate = getattr(episode, attr, None)
        stem = _safe_stem(candidate)
        if stem:
            stems.append(stem)
    try:
        meta = json.loads(getattr(episode, "meta_json", "{}") or "{}")
        transcripts_meta = meta.get("transcripts") or {}
        for val in transcripts_meta.values():
            stem = _safe_stem(val)
            if stem:
                stems.append(stem)
        extra = meta.get("transcript_stem")
        stem = _safe_stem(extra)
        if stem:
            stems.append(stem)
    except Exception:
        pass
    # Deduplicate order preserving
    seen: set[str] = set()
    ordered: list[str] = []
    for stem in stems:
        if stem and stem not in seen:
            seen.add(stem)
            ordered.append(stem)
    return ordered


def _has_local_transcript_for_stem(stem: str) -> bool:
    if not stem:
        return False
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    for suffix in _TRANSCRIPT_SUFFIXES:
        candidate = TRANSCRIPTS_DIR / f"{stem}{suffix}"
        try:
            if candidate.exists():
                return True
        except Exception:
            continue
    return False


def transcript_endpoints_for_episode(
    episode: Any,
    *,
    api_base_url: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Return relative/absolute transcript URLs for an episode.

    The function infers availability based on stored transcript metadata or
    on-disk artifacts under ``TRANSCRIPTS_DIR``. Absolute URLs are only
    generated when ``api_base_url`` is provided (expected to include scheme).
    """

    try:
        episode_id = str(getattr(episode, "id"))
    except Exception:
        episode_id = None
    if not episode_id:
        return {"available": False, "json": None, "text": None, "absolute_json": None, "absolute_text": None}

    relative_json = f"/api/transcripts/episodes/{episode_id}.json"
    relative_text = f"/api/transcripts/episodes/{episode_id}.txt"

    available = False

    try:
        meta = json.loads(getattr(episode, "meta_json", "{}") or "{}")
        transcripts_meta = meta.get("transcripts") or {}
        if transcripts_meta:
            for val in transcripts_meta.values():
                if val:
                    available = True
                    break
    except Exception:
        transcripts_meta = {}

    if not available:
        for stem in _candidate_stems_from_episode(episode):
            if _has_local_transcript_for_stem(stem):
                available = True
                break

    absolute_json = None
    absolute_text = None
    if available and api_base_url:
        base = api_base_url.rstrip("/")
        absolute_json = f"{base}{relative_json}"
        absolute_text = f"{base}{relative_text}"

    return {
        "available": available,
        "json": relative_json if available else None,
        "text": relative_text if available else None,
        "absolute_json": absolute_json,
        "absolute_text": absolute_text,
    }
