from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from api.core.database import get_session
from api.models.onboarding import OnboardingSession
from api.models.podcast import Podcast
from api.models.user import User
from api.routers.auth.dependencies import get_current_user


router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class CreateOnboardingSessionRequest(BaseModel):
    podcast_id: UUID


@router.post("/sessions", response_model=OnboardingSession)
def create_session(
    payload: CreateOnboardingSessionRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Create or update an onboarding session for the current user.

    Called when the wizard creates a brand-new podcast. If a session already
    exists, we simply update the associated podcast_id so that only the most
    recent run is eligible for a Start Over reset.
    """

    podcast = session.get(Podcast, payload.podcast_id)
    if not podcast or podcast.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Podcast not found")

    stmt = select(OnboardingSession).where(OnboardingSession.user_id == current_user.id)
    existing = session.exec(stmt).first()

    if existing:
        existing.podcast_id = podcast.id
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    record = OnboardingSession(user_id=current_user.id, podcast_id=podcast.id)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@router.options("/sessions", include_in_schema=False)
def options_sessions() -> Response:
    """Handle CORS preflight checks for onboarding sessions."""
    return Response(status_code=204)


@router.post("/reset")
def reset_current_onboarding(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Blow away everything created in the current onboarding session.

    This is only used for brand-new user onboarding. We:
      - Look up the user's OnboardingSession
      - Delete the associated podcast (cascades episodes, media, distribution)
      - Delete the OnboardingSession itself
    Existing podcasts or assets outside this session are untouched.
    """

    stmt = select(OnboardingSession).where(OnboardingSession.user_id == current_user.id)
    record = session.exec(stmt).first()
    if not record:
        return {"status": "ok", "reset": False}

    if record.podcast_id:
        podcast = session.get(Podcast, record.podcast_id)
        if podcast and podcast.user_id == current_user.id:
            session.delete(podcast)

    session.delete(record)
    session.commit()
    return {"status": "ok", "reset": True}

