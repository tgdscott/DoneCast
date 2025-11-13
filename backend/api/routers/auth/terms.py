"""Routes exposing policy and terms information."""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from api.core import crud
from api.core.config import settings
from api.core.database import get_session
from api.core.ip_utils import get_client_ip
from api.models.user import User, UserPublic
from api.models.assistant import FeedbackSubmission

from .utils import get_current_user, to_user_public

router = APIRouter()
log = logging.getLogger(__name__)

# Email configuration (same as assistant.py)
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", getattr(settings, "ADMIN_EMAIL", "admin@podcastplusplus.com"))
SMTP_HOST = os.getenv("SMTP_HOST", getattr(settings, "SMTP_HOST", "smtp.mailgun.org"))
SMTP_PORT = int(os.getenv("SMTP_PORT", getattr(settings, "SMTP_PORT", "587")))
SMTP_USER = os.getenv("SMTP_USER", getattr(settings, "SMTP_USER", ""))
SMTP_PASSWORD = os.getenv("SMTP_PASS", os.getenv("SMTP_PASSWORD", getattr(settings, "SMTP_PASSWORD", "")))


class TermsInfo(BaseModel):
    version: str
    url: str


class TermsAcceptRequest(BaseModel):
    version: str | None = None


class TermsConcernRequest(BaseModel):
    concern: str


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
    
    # Get the real client IP address (handles Cloud Run proxy)
    ip = get_client_ip(request)
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


def _send_tos_concern_email(concern: str, user: User, terms_version: str) -> None:
    """Send email notification to admin when user submits ToS concern."""
    if not SMTP_USER or not SMTP_PASSWORD:
        log.warning("SMTP not configured - skipping ToS concern email notification")
        return
    
    try:
        from datetime import datetime
        current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        last_accepted = user.terms_accepted_at.strftime('%Y-%m-%d %H:%M:%S UTC') if user.terms_accepted_at else 'Never'
        
        # Create email
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"Terms of Service Concern from {user.email}"
        msg['From'] = SMTP_USER
        msg['To'] = ADMIN_EMAIL
        
        # Create HTML body
        html = f"""
        <html>
        <body>
            <h2 style="color: #d32f2f;">📋 Terms of Service Concern</h2>
            <p><strong>User:</strong> {user.first_name or 'Unknown'} ({user.email})</p>
            <p><strong>Terms Version:</strong> {terms_version}</p>
            <p><strong>Last Accepted Terms:</strong> {last_accepted}</p>
            <p><strong>Concern Submitted:</strong> {current_time}</p>
            <hr>
            <h3>User's Concern:</h3>
            <p style="white-space: pre-wrap;">{concern}</p>
            <hr>
            <p><em>This concern was submitted when the user declined to accept the updated Terms of Service.</em></p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html, 'html'))
        
        # Send via SMTP
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        log.info(f"ToS concern email sent for user {user.email}")
    except Exception as e:
        log.error(f"Failed to send ToS concern email: {e}")


@router.post("/terms/concern")
async def submit_terms_concern(
    payload: TermsConcernRequest,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Submit a concern about the Terms of Service.
    
    This endpoint is called when a user declines to accept the updated terms.
    The concern is saved as a feedback submission and emailed to the admin.
    """
    
    if not payload.concern or not payload.concern.strip():
        raise HTTPException(status_code=400, detail="Concern message is required")
    
    terms_version = str(getattr(settings, "TERMS_VERSION", ""))
    user_agent = request.headers.get("user-agent", "") if request and request.headers else None
    
    # Get page URL from referer if available
    page_url = request.headers.get("referer") or "/terms"
    
    # Create feedback submission for ToS concern
    feedback = FeedbackSubmission(
        user_id=current_user.id,
        conversation_id=None,
        type="tos_concern",
        title=f"Terms of Service Concern - Version {terms_version}",
        description=payload.concern.strip(),
        severity="medium",
        page_url=page_url,
        user_action="declined_terms_acceptance",
        browser_info=user_agent,
        error_logs=None,
    )
    
    session.add(feedback)
    session.commit()
    session.refresh(feedback)
    
    # Send email notification to admin
    try:
        _send_tos_concern_email(payload.concern.strip(), current_user, terms_version)
        feedback.admin_notified = True
        session.add(feedback)
        session.commit()
    except Exception as e:
        log.error(f"Failed to send ToS concern email: {e}")
        # Continue anyway - email is nice-to-have
    
    log.info(f"ToS concern submitted: {feedback.id} by {current_user.email}")
    
    return {
        "id": str(feedback.id),
        "message": "Thank you for your feedback. Someone will review your concern and get back to you soon to address it."
    }
