"""Routes exposing policy and terms information."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from api.core import crud
from api.core.config import settings
from api.core.database import get_session
from api.models.user import User, UserPublic

from .utils import get_current_user, to_user_public

router = APIRouter()


class TermsInfo(BaseModel):
    version: str
    url: str


class TermsAcceptRequest(BaseModel):
    version: str | None = None


@router.get("/terms/info", response_model=TermsInfo)
async def get_terms_info() -> TermsInfo:
    """Return the current Terms of Use version and URL."""

    return TermsInfo(
        version=str(getattr(settings, "TERMS_VERSION", "")),
        url=str(getattr(settings, "TERMS_URL", "/terms")),
    )


@router.post("/terms/accept", response_model=UserPublic)
async def accept_terms(
    payload: TermsAcceptRequest,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> UserPublic:
    """Record acceptance of the current Terms of Use for the authenticated user."""

    required = str(getattr(settings, "TERMS_VERSION", ""))
    version = (payload.version or "").strip() or required
    if not required:
        raise HTTPException(status_code=500, detail="Server missing TERMS_VERSION configuration")
    if version != required:
        raise HTTPException(
            status_code=400,
            detail="Terms version mismatch. Please refresh and accept the latest terms.",
        )
    try:
        ip = request.client.host if request and request.client else None
    except Exception:
        ip = None
    ua = request.headers.get("user-agent", "") if request and request.headers else None
    crud.record_terms_acceptance(
        session=session,
        user=current_user,
        version=version,
        ip=ip,
        user_agent=ua,
    )
    session.refresh(current_user)
    return to_user_public(current_user)
