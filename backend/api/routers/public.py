from fastapi import APIRouter, Query, Depends
from sqlmodel import Session, select
from sqlalchemy import text
from api.core.database import get_session
from api.models.podcast import Episode
from api.models.settings import (
    AdminSettings,
    load_admin_settings,
    load_landing_content,
    LandingPageContent,
)
import os
from pathlib import Path
from api.core.paths import FINAL_DIR, MEDIA_DIR

router = APIRouter(prefix="/public", tags=["Public"])

@router.get("/episodes")
def public_episodes(limit: int = Query(10, ge=1, le=50), session: Session = Depends(get_session)):
    """List recently published episodes (unauthenticated) for demo.
    Returns only fields safe for public consumption.
    """
    statement = (
        select(Episode)
        .where(Episode.status == "published")
        .order_by(text("processed_at DESC"))
        .limit(limit)
    )
    eps = session.exec(statement).all()
    
    items = []
    missing_audio_count = 0
    for e in eps:
        audio_url = None
        if e.final_audio_path:
            base = os.path.basename(e.final_audio_path)
            candidates = [FINAL_DIR / base, MEDIA_DIR / base]
            existing = next((c for c in candidates if c.exists()), None)
            if existing is not None:
                if existing.parent == MEDIA_DIR:
                    audio_url = f"/static/media/{base}"
                else:
                    audio_url = f"/static/final/{base}"
            else:
                missing_audio_count += 1
        
        # Use compute_cover_info to properly handle gcs_cover_path (R2 URLs)
        from api.routers.episodes.common import compute_cover_info
        cover_info = compute_cover_info(e)
        cover_url = cover_info.get("cover_url")
        
        # Fallback: if no cover_url from compute_cover_info, try cover_path
        if not cover_url and e.cover_path:
            cp = str(e.cover_path)
            if cp.lower().startswith(("http://", "https://")):
                # Only use if it's not a Spreaker URL
                if "spreaker.com" not in cp.lower() and "cdn.spreaker.com" not in cp.lower():
                    cover_url = cp
            else:
                cover_url = f"/static/media/{os.path.basename(cp)}"

        items.append({
            "id": str(e.id),
            "title": e.title,
            "description": e.show_notes or "",
            "final_audio_url": audio_url,
            "cover_url": cover_url,
        })

    return {"items": items, "diagnostics": {"missing_audio_files": missing_audio_count}}

# Lightweight config surface for SPA boot-time fetch.
from api.core.config import settings


def _load_admin_settings_safe() -> AdminSettings:
    try:
        from api.core.database import engine
        from sqlmodel import Session as SQLSession

        with SQLSession(engine) as session:
            return load_admin_settings(session)
    except Exception:
        return AdminSettings()


def _clamp_upload_limit(raw_value: int | None) -> int:
    try:
        base_value = raw_value if raw_value else 500
        value = int(base_value)
    except (TypeError, ValueError):
        return 500
    if value < 10:
        return 10
    if value > 2048:
        return 2048
    return value


@router.get("/config")
def public_config():
    admin_settings = _load_admin_settings_safe()
    return {
        "terms_version": getattr(settings, "TERMS_VERSION", ""),
    # Rebrand: expose new API base (frontend should prefer dynamic origin in prod)
        "api_base": "https://api.podcastplusplus.com",
        # Include dynamic admin-exposed limits for client UX (non-sensitive)
        "max_upload_mb": _get_max_upload_mb(admin_settings),
        "browser_audio_conversion_enabled": bool(
            admin_settings.browser_audio_conversion_enabled
        ),
    }


@router.get("/landing", response_model=LandingPageContent)
def public_landing_content(session: Session = Depends(get_session)) -> LandingPageContent:
    return load_landing_content(session)

# Pull current admin setting from DB if available; default to 500 on error
def _get_max_upload_mb(admin_settings: AdminSettings | None = None) -> int:
    try:
        settings_obj = admin_settings or _load_admin_settings_safe()
        return _clamp_upload_limit(getattr(settings_obj, "max_upload_mb", 500))
    except Exception:
        return 500
