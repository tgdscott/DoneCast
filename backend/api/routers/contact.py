"""
Contact form submission endpoint.
Accepts contact form submissions and sends them via email to support.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional
from api.routers.auth import get_current_user
from api.models.user import User
from api.services.mailer import mailer
import logging

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contact", tags=["contact"])


class ContactFormSubmission(BaseModel):
    name: str
    email: EmailStr
    subject: str  # general, technical, billing, feature, bug, account, feedback
    message: str


@router.post("")
def submit_contact_form(
    submission: ContactFormSubmission,
    current_user: Optional[User] = Depends(get_current_user)
):
    """
    Submit a contact form message.
    Sends email to support team with user's inquiry.
    """
    if not submission.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    
    if not submission.message.strip():
        raise HTTPException(status_code=400, detail="Message is required")
    
    # Map subject codes to readable labels
    subject_labels = {
        'general': 'General Inquiry',
        'technical': 'Technical Support',
        'billing': 'Billing Question',
        'feature': 'Feature Request',
        'bug': 'Bug Report',
        'account': 'Account Issue',
        'feedback': 'Feedback'
    }
    
    subject_label = subject_labels.get(submission.subject, 'Contact Form')
    
    # Build email content
    user_info = ""
    if current_user:
        # Get user display name (email is required, full_name optional)
        display_name = getattr(current_user, 'full_name', None) or current_user.email.split('@')[0]
        user_info = f"""
User Account:
- Email: {current_user.email}
- User ID: {current_user.id}
- Name: {display_name}
"""
    
    email_body = f"""
New contact form submission:

From: {submission.name}
Email: {submission.email}
Subject: {subject_label}

{user_info}

Message:
{submission.message}

---
Sent via Podcast Plus Plus contact form
"""
    
    try:
        # Send email to support
        success = mailer.send(
            to="support@podcastplusplus.com",
            subject=f"[Contact Form] {subject_label} - {submission.name}",
            text=email_body
        )
        
        if not success:
            raise Exception("Mailer returned False")
        
        # Send confirmation to user
        confirmation_body = f"""
Hi {submission.name},

Thank you for contacting Podcast Plus Plus! We've received your message and will get back to you as soon as possible.

Your message:
{submission.message}

---
The Podcast Plus Plus Team
https://podcastplusplus.com
"""
        
        mailer.send(
            to=submission.email,
            subject="We received your message - Podcast Plus Plus",
            text=confirmation_body
        )
        
        log.info(f"[contact] Form submitted by {submission.name} ({submission.email}), subject: {subject_label}")
        
        return {"ok": True, "message": "Message sent successfully"}
        
    except Exception as e:
        log.error(f"[contact] Failed to send contact form email: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to send message. Please try again or email us directly at support@podcastplusplus.com"
        )
