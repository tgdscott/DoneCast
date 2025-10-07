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
from sqlmodel import select
import api.services.ai_enhancer as enhancer
from api.services import tts_quota
from api.services.billing import usage as billing_usage
import math

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
    # When a precheck indicates this request may incur minutes, the client must set this to true
    # to proceed. If not set, we'll respond with a warning and refuse to generate.
    confirm_charge: Optional[bool] = Field(default=False)


class TTSPRECHECKBody(BaseModel):
    text: str = Field(..., min_length=1)
    speaking_rate: Optional[float] = Field(default=1.0)
    category: MediaCategory


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

    # Precheck quota and spam guard
    try:
        pre = tts_quota.precheck(
            session,
            current_user.id,
            body.category,
            text=text,
            speaking_rate=float(body.speaking_rate or 1.0),
        )
    except Exception:
        pre = {"ok": True, "spam_block": False, "warn_may_cost": False}

    if pre.get("spam_block"):
        raise HTTPException(status_code=429, detail={
            "message": "You recently created a similar TTS clip. Please wait a few seconds or reuse the one you just generated.",
            "code": "tts_spam_block"
        })

    if pre.get("warn_may_cost") and not bool(body.confirm_charge):
        # Do not synthesize; require explicit confirmation from client
        raise HTTPException(status_code=409, detail={
            "message": "We noticed high usage here. Anything else you create may count against your plan's minutes.",
            "code": "tts_confirm_required",
        })

    # Record the intent so we can finalize with actual seconds after generation
    try:
        usage_row = tts_quota.record_request(
            session,
            current_user.id,
            body.category,
            text=text,
            speaking_rate=float(body.speaking_rate or 1.0),
        )
        usage_id = getattr(usage_row, "id", None)
    except Exception:
        usage_id = None

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

    # Upload to GCS for persistence (intro/outro categories need to survive container restarts)
    import os as _os
    gcs_bucket = _os.getenv("GCS_BUCKET", "ppp-media-us-west1")
    final_filename = filename  # Will be replaced with gs:// URL if GCS upload succeeds
    if gcs_bucket and body.category in ("intro", "outro", "music", "sfx", "commercial"):
        try:
            from infrastructure import gcs
            gcs_key = f"media/{current_user.id.hex}/{body.category.value}/{filename}"
            with open(out_path, "rb") as f:
                gcs_url = gcs.upload_fileobj(gcs_bucket, gcs_key, f, content_type="audio/mpeg")
            if gcs_url:
                final_filename = gcs_url
                log.info(f"[tts] Uploaded {body.category.value} to GCS: {gcs_url}")
        except Exception as e:
            log.warning(f"[tts] Failed to upload {body.category.value} to GCS: {e}")
            # Fallback to local filename - non-fatal in dev

    # Friendly name fallback
    if body.friendly_name and body.friendly_name.strip():
        friendly_name = body.friendly_name.strip()
    else:
        words = text.split()
        friendly_name = f"TTS – {' '.join(words[:6])}"

    # Enforce unique friendly name per user (case-insensitive)
    try:
        rows = session.exec(
            select(MediaItem.friendly_name).where(MediaItem.user_id == current_user.id)
        ).all() or []
        lower = { (r[0] if isinstance(r, tuple) else r) for r in rows }
        lower = { str(x).strip().lower() for x in lower if x }
        if friendly_name.strip().lower() in lower:
            raise HTTPException(status_code=409, detail=f"A media item named '{friendly_name}' already exists. Please choose a different name.")
    except HTTPException:
        raise
    except Exception:
        # On unexpected error checking uniqueness, proceed without blocking
        pass

    item = MediaItem(
        filename=final_filename,  # Use GCS URL if uploaded, otherwise local filename
        friendly_name=friendly_name,
        category=body.category,
        content_type="audio/mpeg",
        filesize=filesize,
        user_id=current_user.id,
    )
    session.add(item)
    session.commit()
    session.refresh(item)

    # Finalize usage actual seconds and optionally post a minute debit if confirmed path
    try:
        ms = len(audio)  # pydub segment length in ms
        seconds_actual = max(0.0, float(ms) / 1000.0)
        if usage_id is not None:
            tts_quota.finalize_actual_seconds(session, usage_id, seconds_actual)
        # Determine charge only when client confirmed they were warned
        if pre.get("warn_may_cost") and bool(body.confirm_charge):
            # Compute daily usage BEFORE this generation
            used_s_before, _ = tts_quota.daily_usage(session, current_user.id, body.category)
            free_left_s = max(0.0, float(tts_quota.DailyQuota().free_seconds_per_type) - used_s_before)
            charge_seconds = max(0.0, seconds_actual - free_left_s)
            minutes_to_debit = int(math.ceil(charge_seconds / 60.0)) if charge_seconds > 0 else 0
            if minutes_to_debit > 0:
                try:
                    billing_usage.post_debit(
                        session,
                        current_user.id,
                        minutes=minutes_to_debit,
                        episode_id=None,
                        reason=str(billing_usage.LedgerReason.TTS_LIBRARY.value) if hasattr(billing_usage, 'LedgerReason') else "TTS_LIBRARY",
                        correlation_id=f"tts:{current_user.id.hex}:{item.id}",
                        notes=f"TTS {body.category.value} library generation charge ({seconds_actual:.2f}s)",
                    )
                except Exception:
                    # Don't fail the request if billing posting fails; log only
                    log.exception("Failed to post minutes debit for TTS library generation")
        # If not warned path, we charge 0 minutes, even if this exceeded the daily free seconds (grace applied)
    except Exception:
        # Non-fatal; ensure we don't break the happy path
        log.exception("Failed to finalize TTS usage/billing")

    return item


@router.post("/tts/precheck")
async def tts_precheck(
    body: TTSPRECHECKBody,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    sr = 1.0
    try:
        sr = float(body.speaking_rate or 1.0)
        if sr <= 0:
            sr = 1.0
        if sr > 3.0:
            sr = 3.0
    except Exception:
        sr = 1.0

    res = tts_quota.precheck(
        session,
        current_user.id,
        body.category,
        text=text,
        speaking_rate=sr,
    )
    # Keep messaging generic and do not expose numeric policy publicly
    message = None
    if res.get("spam_block"):
        message = "You recently created a similar TTS clip. Please wait a few seconds or reuse the one you just generated."
    elif res.get("warn_may_cost"):
        message = "We noticed high usage here. Anything else you create may count against your plan's minutes."
    return {"ok": bool(res.get("ok", True)), "spam_block": bool(res.get("spam_block")), "warn_may_cost": bool(res.get("warn_may_cost")), "message": message}
