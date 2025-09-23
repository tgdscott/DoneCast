from fastapi import APIRouter, Query, Depends
from sqlmodel import Session, select
from sqlalchemy import text
from api.core.database import get_session
from api.models.podcast import Episode
import os
from pathlib import Path
from api.core.paths import FINAL_DIR

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
            file_path = FINAL_DIR / base
            if file_path.exists():
                audio_url = f"/static/final/{base}"
            else:
                missing_audio_count += 1
        
        cover_url = None
        if e.cover_path:
            cp = str(e.cover_path)
            if cp.lower().startswith(("http://", "https://")):
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

@router.get("/config")
def public_config():
    return {
        "terms_version": getattr(settings, "TERMS_VERSION", ""),
        "api_base": "https://api.getpodcastplus.com",
        # Include dynamic admin-exposed limits for client UX (non-sensitive)
        "max_upload_mb": _get_max_upload_mb(),
    }

# Pull current admin setting from DB if available; default to 500 on error
def _get_max_upload_mb() -> int:
    try:
        from api.core.database import get_session
        from fastapi import Depends
        # We cannot use Depends here; manually open a session
        from sqlmodel import Session
        from api.core.database import engine
        with Session(engine) as s:
            from api.models.settings import load_admin_settings
            admin = load_admin_settings(s)
            val = int(getattr(admin, 'max_upload_mb', 500) or 500)
            # enforce a sane floor/ceiling
            if val < 10:
                return 10
            if val > 2048:
                return 2048
            return val
    except Exception:
        return 500
