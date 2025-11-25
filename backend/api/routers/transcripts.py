from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlmodel import Session
from typing import Optional
import json
from pathlib import Path
import os
from uuid import UUID as _UUID

from api.core.database import get_session
from api.services.audio.transcript_io import load_transcript_json
from api.models.podcast import Episode
from api.services.episodes import repo as _ep_repo
from api.core.paths import TRANSCRIPTS_DIR
from api.services.transcripts import discover_transcript_json_path as _discover_transcript_json_path  # reuse discovery

router = APIRouter(prefix="/transcripts", tags=["transcripts"])


def _format_timestamp(seconds: float) -> str:
    """Format seconds as MM:SS or HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _format_diarized_transcript(words: list) -> str:
    """Convert word-level transcript to diarized text format with speaker labels.
    
    Builds phrases by grouping consecutive words from the same speaker with gaps < 0.8s.
    Formats as: [MM:SS - MM:SS] Speaker: text
    """
    if not words:
        return ""
    
    phrases = []
    current_phrase = None
    prev_end = None
    prev_speaker = None
    gap_threshold = 0.8  # seconds
    
    for w in words:
        if not isinstance(w, dict):
            continue
        
        word_text = str(w.get("word", "")).strip()
        if not word_text:
            continue
        
        start = float(w.get("start", 0.0))
        end = float(w.get("end", start))
        speaker = str(w.get("speaker") or "Speaker")
        
        # Calculate gap from previous word
        gap = (start - prev_end) if prev_end is not None else 0.0
        
        # Start new phrase if speaker changed or gap is too large
        if current_phrase is None or speaker != prev_speaker or gap >= gap_threshold:
            if current_phrase is not None:
                phrases.append(current_phrase)
            current_phrase = {
                "speaker": speaker,
                "start": start,
                "end": end,
                "text": word_text
            }
        else:
            # Continue current phrase
            current_phrase["end"] = end
            current_phrase["text"] += " " + word_text
        
        prev_end = end
        prev_speaker = speaker
    
    # Don't forget the last phrase
    if current_phrase is not None:
        phrases.append(current_phrase)
    
    # Format phrases as text
    lines = []
    for p in phrases:
        start_ts = _format_timestamp(p["start"])
        end_ts = _format_timestamp(p["end"])
        speaker = p["speaker"]
        text = p["text"].strip()
        lines.append(f"[{start_ts} - {end_ts}] {speaker}: {text}")
    
    return "\n".join(lines) + ("\n" if lines else "")


def _resolve_from_gcs(session: Session, episode_id: str) -> Optional[tuple[str, bytes]]:
    """Attempt to fetch transcript JSON content from GCS based on episode/user stems.

    Returns (filename, content_bytes) or None.
    """
    try:
        from api.models.podcast import Episode as _Ep
        ep_uuid = None
        try:
            ep_uuid = _UUID(str(episode_id))
        except Exception:
            ep_uuid = None
        ep: Optional[_Ep] = _ep_repo.get_episode_by_id(session, ep_uuid) if ep_uuid else None
    except Exception:
        ep = None
    if not ep:
        return None
    user_id = str(getattr(ep, 'user_id', '') or '')
    if not user_id:
        return None
    stems: list[str] = []
    for attr in ("working_audio_name", "final_audio_path"):
        v = getattr(ep, attr, None)
        if v:
            try:
                stems.append(Path(str(v)).stem)
            except Exception:
                pass
    try:
        meta = json.loads(getattr(ep, 'meta_json', '{}') or '{}')
        for k in ("source_filename", "main_content_filename", "output_filename"):
            v = meta.get(k)
            if v:
                try:
                    stems.append(Path(str(v)).stem)
                except Exception:
                    pass
    except Exception:
        pass
    stems = [s for s in dict.fromkeys([s for s in stems if s])]
    if not stems:
        return None
    bucket = (os.getenv("TRANSCRIPTS_BUCKET") or os.getenv("MEDIA_BUCKET") or "").strip()
    if not bucket:
        return None
    from api.infrastructure.gcs import download_bytes  # type: ignore
    # Try user-specific path first, then a shared transcripts/<stem>.json
    for stem in stems:
        for key in (f"transcripts/{user_id}/{stem}.json", f"transcripts/{stem}.json"):
            try:
                data = download_bytes(bucket, key)
                return (f"{stem}.json", data)
            except Exception:
                continue
    return None


@router.get("/episodes/{episode_id}.json")
def get_episode_transcript_json(episode_id: str, session: Session = Depends(get_session)):
    path = _discover_transcript_json_path(session, episode_id, None)
    if not path:
        # attempt GCS
        gcs_hit = _resolve_from_gcs(session, episode_id)
        if gcs_hit:
            fname, data = gcs_hit
            return Response(content=data, media_type="application/json")
        raise HTTPException(status_code=404, detail="TRANSCRIPT_NOT_FOUND")
    try:
        content = Path(path).read_bytes()
        return Response(content=content, media_type="application/json")
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Failed to read transcript file %s: %s", path, e, exc_info=True)
        raise HTTPException(status_code=404, detail="TRANSCRIPT_NOT_FOUND")


@router.get("/episodes/{episode_id}.txt")
def get_episode_transcript_text(episode_id: str, session: Session = Depends(get_session)):
    path = _discover_transcript_json_path(session, episode_id, None)
    words = None
    if path and Path(path).exists():
        try:
            words = load_transcript_json(Path(path))
        except Exception:
            words = None
    if words is None:
        gcs_hit = _resolve_from_gcs(session, episode_id)
        if gcs_hit:
            try:
                _, data = gcs_hit
                words = json.loads(data)
            except Exception:
                words = None
    if words is None:
        raise HTTPException(status_code=404, detail="TRANSCRIPT_NOT_FOUND")
    
    # Generate diarized transcript with speaker labels and timestamps
    try:
        text = _format_diarized_transcript(words)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Failed to format diarized transcript: %s", e, exc_info=True)
        # Fallback to simple concatenation if formatting fails
        try:
            text = " ".join([str(w.get("word", "")).strip() for w in words if w.get("word")])
        except Exception as fallback_err:
            logging.getLogger(__name__).error("Failed to fallback format transcript: %s", fallback_err, exc_info=True)
            text = ""
    return Response(content=text.encode("utf-8"), media_type="text/plain; charset=utf-8")


@router.get("/by-hint")
def get_transcript_by_hint(
    hint: str = Query(..., description="Filename or URI hint pointing to the media/transcript (e.g., gs://.../file.mp3)"),
    fmt: str = Query("json", description="Output format: 'json' (default) or 'txt'"),
    session: Session = Depends(get_session),
):
    """Return a transcript using a filename or GCS URI hint.

    This endpoint is useful immediately after upload, before an Episode row exists.
    It reuses discovery to find or download a transcript JSON locally and can
    return either the raw JSON array of word tokens or a plain-text rendering.
    """
    if not isinstance(hint, str) or not hint.strip():
        raise HTTPException(status_code=400, detail="Missing hint")

    # Reuse broad discovery: looks locally, then attempts GCS download
    path = _discover_transcript_json_path(session, episode_id=None, hint=hint)
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="TRANSCRIPT_NOT_FOUND")

    try:
        if (fmt or "json").lower() == "txt":
            try:
                words = load_transcript_json(Path(path))
            except Exception:
                words = None
            if words is None:
                raise HTTPException(status_code=404, detail="TRANSCRIPT_NOT_FOUND")
            try:
                text = _format_diarized_transcript(words)
            except Exception:
                # Fallback to simple concatenation if formatting fails
                try:
                    text = " ".join([str(w.get("word", "")).strip() for w in words if w.get("word")])
                except Exception:
                    text = ""
            return Response(content=text.encode("utf-8"), media_type="text/plain; charset=utf-8")
        else:
            content = Path(path).read_bytes()
            return Response(content=content, media_type="application/json")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="TRANSCRIPT_NOT_FOUND")
