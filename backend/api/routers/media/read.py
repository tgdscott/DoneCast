from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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
    request: Request,
    id: Optional[str] = Query(default=None),
    path: Optional[str] = Query(default=None, description="gs:// path or local filename (dev)"),
    resolve: bool = Query(default=False, description="If true, return JSON {url} instead of redirect"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return a temporary URL (or redirect) to preview a media item.

    Priority: id -> lookup and verify ownership. If not provided, allow explicit path only in dev.
    For gs://, generate a short-lived signed URL. For local filenames, serve via /static/media.

    If `resolve=true`, return a JSON body `{ "url": "..." }` instead of issuing a redirect.
    """
    from fastapi.responses import RedirectResponse, JSONResponse
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

    # Compute destination URL
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
    else:
        # Local dev file under MEDIA_DIR -> mount is at /static/media
        filename = path.lstrip("/\\")
        # Resolve the candidate path and ensure it remains inside MEDIA_DIR to
        # avoid ``..`` traversal or symlink escapes. ``resolve(strict=False)``
        # keeps nonexistent files from raising but still normalizes ``..``.
        try:
            media_root = MEDIA_DIR.resolve()
        except Exception:
            media_root = MEDIA_DIR
        try:
            candidate = (MEDIA_DIR / filename).resolve(strict=False)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid path")

        try:
            relative_path = candidate.relative_to(media_root)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid path")

        rel = f"/static/media/{relative_path.as_posix()}"
        # Build absolute URL for clients so they don't depend on frontend proxying
        try:
            base = str(request.base_url).rstrip("/")
            url = f"{base}{rel}" if base else rel
        except Exception:
            url = rel

    if resolve:
        payload = {"url": url}
        # For local/dev paths, also include the relative path so clients behind a proxy can prefer it
        if not path.startswith("gs://"):
            payload["path"] = rel
        return JSONResponse(payload)
    return RedirectResponse(url)
