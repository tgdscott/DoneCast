from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from sqlalchemy import func

from api.core.database import get_session
from api.models.podcast import Podcast
from api.models.user import User
from api.models.website import PodcastWebsite, PodcastWebsiteStatus
from api.models.website_page import WebsitePage
from api.routers.auth import get_current_user
from api.services import podcast_websites
from api.services.podcast_websites import (
    PodcastWebsiteAIError,
    PodcastWebsiteContent,
    PodcastWebsiteDomainError,
)
from api.services.website_sections import get_section_definition

log = logging.getLogger(__name__)

# Optional import for AI theme generator - don't crash if it fails
try:
    from api.services.ai_theme_generator import generate_complete_theme
except ImportError as e:
    log.warning("AI theme generator not available: %s", e)
    generate_complete_theme = None

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


class WebsiteGenerationRequest(BaseModel):
    design_vibe: Optional[str] = Field(default=None, description="Desired visual vibe (e.g. 'Modern', 'Retro')")
    color_preference: Optional[str] = Field(default=None, description="Specific color preferences")
    additional_notes: Optional[str] = Field(default=None, description="Other design notes")
    host_bio: str = Field(..., min_length=50, description="Required host bio to prefill the website")


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
    req: Optional[WebsiteGenerationRequest] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    podcast = _load_podcast(session, podcast_id, current_user)
    try:
        # Convert request model to dict if present
        design_prefs = req.dict() if req else {}
        website, content = podcast_websites.create_or_refresh_site(session, podcast, current_user, design_prefs=design_prefs)
    except PodcastWebsiteAIError as exc:
        log.exception("Failed to regenerate website with AI: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc) or "AI website generation failed")
    except Exception as exc:
        log.exception("Unexpected error during website regeneration: %s", exc)
        raise HTTPException(status_code=500, detail=f"Website regeneration failed: {str(exc)}")
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


@router.post("/generate-ai-theme")
def generate_ai_theme(
    podcast_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Analyze podcast and generate a complete themed design.
    
    This endpoint:
    1. Analyzes the podcast (name, description, cover art, tone)
    2. Generates a theme specification (colors, fonts, motifs, animations)
    3. Maps the theme to building blocks (sections)
    4. Generates custom CSS that styles the blocks
    5. Applies the theme to the website
    """
    if generate_complete_theme is None:
        raise HTTPException(
            status_code=503,
            detail="AI theme generator is not available. Please check server logs."
        )
    
    podcast = _load_podcast(session, podcast_id, current_user)
    
    # Ensure website exists
    website = session.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    if website is None:
        # Create website if it doesn't exist
        from api.services.podcast_websites import create_or_refresh_site
        website, _ = create_or_refresh_site(session, podcast, current_user)
        session.commit()
        session.refresh(website)
    
    # Get cover URL and tagline for better analysis
    cover_url, _ = podcast_websites._derive_visual_identity(podcast)
    tagline = None  # Could extract from description or add as separate field
    
    try:
        # Generate complete theme
        theme_result = generate_complete_theme(podcast, cover_url, tagline)
        
        # Apply theme to website - ONLY update theme-related config, preserve structure
        current_config = website.get_sections_config()
        
        # Only update theme metadata and section styling, don't change section structure
        for section_id, section_config in theme_result.sections_config.get("sections_config", {}).items():
            if section_id == "_theme_metadata":
                # Always update theme metadata
                current_config[section_id] = section_config
            elif section_id in current_config:
                # Merge styling/config but preserve existing structure
                # Only update style-related fields, not content/structure
                existing = current_config[section_id]
                # Merge only theme-related fields (colors, styles, etc.)
                # Don't overwrite headings, content, or structural settings
                style_fields = ['background_color', 'text_color', 'style', 'variant', 'layout', 'show_cover_art']
                for field in style_fields:
                    if field in section_config:
                        existing[field] = section_config[field]
            else:
                # New section config - add it
                current_config[section_id] = section_config
        
        website.set_sections_config(current_config)
        
        # DO NOT update sections_order - preserve user's section arrangement
        # if theme_result.sections_config.get("sections_order"):
        #     website.set_sections_order(theme_result.sections_config["sections_order"])
        
        # Apply CSS (this is the main theme change)
        website.global_css = theme_result.css
        
        # Update timestamp
        website.updated_at = datetime.utcnow()
        
        session.add(website)
        session.commit()
        session.refresh(website)
        
        return {
            "message": "AI theme generated and applied successfully",
            "description": theme_result.description,
            "theme_spec": theme_result.theme_spec.dict(),
            "sections_config": theme_result.sections_config,
            "css_preview": theme_result.css[:500] + "..." if len(theme_result.css) > 500 else theme_result.css
        }
        
    except Exception as e:
        log.exception("Failed to generate AI theme: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate AI theme: {str(e)}"
        )


@router.post("/reset")
def reset_website(
    podcast_id: UUID,
    req: ResetWebsiteRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Reset website to default settings. Requires confirmation phrase 'here comes the boom'."""
    # Validate inputs
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
    
    # Get cover URL and theme - use defaults if extraction fails
    cover_url = None
    theme = None
    try:
        cover_url, theme = podcast_websites._derive_visual_identity(podcast)
    except Exception as e:
        log.warning("Failed to derive visual identity during reset: %s", e)
        # Continue with None values - defaults will be used
    
    # Create default sections - this should always succeed
    sections_order, sections_config, sections_enabled = podcast_websites._create_default_sections(
        podcast, cover_url, theme
    )
    
    # Generate CSS from theme or use defaults
    css = None
    if theme:
        try:
            css = podcast_websites._generate_css_from_theme(theme, podcast.name)
        except Exception as e:
            log.warning("Failed to generate CSS from theme: %s", e)
    
    if not css:
        # Use default theme for CSS generation
        default_theme = {
            "primary_color": "#0f172a",
            "secondary_color": "#ffffff",
            "accent_color": "#2563eb",
            "background_color": "#f8fafc",
            "text_color": "#ffffff",
            "mood": "balanced",
        }
        try:
            css = podcast_websites._generate_css_from_theme(default_theme, podcast.name)
        except Exception as e:
            log.warning("Failed to generate default CSS: %s", e)
            css = None
    
    # Apply all changes to website
    website.set_sections_order(sections_order)
    website.set_sections_config(sections_config)
    website.set_sections_enabled(sections_enabled)
    website.global_css = css
    website.layout_json = "{}"  # Clear legacy layout
    website.status = PodcastWebsiteStatus.draft
    website.updated_at = datetime.utcnow()
    
    # Delete all pages (reset to single-page site)
    pages = session.exec(select(WebsitePage).where(WebsitePage.website_id == website.id)).all()
    for page in pages:
        session.delete(page)
    
    # Save changes
    session.add(website)
    session.commit()
    session.refresh(website)
    
    return _serialize_response(website)


# ============================================================================
# Multi-Page Support Endpoints
# ============================================================================

class CreatePageRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="Page title")
    slug: Optional[str] = Field(None, max_length=200, description="URL slug (auto-generated from title if not provided)")
    is_home: bool = Field(default=False, description="Whether this is the home page")


class UpdatePageRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    slug: Optional[str] = Field(None, max_length=200)
    is_home: Optional[bool] = None
    order: Optional[int] = None


class PageResponse(BaseModel):
    id: UUID
    website_id: UUID
    title: str
    slug: str
    is_home: bool
    order: int
    sections_order: List[str]
    sections_config: Dict[str, Dict[str, Any]]
    sections_enabled: Dict[str, bool]
    created_at: datetime
    updated_at: datetime


def _slugify_page_title(title: str) -> str:
    """Generate URL-friendly slug from page title."""
    import re
    slug = title.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug[:200]


@router.get("/pages", response_model=List[PageResponse])
def list_pages(
    podcast_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """List all pages for a website."""
    podcast = _load_podcast(session, podcast_id, current_user)
    website = session.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    if website is None:
        raise HTTPException(status_code=404, detail="Website not created yet")
    
    pages = session.exec(select(WebsitePage).where(WebsitePage.website_id == website.id).order_by(WebsitePage.order, WebsitePage.created_at)).all()
    
    return [
        PageResponse(
            id=page.id,
            website_id=page.website_id,
            title=page.title,
            slug=page.slug,
            is_home=page.is_home,
            order=page.order,
            sections_order=page.get_sections_order(),
            sections_config=page.get_sections_config(),
            sections_enabled=page.get_sections_enabled(),
            created_at=page.created_at,
            updated_at=page.updated_at,
        )
        for page in pages
    ]


@router.post("/pages", response_model=PageResponse, status_code=201)
def create_page(
    podcast_id: UUID,
    req: CreatePageRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Create a new page for the website."""
    podcast = _load_podcast(session, podcast_id, current_user)
    website = session.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    if website is None:
        raise HTTPException(status_code=404, detail="Website not created yet")
    
    # Generate slug if not provided
    slug = req.slug or _slugify_page_title(req.title)
    
    # Ensure slug is unique
    existing = session.exec(select(WebsitePage).where(WebsitePage.website_id == website.id, WebsitePage.slug == slug)).first()
    if existing:
        counter = 1
        base_slug = slug
        while existing:
            slug = f"{base_slug}-{counter}"
            existing = session.exec(select(WebsitePage).where(WebsitePage.website_id == website.id, WebsitePage.slug == slug)).first()
            counter += 1
    
    # If this is set as home, unset other home pages
    if req.is_home:
        other_home = session.exec(select(WebsitePage).where(WebsitePage.website_id == website.id, WebsitePage.is_home == True)).first()
        if other_home:
            other_home.is_home = False
            session.add(other_home)
    
    # Get max order for positioning
    # func.max() always returns exactly one row (even if None), so .first() is safe
    max_order_result = session.exec(select(func.max(WebsitePage.order)).where(WebsitePage.website_id == website.id)).first()
    max_order = max_order_result if max_order_result is not None else 0
    
    page = WebsitePage(
        website_id=website.id,
        title=req.title,
        slug=slug,
        is_home=req.is_home,
        order=max_order + 1,
    )
    
    session.add(page)
    session.commit()
    session.refresh(page)
    
    return PageResponse(
        id=page.id,
        website_id=page.website_id,
        title=page.title,
        slug=page.slug,
        is_home=page.is_home,
        order=page.order,
        sections_order=page.get_sections_order(),
        sections_config=page.get_sections_config(),
        sections_enabled=page.get_sections_enabled(),
        created_at=page.created_at,
        updated_at=page.updated_at,
    )


@router.get("/pages/{page_id}", response_model=PageResponse)
def get_page(
    podcast_id: UUID,
    page_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get a specific page."""
    podcast = _load_podcast(session, podcast_id, current_user)
    website = session.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    if website is None:
        raise HTTPException(status_code=404, detail="Website not created yet")
    
    page = session.exec(select(WebsitePage).where(WebsitePage.id == page_id, WebsitePage.website_id == website.id)).first()
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    
    return PageResponse(
        id=page.id,
        website_id=page.website_id,
        title=page.title,
        slug=page.slug,
        is_home=page.is_home,
        order=page.order,
        sections_order=page.get_sections_order(),
        sections_config=page.get_sections_config(),
        sections_enabled=page.get_sections_enabled(),
        created_at=page.created_at,
        updated_at=page.updated_at,
    )


@router.patch("/pages/{page_id}", response_model=PageResponse)
def update_page(
    podcast_id: UUID,
    page_id: UUID,
    req: UpdatePageRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update a page."""
    podcast = _load_podcast(session, podcast_id, current_user)
    website = session.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    if website is None:
        raise HTTPException(status_code=404, detail="Website not created yet")
    
    page = session.exec(select(WebsitePage).where(WebsitePage.id == page_id, WebsitePage.website_id == website.id)).first()
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    
    if req.title is not None:
        page.title = req.title
    if req.slug is not None:
        # Check slug uniqueness
        existing = session.exec(select(WebsitePage).where(WebsitePage.website_id == website.id, WebsitePage.slug == req.slug, WebsitePage.id != page_id)).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Slug '{req.slug}' is already in use")
        page.slug = req.slug
    if req.is_home is not None:
        if req.is_home:
            # Unset other home pages
            other_home = session.exec(select(WebsitePage).where(WebsitePage.website_id == website.id, WebsitePage.is_home == True, WebsitePage.id != page_id)).first()
            if other_home:
                other_home.is_home = False
                session.add(other_home)
        page.is_home = req.is_home
    if req.order is not None:
        page.order = req.order
    
    page.updated_at = datetime.utcnow()
    session.add(page)
    session.commit()
    session.refresh(page)
    
    return PageResponse(
        id=page.id,
        website_id=page.website_id,
        title=page.title,
        slug=page.slug,
        is_home=page.is_home,
        order=page.order,
        sections_order=page.get_sections_order(),
        sections_config=page.get_sections_config(),
        sections_enabled=page.get_sections_enabled(),
        created_at=page.created_at,
        updated_at=page.updated_at,
    )


@router.delete("/pages/{page_id}", status_code=204)
def delete_page(
    podcast_id: UUID,
    page_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Delete a page."""
    podcast = _load_podcast(session, podcast_id, current_user)
    website = session.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    if website is None:
        raise HTTPException(status_code=404, detail="Website not created yet")
    
    page = session.exec(select(WebsitePage).where(WebsitePage.id == page_id, WebsitePage.website_id == website.id)).first()
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    
    if page.is_home:
        raise HTTPException(status_code=400, detail="Cannot delete the home page")
    
    session.delete(page)
    session.commit()
    return None
