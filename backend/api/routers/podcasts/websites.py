from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
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
from api.services.website_sections import get_section_definition

log = logging.getLogger(__name__)

router = APIRouter(prefix="/{podcast_id}/website", tags=["Podcast Websites"])


class PodcastWebsiteResponse(BaseModel):
    id: UUID
    podcast_id: UUID
    subdomain: str
    global_css: Optional[str] = None
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


class SectionOrderRequest(BaseModel):
    section_ids: List[str] = Field(..., description="Ordered list of section IDs")


class SectionConfigRequest(BaseModel):
    config: Dict[str, Any] = Field(..., description="Section configuration object")


class SectionToggleRequest(BaseModel):
    enabled: bool = Field(..., description="Enable or disable the section")


class SectionRefineRequest(BaseModel):
    instruction: str = Field(..., min_length=1, description="AI instruction for refining this section")


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
        global_css=website.global_css,
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


# ============================================================================
# Section Management Endpoints
# ============================================================================

@router.get("/sections")
def get_sections(
    podcast_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get current section configuration for the website."""
    podcast = _load_podcast(session, podcast_id, current_user)
    website = session.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    if website is None:
        raise HTTPException(status_code=404, detail="Website not created yet")
    
    return {
        "sections_order": website.get_sections_order(),
        "sections_config": website.get_sections_config(),
        "sections_enabled": website.get_sections_enabled(),
    }


@router.patch("/sections/order")
def reorder_sections(
    podcast_id: UUID,
    req: SectionOrderRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update the display order of sections."""
    podcast = _load_podcast(session, podcast_id, current_user)
    website = session.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    if website is None:
        raise HTTPException(status_code=404, detail="Website not created yet")
    
    # Validate that all section IDs are valid
    for section_id in req.section_ids:
        if get_section_definition(section_id) is None:
            raise HTTPException(status_code=400, detail=f"Invalid section ID: {section_id}")
    
    website.set_sections_order(req.section_ids)
    session.add(website)
    session.commit()
    session.refresh(website)
    
    return {
        "sections_order": website.get_sections_order(),
        "message": "Section order updated successfully"
    }


@router.patch("/sections/{section_id}/config")
def update_section_config(
    podcast_id: UUID,
    section_id: str,
    req: SectionConfigRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update configuration for a specific section."""
    podcast = _load_podcast(session, podcast_id, current_user)
    website = session.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    if website is None:
        raise HTTPException(status_code=404, detail="Website not created yet")
    
    # Validate section exists
    section_def = get_section_definition(section_id)
    if section_def is None:
        raise HTTPException(status_code=404, detail=f"Section not found: {section_id}")
    
    website.update_section_config(section_id, req.config)
    session.add(website)
    session.commit()
    session.refresh(website)
    
    return {
        "section_id": section_id,
        "config": website.get_sections_config().get(section_id, {}),
        "message": "Section configuration updated successfully"
    }


@router.patch("/sections/{section_id}/toggle")
def toggle_section(
    podcast_id: UUID,
    section_id: str,
    req: SectionToggleRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Enable or disable a specific section."""
    podcast = _load_podcast(session, podcast_id, current_user)
    website = session.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    if website is None:
        raise HTTPException(status_code=404, detail="Website not created yet")
    
    # Validate section exists
    section_def = get_section_definition(section_id)
    if section_def is None:
        raise HTTPException(status_code=404, detail=f"Section not found: {section_id}")
    
    website.toggle_section(section_id, req.enabled)
    session.add(website)
    session.commit()
    session.refresh(website)
    
    return {
        "section_id": section_id,
        "enabled": req.enabled,
        "message": f"Section {'enabled' if req.enabled else 'disabled'} successfully"
    }


@router.post("/sections/{section_id}/refine")
def refine_section(
    podcast_id: UUID,
    section_id: str,
    req: SectionRefineRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Use AI to refine a specific section's content."""
    podcast = _load_podcast(session, podcast_id, current_user)
    website = session.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    if website is None:
        raise HTTPException(status_code=404, detail="Website not created yet")
    
    # Validate section exists
    section_def = get_section_definition(section_id)
    if section_def is None:
        raise HTTPException(status_code=404, detail=f"Section not found: {section_id}")
    
    # TODO: Implement AI refinement logic
    # This will call a new service function that:
    # 1. Gets current section config
    # 2. Builds context-aware AI prompt using section's ai_prompt_hints
    # 3. Calls Gemini with the refinement instruction
    # 4. Updates section config with AI-generated improvements
    
    raise HTTPException(
        status_code=501,
        detail="AI section refinement coming soon - implement in podcast_websites service"
    )


# ============================================================================
# CSS & Styling Endpoints
# ============================================================================

class UpdateCSSRequest(BaseModel):
    css: str = Field(..., description="Custom CSS to apply to the website")
    ai_prompt: Optional[str] = Field(None, description="Optional AI prompt for CSS generation")


class ResetWebsiteRequest(BaseModel):
    confirmation_phrase: str = Field(..., description="Must be 'here comes the boom' to confirm reset")


@router.patch("/css")
def update_css(
    podcast_id: UUID,
    req: UpdateCSSRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update the global CSS for the website."""
    podcast = _load_podcast(session, podcast_id, current_user)
    website = session.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    if website is None:
        raise HTTPException(status_code=404, detail="Website not created yet")
    
    if req.ai_prompt:
        # Use AI to generate CSS based on the prompt
        try:
            theme = website.parsed_layout().get("theme", {})
            css = podcast_websites.generate_css_with_ai(podcast, theme, req.ai_prompt)
            website.global_css = css
        except podcast_websites.PodcastWebsiteAIError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
    else:
        # Direct CSS update
        website.global_css = req.css
    
    website.updated_at = datetime.utcnow()
    session.add(website)
    session.commit()
    session.refresh(website)
    
    return {
        "message": "CSS updated successfully",
        "css": website.global_css
    }


@router.get("/css")
def get_css(
    podcast_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get the current global CSS for the website."""
    podcast = _load_podcast(session, podcast_id, current_user)
    website = session.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    if website is None:
        raise HTTPException(status_code=404, detail="Website not created yet")
    
    return {
        "css": website.global_css or ""
    }


@router.post("/reset")
def reset_website(
    podcast_id: UUID,
    req: ResetWebsiteRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Reset website to default settings. Requires confirmation phrase 'here comes the boom'."""
    podcast = _load_podcast(session, podcast_id, current_user)
    website = session.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    if website is None:
        raise HTTPException(status_code=404, detail="Website not created yet")
    
    # Verify confirmation phrase
    if req.confirmation_phrase.strip().lower() != "here comes the boom":
        raise HTTPException(
            status_code=400,
            detail="Invalid confirmation phrase. Type 'here comes the boom' to confirm reset."
        )
    
    # Reset to default state
    try:
        cover_url, theme = podcast_websites._derive_visual_identity(podcast)
        sections_order, sections_config, sections_enabled = podcast_websites._create_default_sections(podcast, cover_url, theme)
        
        website.set_sections_order(sections_order)
        website.set_sections_config(sections_config)
        website.set_sections_enabled(sections_enabled)
        
        # Regenerate CSS from theme
        if theme:
            css = podcast_websites._generate_css_from_theme(theme, podcast.name)
            website.global_css = css
        else:
            website.global_css = None
        
        # Reset layout to default
        user = current_user
        _, content = podcast_websites.create_or_refresh_site(session, podcast, user)
        
        website.status = PodcastWebsiteStatus.draft
        website.updated_at = datetime.utcnow()
        session.add(website)
        session.commit()
        session.refresh(website)
        
        return _serialize_response(website, content)
    except Exception as exc:
        log.exception("Failed to reset website for podcast %s: %s", podcast_id, exc)
        raise HTTPException(status_code=500, detail="Failed to reset website")
