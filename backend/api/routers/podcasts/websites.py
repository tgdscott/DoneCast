from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from api.core.database import get_session
from api.models.podcast import Podcast
from api.models.user import User
from api.models.website import PodcastWebsite, PodcastWebsiteStatus
from api.routers.auth import get_current_user
from api.services import podcast_websites
from api.services.podcast_websites import (
    PodcastWebsiteAIError,
    PodcastWebsiteContent,
    PodcastWebsiteDomainError,
)

router = APIRouter(prefix="/{podcast_id}/website", tags=["Podcast Websites"])


class PodcastWebsiteResponse(BaseModel):
    id: UUID
    podcast_id: UUID
    subdomain: str
    default_domain: str
    custom_domain: Optional[str] = None
    status: PodcastWebsiteStatus
    layout: PodcastWebsiteContent
    last_generated_at: Optional[datetime] = None
    prompt_log_path: Optional[str] = None

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class WebsiteChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Instruction for the AI site builder")


class CustomDomainRequest(BaseModel):
    custom_domain: Optional[str] = Field(default=None, description="Fully qualified domain or None to remove")


def _load_podcast(session: Session, podcast_id: UUID, user: User) -> Podcast:
    stmt = select(Podcast).where(Podcast.id == podcast_id, Podcast.user_id == user.id)
    podcast = session.exec(stmt).first()
    if podcast is None:
        raise HTTPException(status_code=404, detail="Podcast not found")
    return podcast


def _serialize_response(website: PodcastWebsite, content: Optional[PodcastWebsiteContent] = None) -> PodcastWebsiteResponse:
    payload = content or PodcastWebsiteContent(**website.parsed_layout())
    return PodcastWebsiteResponse(
        id=website.id,
        podcast_id=website.podcast_id,
        subdomain=website.subdomain,
        default_domain=podcast_websites.get_default_domain(website.subdomain),
        custom_domain=website.custom_domain,
        status=website.status,
        layout=payload,
        last_generated_at=website.last_generated_at,
        prompt_log_path=website.prompt_log_path,
    )


@router.get("", response_model=PodcastWebsiteResponse)
def get_website(
    podcast_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    podcast = _load_podcast(session, podcast_id, current_user)
    website = session.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    if website is None:
        raise HTTPException(status_code=404, detail="Website not created yet")
    return _serialize_response(website)


@router.post("", response_model=PodcastWebsiteResponse)
def generate_website(
    podcast_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    podcast = _load_podcast(session, podcast_id, current_user)
    try:
        website, content = podcast_websites.create_or_refresh_site(session, podcast, current_user)
    except PodcastWebsiteAIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return _serialize_response(website, content)


@router.post("/chat", response_model=PodcastWebsiteResponse)
def chat_with_builder(
    podcast_id: UUID,
    req: WebsiteChatRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    podcast = _load_podcast(session, podcast_id, current_user)
    website = session.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    if website is None:
        raise HTTPException(status_code=404, detail="Website not created yet")
    try:
        updated, content = podcast_websites.apply_ai_update(session, website, podcast, current_user, req.message)
    except PodcastWebsiteAIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return _serialize_response(updated, content)


@router.patch("/domain", response_model=PodcastWebsiteResponse)
def update_domain(
    podcast_id: UUID,
    req: CustomDomainRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    podcast = _load_podcast(session, podcast_id, current_user)
    website = session.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    if website is None:
        raise HTTPException(status_code=404, detail="Website not created yet")
    try:
        updated = podcast_websites.update_custom_domain(session, website, current_user, req.custom_domain)
    except PodcastWebsiteDomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _serialize_response(updated)
