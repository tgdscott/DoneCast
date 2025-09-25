from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import text as _sa_text
from sqlmodel import Session, select

from api.models.podcast import MediaItem, MediaCategory
from api.models.user import User
from api.core.database import get_session
from api.core.auth import get_current_user

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

