"""
Website publishing endpoints with automatic domain provisioning.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel

from api.core.database import get_session
from api.models.podcast import Podcast
from api.models.website import PodcastWebsite, PodcastWebsiteStatus
from api.routers.auth import get_current_user
from api.services.domain_mapping import provision_subdomain, check_domain_status, DomainMappingError


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/podcasts", tags=["Website Publishing"])


class PublishWebsiteRequest(BaseModel):
    """Request to publish a podcast website."""
    auto_provision_domain: bool = True  # Automatically create subdomain mapping


class PublishWebsiteResponse(BaseModel):
    """Response from publishing a website."""
    success: bool
    status: str
    message: str
    domain: str | None = None
    ssl_status: str | None = None
    estimated_ready_time: str | None = None


class DomainStatusResponse(BaseModel):
    """Domain mapping and SSL certificate status."""
    domain: str
    status: str
    ssl_status: str
    message: str
    is_ready: bool


@router.post("/{podcast_id}/website/publish", response_model=PublishWebsiteResponse)
async def publish_website(
    podcast_id: str,
    request: PublishWebsiteRequest,
    db: Session = Depends(get_session),
    user=Depends(get_current_user)
):
    """
    Publish a podcast website and optionally provision its subdomain.
    
    This will:
    1. Set website status to "published"
    2. Optionally create Cloud Run domain mapping (FREE SSL cert)
    3. SSL cert takes 10-15 minutes to provision
    
    **Note:** Domain provisioning is asynchronous. The website will be accessible
    once the SSL certificate is ready (~10-15 minutes).
    """
    # Get podcast
    podcast = db.exec(
        select(Podcast).where(Podcast.id == podcast_id, Podcast.user_id == user.id)
    ).first()
    
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    # Get website
    website = db.exec(
        select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast_id)
    ).first()
    
    if not website:
        raise HTTPException(status_code=404, detail="Website not created yet")
    
    if not website.subdomain:
        raise HTTPException(status_code=400, detail="Website subdomain not set")
    
    # Update website status to published
    website.status = PodcastWebsiteStatus.PUBLISHED
    db.add(website)
    db.commit()
    db.refresh(website)
    
    # Optionally provision domain mapping
    domain_info = None
    if request.auto_provision_domain:
        try:
            logger.info(f"Provisioning domain mapping for {website.subdomain}")
            domain_info = await provision_subdomain(website.subdomain)
            
            return PublishWebsiteResponse(
                success=True,
                status="published",
                message="Website published successfully. SSL certificate is being provisioned.",
                domain=domain_info["domain"],
                ssl_status=domain_info["ssl_status"],
                estimated_ready_time="10-15 minutes"
            )
            
        except DomainMappingError as e:
            logger.error(f"Domain provisioning failed for {website.subdomain}: {e}")
            # Website is still published, just warn about domain
            return PublishWebsiteResponse(
                success=True,
                status="published",
                message=f"Website published but domain provisioning failed: {str(e)}",
                domain=f"{website.subdomain}.podcastplusplus.com",
                ssl_status="error"
            )
    
    return PublishWebsiteResponse(
        success=True,
        status="published",
        message="Website published successfully (domain provisioning skipped).",
        domain=f"{website.subdomain}.podcastplusplus.com"
    )


@router.post("/{podcast_id}/website/unpublish")
async def unpublish_website(
    podcast_id: str,
    db: Session = Depends(get_session),
    user=Depends(get_current_user)
):
    """
    Unpublish a podcast website (set back to draft).
    
    **Note:** This does NOT delete the domain mapping. The subdomain will still
    resolve to the site, but the API will return 404 for published endpoint.
    """
    # Get podcast
    podcast = db.exec(
        select(Podcast).where(Podcast.id == podcast_id, Podcast.user_id == user.id)
    ).first()
    
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    # Get website
    website = db.exec(
        select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast_id)
    ).first()
    
    if not website:
        raise HTTPException(status_code=404, detail="Website not created yet")
    
    # Update status to draft
    website.status = PodcastWebsiteStatus.DRAFT
    db.add(website)
    db.commit()
    
    return {"success": True, "message": "Website unpublished successfully"}


@router.get("/{podcast_id}/website/domain-status", response_model=DomainStatusResponse)
async def get_domain_status(
    podcast_id: str,
    db: Session = Depends(get_session),
    user=Depends(get_current_user)
):
    """
    Check the status of a website's domain mapping and SSL certificate.
    
    Use this to poll for SSL certificate readiness after publishing.
    """
    # Get podcast
    podcast = db.exec(
        select(Podcast).where(Podcast.id == podcast_id, Podcast.user_id == user.id)
    ).first()
    
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    # Get website
    website = db.exec(
        select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast_id)
    ).first()
    
    if not website:
        raise HTTPException(status_code=404, detail="Website not created yet")
    
    if not website.subdomain:
        raise HTTPException(status_code=400, detail="Website subdomain not set")
    
    # Check domain status
    status_info = await check_domain_status(website.subdomain)
    
    is_ready = (
        status_info["status"] == "active" and 
        status_info["ssl_status"] == "active"
    )
    
    return DomainStatusResponse(
        domain=status_info["domain"],
        status=status_info["status"],
        ssl_status=status_info["ssl_status"],
        message=status_info["message"],
        is_ready=is_ready
    )
