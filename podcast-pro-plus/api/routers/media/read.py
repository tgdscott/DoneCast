from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text as _sa_text
from sqlmodel import Session, select

from api.models.podcast import MediaItem, MediaCategory
from api.models.user import User
from api.core.database import get_session
from api.routers.auth import get_current_user

router = APIRouter(prefix="/media", tags=["Media Library"])


@router.get("/", response_model=List[MediaItem])
async def list_user_media(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Retrieve the current user's media library, filtering out main content and covers.

    Only return items in categories: intro, outro, music, sfx, commercial.
    """
    allowed = [
        MediaCategory.intro,
        MediaCategory.outro,
        MediaCategory.music,
        MediaCategory.sfx,
        MediaCategory.commercial,
    ]
    statement = (
        select(MediaItem)
        .where(
            MediaItem.user_id == current_user.id,
            MediaItem.category.in_(allowed),  # type: ignore[attr-defined]
        )
        .order_by(_sa_text("created_at DESC"))
    )
    return session.exec(statement).all()


@router.get("/preview")
def preview_media(
    id: Optional[str] = Query(default=None),
    path: Optional[str] = Query(default=None, description="gs:// path or local filename (dev)"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return a temporary URL (or redirect) to preview a media item.

    Priority: id -> lookup and verify ownership. If not provided, allow explicit path only in dev.
    For gs://, generate a short-lived signed URL. For local filenames, serve via /static/media.
    """
    from fastapi.responses import RedirectResponse
    from api.core.paths import MEDIA_DIR
    from infrastructure.gcs import make_signed_url
    import os

    item: Optional[MediaItem] = None
    if id:
        try:
            from uuid import UUID as _UUID
            uid = _UUID(id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid id")
        item = session.get(MediaItem, uid)
        if not item or item.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Not found")
        path = item.filename

    if not path:
        raise HTTPException(status_code=400, detail="Missing id or path")

    if path.startswith("gs://"):
        # gs://bucket/key -> signed URL
        p = path[5:]
        bucket, _, key = p.partition("/")
        if not bucket or not key:
            raise HTTPException(status_code=400, detail="Invalid gs path")
        try:
            url = make_signed_url(bucket, key, minutes=int(os.getenv("GCS_SIGNED_URL_TTL_MIN", "10")))
        except Exception as ex:
            raise HTTPException(status_code=500, detail=f"Failed to sign URL: {ex}")
        return RedirectResponse(url)
    else:
        # Local dev file under MEDIA_DIR -> mount is at /static/media
        filename = path.lstrip("/\\")
        full = MEDIA_DIR / filename
        if not str(full).startswith(str(MEDIA_DIR)):
            raise HTTPException(status_code=400, detail="Invalid path")
        # Trust static mount route
        return RedirectResponse(url=f"/static/media/{filename}")
