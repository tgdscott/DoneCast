from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session
import logging

from api.core.database import get_session
from api.models.user import User
from api.routers.auth import get_current_user
from api.core.paths import MEDIA_DIR
from api.models.podcast import MediaItem, MediaCategory
import api.services.ai_enhancer as enhancer

router = APIRouter(prefix="/media", tags=["Media Library"])
log = logging.getLogger(__name__)


class TTSCREATEBody(BaseModel):
    text: str = Field(..., min_length=1)
    voice_id: Optional[str] = None
    provider: Literal["elevenlabs", "google"] = "elevenlabs"
    google_voice: Optional[str] = Field(default=None)
    speaking_rate: Optional[float] = Field(default=1.0)
    category: MediaCategory
    friendly_name: Optional[str] = None


def _safe_slug(text: str) -> str:
    base = " ".join(text.strip().split())[:60]
    if not base:
        base = "tts"
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in base.lower())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "tts"


@router.post("/tts", response_model=MediaItem)
async def create_tts_media(
    body: TTSCREATEBody,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    # Clamp speaking rate to a sane range
    try:
        sr = float(body.speaking_rate or 1.0)
        if sr <= 0:
            sr = 1.0
        if sr > 3.0:
            sr = 3.0
    except Exception:
        sr = 1.0

    # Synthesize
    try:
        audio = enhancer.generate_speech_from_text(
            text=text,
            voice_id=body.voice_id,
            provider=body.provider or "elevenlabs",
            google_voice=(body.google_voice or "en-US-Neural2-C"),
            speaking_rate=sr,
            # Pass the user to the service so it can access user-specific API keys
            user=current_user,
        )
    except enhancer.AIEnhancerError as e:
        raise HTTPException(status_code=502, detail=f"TTS failed: {e}")
    except Exception as e:
        log.exception("TTS synthesis failed with an unexpected error: %s", e)
        err_str = str(e).lower()
        if "elevenlabs" in err_str and ("authentication" in err_str or "api key" in err_str):
            detail = "TTS failed: Invalid or missing ElevenLabs API key. Check your settings or the server configuration."
        else:
            detail = "TTS failed due to an unexpected server error. Please check the server logs."
        raise HTTPException(status_code=500, detail=detail)

    # Export mp3 to MEDIA_DIR
    slug = _safe_slug(text)
    filename = f"{current_user.id.hex}_{slug}.mp3"
    # Avoid rare collisions
    i = 1
    out_path = MEDIA_DIR / filename
    while out_path.exists() and i < 1000:
        filename = f"{current_user.id.hex}_{slug}-{i}.mp3"
        out_path = MEDIA_DIR / filename
        i += 1

    try:
        audio.export(out_path, format="mp3")
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to save synthesized audio")

    filesize = None
    try:
        filesize = out_path.stat().st_size
    except Exception:
        pass

    # Friendly name fallback
    if body.friendly_name and body.friendly_name.strip():
        friendly_name = body.friendly_name.strip()
    else:
        words = text.split()
        friendly_name = f"TTS – {' '.join(words[:6])}"

    item = MediaItem(
        filename=filename,
        friendly_name=friendly_name,
        category=body.category,
        content_type="audio/mpeg",
        filesize=filesize,
        user_id=current_user.id,
    )
    session.add(item)
    session.commit()
    session.refresh(item)

    return item
