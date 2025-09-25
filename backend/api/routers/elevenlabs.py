from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from api.core.config import settings
from api.services.elevenlabs_service import ElevenLabsService
from api.core.auth import get_current_user
from api.models.user import User


router = APIRouter(prefix="/elevenlabs", tags=["elevenlabs"])


class VoiceItem(BaseModel):
    voice_id: Any | None = None
    name: Any | None = None
    common_name: Any | None = None
    description: Any | None = None
    preview_url: Any | None = None
    labels: Any | None = None


class VoicesResponse(BaseModel):
    items: List[VoiceItem]
    page: int
    size: int
    total: int


@router.get("/voices", response_model=VoicesResponse)
def list_voices(search: str = "", page: int = 1, size: int = 25) -> Dict[str, Any]:
    platform_key = getattr(settings, "ELEVENLABS_API_KEY", None)
    if not platform_key:
        raise HTTPException(status_code=400, detail="ELEVENLABS_API_KEY not configured")
    svc = ElevenLabsService(platform_key=platform_key)
    data = svc.list_voices(search=search, page=page, size=size)
    # Pydantic will coerce to the response model
    return data


@router.get("/voice/{voice_id}/resolve", response_model=VoiceItem)
def resolve_voice(voice_id: str, current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Resolve a single voice by ID.

    Tries platform key first; if not found, tries the user's BYOK if present.
    Returns a normalized VoiceItem shape.
    """
    # Platform key
    platform_key = getattr(settings, "ELEVENLABS_API_KEY", None)
    if platform_key:
        svc = ElevenLabsService(platform_key=platform_key)
        v = svc.get_voice(voice_id)
        if v:
            return v
    # Fall back to user's personal key (BYOK)
    user_key = getattr(current_user, "elevenlabs_api_key", None)
    if user_key:
        svc2 = ElevenLabsService(platform_key=user_key)
        v2 = svc2.get_voice(voice_id)
        if v2:
            return v2
    raise HTTPException(status_code=404, detail="VOICE_NOT_FOUND")
