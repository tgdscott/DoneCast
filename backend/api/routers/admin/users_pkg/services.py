from __future__ import annotations

import logging
import os
import json
import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Set
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_, text
from sqlmodel import Session, select, desc as sqlmodel_desc

from api.core import crud
from api.core.database import commit_with_retry
from api.core.config import settings
# Basic Models
from api.models.user import User, UserPublic, UserTermsAcceptance
from api.models.podcast import Episode, Podcast, MediaItem, PodcastTemplate, EpisodeSection, PodcastDistributionStatus
from api.models.transcription import MediaTranscript
from api.models.usage import ProcessingMinutesLedger, LedgerDirection, LedgerReason
from api.models.enums import EpisodeStatus

# Optional Imports handling
try:
    from api.models.website import PodcastWebsite
    WEBSITE_AVAILABLE = True
except ImportError:
    WEBSITE_AVAILABLE = False

try:
    from api.models.subscription import Subscription
    SUBSCRIPTION_AVAILABLE = True
except ImportError:
    SUBSCRIPTION_AVAILABLE = False

try:
    from api.models.notification import Notification
    NOTIFICATION_AVAILABLE = True
except ImportError:
    NOTIFICATION_AVAILABLE = False

try:
    from api.models.assistant import AssistantConversation, AssistantMessage, AssistantGuidance
    ASSISTANT_AVAILABLE = True
except ImportError:
    ASSISTANT_AVAILABLE = False

try:
    from api.models.verification import EmailVerification, OwnershipVerification, PasswordReset
    VERIFICATION_AVAILABLE = True
except ImportError:
    VERIFICATION_AVAILABLE = False

try:
    from api.models.admin_log import AdminActionLog, AdminActionType
    ADMIN_LOG_AVAILABLE = True
except ImportError:
    ADMIN_LOG_AVAILABLE = False
    
# GCS
try:
    from infrastructure.gcs import _get_gcs_client
    GCS_AVAILABLE = True
except Exception:
    GCS_AVAILABLE = False

# Local Schemas
from .schemas import (
    UserAdminOut, UserAdminUpdate, RefundCreditsRequest, AwardCreditsRequest,
    DenyRefundRequest, RefundRequestResponse, RefundRequestDetail,
    UserRefundContext, EpisodeRefundDetail, LedgerEntryDetail,
    RefundLogEntry, CreditAwardLogEntry
)

log = logging.getLogger(__name__)

# Constants
ADMIN_TIERS = {"admin", "superadmin"}
PROTECTED_SUPERADMIN_EMAIL = getattr(settings, 'ADMIN_EMAIL', '').lower()

def get_all_users(session: Session) -> List[UserPublic]:
    return crud.get_all_users(session=session)

def get_users_full(session: Session) -> List[UserAdminOut]:
    counts: Dict[UUID, int] = dict(
        session.exec(select(Episode.user_id, func.count(Episode.id)).group_by(Episode.user_id)).all()
    )
    latest: Dict[UUID, Optional[datetime]] = dict(
        session.exec(select(Episode.user_id, func.max(Episode.processed_at)).group_by(Episode.user_id)).all()
    )
    
    # Get email verification status for each user
    verified_user_ids: Set[UUID] = set()
    if VERIFICATION_AVAILABLE:
        verified_records = session.exec(
            select(EmailVerification.user_id)
            .where(EmailVerification.verified_at != None)
            .distinct()
        ).all()
        verified_user_ids = set(verified_records)

    users = crud.get_all_users(session)
    out: List[UserAdminOut] = []
    for user in users:
        last_activity = latest.get(user.id) or user.created_at
        is_verified = user.id in verified_user_ids or bool(getattr(user, "google_id", None))
        out.append(
            UserAdminOut(
                id=str(user.id),
                email=user.email,
                tier=user.tier,
                is_active=user.is_active,
                created_at=user.created_at.isoformat(),
                episode_count=int(counts.get(user.id, 0)),
                last_activity=last_activity.isoformat() if last_activity else None,
                subscription_expires_at=
                    user.subscription_expires_at.isoformat()
                    if getattr(user, "subscription_expires_at", None)
                    else None,
                last_login=user.last_login.isoformat() if getattr(user, "last_login", None) else None,
                email_verified=is_verified,
            )
        )
    return out

def update_user(
    session: Session, 
    admin_user: User, 
    user_id: UUID, 
    update: UserAdminUpdate
) -> UserAdminOut:
    log.debug("update_user payload user_id=%s %s", str(user_id), update.model_dump())
    user = crud.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Protection: Cannot modify superadmin account
    if user.email and user.email.lower() == PROTECTED_SUPERADMIN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify the primary superadmin account."
        )

    # Get the admin's role
    admin_role = str(getattr(admin_user, "role", "")).lower()
    admin_is_superadmin = admin_role == "superadmin" or (
        admin_user.email and admin_user.email.lower() == PROTECTED_SUPERADMIN_EMAIL
    )

    changed = False
    if update.tier is not None:
        try:
            norm_tier = update.tier.strip().lower()
            if norm_tier == "starter":
                norm_tier = "free"
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid tier value")
        
        if norm_tier in ADMIN_TIERS:
            if not admin_is_superadmin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only superadmin can assign admin or superadmin tiers."
                )
            if norm_tier == "superadmin":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Superadmin tier cannot be assigned. It is reserved for the primary admin account."
                )
            if norm_tier == "admin":
                user.role = "admin"
                user.is_admin = True
                log.info("Setting user %s role to 'admin' and is_admin=True", user_id)
        else:
            if user.role in ("admin", "superadmin") and user.role != "superadmin":
                user.role = None
                user.is_admin = False
                log.info("Clearing admin role for user %s (tier changed to %s)", user_id, norm_tier)
        
        user.tier = norm_tier
        changed = True

    if update.is_active is not None:
        user.is_active = update.is_active
        changed = True

    if update.subscription_expires_at is not None:
        raw = update.subscription_expires_at.strip()
        if raw == "":
            user.subscription_expires_at = None
            changed = True
        else:
            try:
                cleaned = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
                if len(cleaned) == 10 and cleaned.count("-") == 2:
                    user.subscription_expires_at = datetime.fromisoformat(cleaned + "T23:59:59")
                else:
                    user.subscription_expires_at = datetime.fromisoformat(cleaned)
                if user.subscription_expires_at.year < 1900 or user.subscription_expires_at.year > 2100:
                    raise HTTPException(
                        status_code=400,
                        detail="subscription_expires_at year out of acceptable range (1900-2100)",
                    )
                changed = True
            except HTTPException:
                raise
            except Exception as exc:
                log.warning("Bad subscription_expires_at '%s' for user %s: %s", raw, user_id, exc)
                raise HTTPException(
                    status_code=400,
                    detail="Invalid subscription_expires_at format; use YYYY-MM-DD or ISO8601",
                )

    if changed:
        log.info(
            "Admin %s updating user %s; tier=%s is_active=%s sub_expires=%s",
            admin_user.email, user_id, update.tier is not None, update.is_active is not None, update.subscription_expires_at is not None
        )
        session.add(user)
        commit_with_retry(session)
        try:
            session.refresh(user)
        except Exception:
            pass

    episode_count = (
        session.exec(select(func.count(Episode.id)).where(Episode.user_id == user.id)).one() or 0
    )
    last_activity = (
        session.exec(select(func.max(Episode.processed_at)).where(Episode.user_id == user.id)).first()
        or user.created_at
    )
    
    email_verified = False
    if VERIFICATION_AVAILABLE:
        verified_check = session.exec(
            select(EmailVerification.user_id)
            .where(
                EmailVerification.user_id == user.id,
                EmailVerification.verified_at != None
            )
            .limit(1)
        ).first()
        email_verified = verified_check is not None

    return UserAdminOut(
        id=str(user.id),
        email=user.email,
        tier=user.tier,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
        episode_count=int(episode_count),
        last_activity=last_activity.isoformat() if last_activity else None,
        subscription_expires_at=
            user.subscription_expires_at.isoformat()
            if getattr(user, "subscription_expires_at", None)
            else None,
        last_login=user.last_login.isoformat() if getattr(user, "last_login", None) else None,
        email_verified=email_verified,
    )

def verify_user_email(
    session: Session,
    admin_user: User,
    user_id: UUID,
) -> Dict[str, Any]:
    """
    Manually verify a user's email address (Admin only).
    """
    log.info(f"[ADMIN] Manual email verification requested by {admin_user.email} for user_id: {user_id}")
    
    # Find the user
    user = crud.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not VERIFICATION_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail="Email verification system not available"
        )
    
    # Check if user already has a verified email
    existing_verification = session.exec(
        select(EmailVerification)
        .where(
            EmailVerification.user_id == user.id,
            EmailVerification.verified_at != None
        )
        .limit(1)
    ).first()
    
    if existing_verification:
        log.info(f"[ADMIN] User {user.email} already has verified email (verified at {existing_verification.verified_at})")
        return {
            "success": True,
            "user_id": str(user.id),
            "email": user.email,
            "already_verified": True,
            "verified_at": existing_verification.verified_at.isoformat() if existing_verification.verified_at else None,
        }
    
    # Create a new verified EmailVerification record
    now = datetime.utcnow()
    verification = EmailVerification(
        user_id=user.id,
        code="ADMIN-VER",
        jwt_token=None,
        expires_at=now,
        verified_at=now,
        used=True,
        created_at=now,
    )
    
    user.is_active = True
    
    session.add(verification)
    session.add(user)
    commit_with_retry(session)
    session.refresh(verification)
    try:
        session.refresh(user)
    except Exception:
        pass
    
    log.info(f"[ADMIN] Created manual email verification for user {user.email} by admin {admin_user.email} and set is_active=True")
    
    return {
        "success": True,
        "user_id": str(user.id),
        "email": user.email,
        "already_verified": False,
        "verified_at": verification.verified_at.isoformat() if verification.verified_at else None,
        "verified_by_admin": admin_user.email,
        "is_active": user.is_active,
    }

def trigger_password_reset(
    session: Session,
    admin_user: User,
    user_id: UUID,
) -> Dict[str, Any]:
    """
    Trigger a password reset email for a user (Admin only).
    """
    log.info(f"[ADMIN] Password reset trigger requested by {admin_user.email} for user_id: {user_id}")
    
    # Find the user
    user = crud.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Cannot reset password for inactive user")

    # Check if verification/reset system is available
    if not VERIFICATION_AVAILABLE:
        raise HTTPException(status_code=503, detail="Verification system not available")

    # Invalidate existing reset tokens
    try:
        resets = session.exec(
            select(PasswordReset).where(
                PasswordReset.user_id == user.id,
                PasswordReset.used_at == None,
            )
        ).all()
        for reset in resets:
            reset.used_at = datetime.utcnow()
            session.add(reset)
        session.commit()
    except Exception:
        session.rollback()

    # Generate new token
    alphabet = string.ascii_letters + string.digits
    token = "".join(secrets.choice(alphabet) for _ in range(40))
    expires = datetime.utcnow() + timedelta(minutes=30)
    
    # Record the reset request
    pr = PasswordReset(
        user_id=user.id, 
        token=token, 
        expires_at=expires, 
        ip="0.0.0.0",  # Placeholder for admin action
        user_agent=f"Admin Action by {admin_user.email}"
    )
    session.add(pr)
    session.commit()

    # Send the email
    from api.services.mailer import mailer
    
    app_base = (settings.APP_BASE_URL or "https://app.podcastplusplus.com").rstrip("/")
    reset_url = f"{app_base}/reset-password?token={token}"
    subj = "Podcast Plus Plus: Password reset request"
    text_body = (
        "We received a request to reset your password (initiated by support).\n\n"
        f"Reset link (valid 30 minutes): {reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )
    html_body = f"""
    <div style='font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:560px;margin:0 auto;padding:8px 4px;'>
      <h2 style='font-size:20px;margin:0 0 12px;'>Reset your password</h2>
      <p style='font-size:15px;line-height:1.5;margin:0 0 16px;'>An administrator has initiated a password reset for your account. Click the button below to choose a new password. This link expires in 30 minutes.</p>
      <p style='text-align:center;margin:0 0 24px;'>
        <a href='{reset_url}' style='display:inline-block;background:#2563eb;color:#fff;text-decoration:none;padding:12px 20px;border-radius:6px;font-weight:600;'>Choose New Password</a>
      </p>
      <p style='font-size:13px;color:#555;margin:0 0 12px;'>If you didn't request this, you can safely ignore this email.</p>
    <p style='font-size:12px;color:#777;margin:24px 0 0;'>&copy; {datetime.utcnow().year} Podcast Plus Plus</p>
    </div>
    """.strip()
    
    try:
        mailer.send(to=user.email, subject=subj, text=text_body, html=html_body)
        log.info(f"[ADMIN] Password reset email sent to {user.email}")
    except Exception as e:
        log.error(f"[ADMIN] Failed to send password reset email to {user.email}: {e}")
        return {
            "success": True, 
            "message": "Token generated but email failed to send", 
            "token": token,
            "error": str(e)
        }

    return {
        "success": True,
        "message": f"Password reset email sent to {user.email}",
        "user_id": str(user.id)
    }

def delete_user_account(
    session: Session,
    admin_user: User,
    user_id: str,
    confirm_email: str
) -> Dict[str, Any]:
    """
    Delete a user and ALL their associated data.
    """
    admin = admin_user
    log.warning(f"[ADMIN] User deletion requested by {admin.email} for user_id: {user_id}")
    log.info(f"[ADMIN] Deletion confirmation email provided: {confirm_email}")
    
    # Parse UUID
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user_id format. Must be a valid UUID."
        )
    
    # Find the user
    user = session.get(User, user_uuid)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found"
        )
    
    # Safety check: confirm email matches
    if user.email != confirm_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email confirmation failed. Expected '{user.email}' but got '{confirm_email}'"
        )
    
    # Protection: Cannot delete superadmin account
    if user.email and user.email.lower() == PROTECTED_SUPERADMIN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete the primary superadmin account."
        )
    
    # Prevent deletion of other admin users (legacy list for safety)
    admin_emails = ["tom@pluspluspodcasts.com", "tgdscott@gmail.com"]
    if user.email.lower() in admin_emails:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete admin users"
        )
    
    # SAFETY GUARDRAIL: Only allow deletion of inactive AND free tier users
    if user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot delete active user. Please set user to inactive first. (Current status: Active)"
        )
    
    user_tier = (user.tier or "free").strip().lower()
    if user_tier == "starter":
        user_tier = "free"
    # Allow deletion of free/starter tier and admin tier (but not superadmin, protected, or paid tiers)
    if user_tier not in ["free", "", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot delete paid user. User must be on 'starter' or 'admin' tier. (Current tier: {user.tier})"
        )
    
    log.warning(f"[ADMIN] Safety checks passed (inactive + free tier). Confirmed deletion of user: {user.email} ({user.id})")
    
    # Capture user details BEFORE deletion
    user_id_hex = user.id.hex
    user_email_copy = user.email
    user_id_str = str(user.id)
    
    # Count items before deletion (for summary)
    transcript_stmt = (
        select(func.count())
        .select_from(MediaTranscript)
        .join(MediaItem)
        .where(MediaItem.user_id == user.id)
    )
    transcript_count = session.exec(transcript_stmt).one()
    
    media_stmt = select(func.count()).select_from(MediaItem).where(MediaItem.user_id == user.id)
    media_count = session.exec(media_stmt).one()
    
    podcast_stmt = select(func.count()).select_from(Podcast).where(Podcast.user_id == user.id)
    podcast_count = session.exec(podcast_stmt).one()
    
    episode_stmt = select(func.count()).select_from(Episode).where(Episode.user_id == user.id)
    episode_count = session.exec(episode_stmt).one()
    
    section_stmt = select(func.count()).select_from(EpisodeSection).where(EpisodeSection.user_id == user.id)
    section_count = session.exec(section_stmt).one()
    
    template_stmt = select(func.count()).select_from(PodcastTemplate).where(PodcastTemplate.user_id == user.id)
    template_count = session.exec(template_stmt).one()
    
    try:
        # Delete in order (child records first to avoid foreign key issues)
        
        # 1. Media transcripts
        transcripts = session.exec(select(MediaTranscript).join(MediaItem).where(MediaItem.user_id == user.id)).all()
        for transcript in transcripts:
            session.delete(transcript)
        log.info(f"[ADMIN] Deleted {transcript_count} media transcripts for user {user.id}")
        
        # 2. Media items
        media_sp = session.begin_nested()
        try:
            media_items = session.exec(select(MediaItem).where(MediaItem.user_id == user.id)).all()
            for item in media_items:
                session.delete(item)
            session.flush()
            media_sp.commit()
            log.info(f"[ADMIN] Deleted {media_count} media items for user {user.id}")
        except Exception as media_err:
            media_sp.rollback()
            log.error(f"[ADMIN] Failed to delete media items (skipping): {media_err}")
            # If ORM fails, try raw SQL
            try:
                log.info("[ADMIN] Attempting raw SQL deletion for media items...")
                session.execute(text("DELETE FROM mediaitem WHERE user_id = :uid"), {"uid": user.id})
                session.commit()
                log.info(f"[ADMIN] Deleted media items via raw SQL for user {user.id}")
            except Exception as sql_err:
                log.error(f"[ADMIN] Raw SQL deletion failed too: {sql_err}")
        
        # 3. Episode sections
        sections = session.exec(select(EpisodeSection).where(EpisodeSection.user_id == user.id)).all()
        for section in sections:
            session.delete(section)
        log.info(f"[ADMIN] Deleted {section_count} episode sections for user {user.id}")
        
        # 4. Episodes
        episodes = session.exec(select(Episode).where(Episode.user_id == user.id)).all()
        for episode in episodes:
            session.delete(episode)
        log.info(f"[ADMIN] Deleted {episode_count} episodes for user {user.id}")
        
        # 5. Templates
        templates = session.exec(select(PodcastTemplate).where(PodcastTemplate.user_id == user.id)).all()
        for template in templates:
            session.delete(template)
        log.info(f"[ADMIN] Deleted {template_count} templates for user {user.id}")
        
        # 5b. Get podcasts first
        podcasts = session.exec(select(Podcast).where(Podcast.user_id == user.id)).all()
        podcast_ids = [podcast.id for podcast in podcasts]
        
        # 5c. Podcast distribution status
        dist_status_count = 0
        if podcast_ids:
            dist_status_by_user = session.exec(
                select(PodcastDistributionStatus).where(PodcastDistributionStatus.user_id == user.id)
            ).all()
            deleted_dist_ids = {d.id for d in dist_status_by_user}
            for dist_status in dist_status_by_user:
                session.delete(dist_status)
            
            dist_status_by_podcast = session.exec(
                select(PodcastDistributionStatus).where(PodcastDistributionStatus.podcast_id.in_(podcast_ids))
            ).all()
            for dist_status in dist_status_by_podcast:
                if dist_status.id not in deleted_dist_ids:
                    session.delete(dist_status)
                    deleted_dist_ids.add(dist_status.id)
            
            dist_status_count = len(deleted_dist_ids)
            if dist_status_count > 0:
                log.info(f"[ADMIN] Marked {dist_status_count} distribution status records for deletion for user {user.id}")
        
        # 5d. Podcast websites
        website_count = 0
        if WEBSITE_AVAILABLE:
            websites_by_user = session.exec(
                select(PodcastWebsite).where(PodcastWebsite.user_id == user.id)
            ).all()
            deleted_website_ids = {w.id for w in websites_by_user}
            for website in websites_by_user:
                session.delete(website)
            
            if podcast_ids:
                websites_by_podcast = session.exec(
                    select(PodcastWebsite).where(PodcastWebsite.podcast_id.in_(podcast_ids))
                ).all()
                for website in websites_by_podcast:
                    if website.id not in deleted_website_ids:
                        session.delete(website)
                        deleted_website_ids.add(website.id)
            
            website_count = len(deleted_website_ids)
            if website_count > 0:
                log.info(f"[ADMIN] Marked {website_count} website records for deletion for user {user.id}")
        
        # Flush related records
        if dist_status_count > 0 or (WEBSITE_AVAILABLE and website_count > 0):
            session.flush()
        
        # 6. Podcasts
        for podcast in podcasts:
            session.delete(podcast)
        log.info(f"[ADMIN] Deleted {podcast_count} podcasts for user {user.id}")
        
        # 7. Terms acceptance
        terms_acceptances = session.exec(select(UserTermsAcceptance).where(UserTermsAcceptance.user_id == user.id)).all()
        terms_count = len(terms_acceptances)
        for terms in terms_acceptances:
            session.delete(terms)
        log.info(f"[ADMIN] Deleted {terms_count} terms acceptance records for user {user.id}")
        
        # 8. Verification records
        if VERIFICATION_AVAILABLE:
            email_verifications = session.exec(select(EmailVerification).where(EmailVerification.user_id == user.id)).all()
            for ev in email_verifications:
                session.delete(ev)
            ownership_verifications = session.exec(select(OwnershipVerification).where(OwnershipVerification.user_id == user.id)).all()
            for ov in ownership_verifications:
                session.delete(ov)
            password_resets = session.exec(select(PasswordReset).where(PasswordReset.user_id == user.id)).all()
            for pr in password_resets:
                session.delete(pr)
            
        # 9. Subscriptions
        if SUBSCRIPTION_AVAILABLE:
            subscriptions = session.exec(select(Subscription).where(Subscription.user_id == user.id)).all()
            for sub in subscriptions:
                session.delete(sub)
        
        # 10. Notifications
        if NOTIFICATION_AVAILABLE:
            notifications = session.exec(select(Notification).where(Notification.user_id == user.id)).all()
            for notif in notifications:
                session.delete(notif)
        
        # 11. Assistant
        if ASSISTANT_AVAILABLE:
            conversations = session.exec(select(AssistantConversation).where(AssistantConversation.user_id == user.id)).all()
            
            # First pass: Delete messages
            for conv in conversations:
                messages = session.exec(select(AssistantMessage).where(AssistantMessage.conversation_id == conv.id)).all()
                for msg in messages:
                    session.delete(msg)
            
            session.flush()
            
            # Second pass: Delete conversations
            for conv in conversations:
                session.delete(conv)
            
            guidances = session.exec(select(AssistantGuidance).where(AssistantGuidance.user_id == user.id)).all()
            for guide in guidances:
                session.delete(guide)
        
        # 12. User account
        session.delete(user)
        log.warning(f"[ADMIN] Deleted user account: {user_email_copy} ({user_id_str})")
        
        # Commit all deletions
        commit_with_retry(session)
        
        # 14. GCS cleanup
        gcs_deleted_count = 0
        gcs_cleanup_status = "skipped"
        gcs_error = None
        
        if GCS_AVAILABLE:
            try:
                client = _get_gcs_client()
                if client:
                    gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
                    bucket = client.bucket(gcs_bucket)
                    user_prefix = f"{user_id_hex}/"
                    
                    log.info(f"[ADMIN] Cleaning up GCS files for user {user_id_str} (prefix: {user_prefix})")
                    
                    blobs = list(bucket.list_blobs(prefix=user_prefix))
                    
                    if blobs:
                        for blob in blobs:
                            try:
                                blob.delete()
                                gcs_deleted_count += 1
                            except Exception as blob_err:
                                log.warning(f"[ADMIN] Failed to delete blob {blob.name}: {blob_err}")
                        
                        gcs_cleanup_status = "completed"
                        log.info(f"[ADMIN] GCS cleanup complete: deleted {gcs_deleted_count} files for user {user_id_str}")
                    else:
                        gcs_cleanup_status = "no_files"
                        log.info(f"[ADMIN] No GCS files found for user {user_id_str}")
                else:
                    gcs_cleanup_status = "client_unavailable"
                    log.warning("[ADMIN] GCS client unavailable - skipping cleanup")
            except Exception as gcs_exc:
                gcs_cleanup_status = "failed"
                gcs_error = str(gcs_exc)
                log.error(f"[ADMIN] GCS cleanup failed for user {user_id_str}: {gcs_exc}", exc_info=True)
        else:
            log.warning("[ADMIN] GCS not available - skipping file cleanup")
        
        gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
        summary = {
            "success": True,
            "deleted_user": {
                "id": user_id_str,
                "email": user_email_copy,
            },
            "deleted_items": {
                "podcasts": podcast_count,
                "episodes": episode_count,
                "episode_sections": section_count,
                "templates": template_count,
                "media_items": media_count,
                "media_transcripts": transcript_count,
            },
            "gcs_cleanup": {
                "status": gcs_cleanup_status,
                "files_deleted": gcs_deleted_count,
                "error": gcs_error,
            },
            "gcs_path": f"gs://{gcs_bucket}/{user_id_hex}/",
            "gcs_manual_command": f"gsutil -m rm -r gs://{gcs_bucket}/{user_id_hex}/" if gcs_cleanup_status == "failed" else None,
        }
        
        log.warning(f"[ADMIN] User deletion complete: {summary}")
        
        return summary
        
    except Exception as exc:
        session.rollback()
        log.error(f"[ADMIN] Failed to delete user {user_id_str}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete user: {str(exc)}"
        )

def get_user_credits_data(
    session: Session,
    user_id: UUID
) -> Dict[str, Any]:
    """
    Get detailed credit history and balance for a user.
    """
    # Get current balance
    from api.services.billing import credits
    balance = credits.get_user_credit_balance(session, user_id)
    
    # Get total allocation (from tier)
    user = crud.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    from api.services import tier_service
    tier = getattr(user, 'tier', 'free') or 'free'
    tier_credits = tier_service.get_tier_credits(session, tier)
    
    # Get ledger entries (recent history)
    ledger_stmt = (
        select(ProcessingMinutesLedger)
        .where(ProcessingMinutesLedger.user_id == user_id)
        .order_by(ProcessingMinutesLedger.created_at.desc())
        .limit(20)
    )
    ledger_entries = session.exec(ledger_stmt).all()
    
    return {
        "balance": balance,
        "total_allocation": tier_credits,
        "ledger": [
            LedgerEntryDetail(
                id=str(entry.id),
                amount=entry.amount,
                reason=entry.reason,
                direction=entry.direction,
                created_at=entry.created_at.isoformat(),
                description=entry.description,
                balance_after=entry.balance_after
            ) for entry in ledger_entries
        ]
    }


def bulk_delete_test_users(
    session: Session,
    admin_user: User,
) -> Dict[str, Any]:
    """
    Bulk delete users that match test account criteria:
    - Email starts with 'builder'
    - Email starts with 'test'
    - Email ends with '@example.com'
    """
    log.warning(f"[ADMIN] Bulk delete of test users requested by {admin_user.email}")
    
    # 1. Find matching users
    query = select(User).where(
        or_(
            User.email.ilike("builder%"),
            User.email.ilike("test%"),
            User.email.ilike("%@example.com")
        )
    )
    candidates = session.exec(query).all()
    
    # Pre-fetch episode counts for efficiency
    candidate_ids = [u.id for u in candidates]
    episode_counts = {}
    if candidate_ids:
        ep_stmt = (
            select(Episode.user_id, func.count(Episode.id))
            .where(Episode.user_id.in_(candidate_ids))
            .group_by(Episode.user_id)
        )
        episode_counts = dict(session.exec(ep_stmt).all())

    deleted_count = 0
    errors = []
    
    for user in candidates:
        if not user.email:
             continue
             
        # SAFETY CHECK: Only delete users with 1 or fewer episodes
        # This protects accounts with significant data
        user_ep_count = episode_counts.get(user.id, 0)
        if user_ep_count > 1:
            log.warning(f"[ADMIN] Skipping test user {user.email} - Has {user_ep_count} episodes (limit: 1)")
            continue

        # Skip if protected
        if user.email.lower() in [PROTECTED_SUPERADMIN_EMAIL, "tom@pluspluspodcasts.com", "tgdscott@gmail.com"]:
            continue
            
        # Skip valid paid accounts just in case (though unlikely for test accounts)
        user_tier = (user.tier or "free").strip().lower()
        if user_tier not in ["free", "starter", "admin", "trial"]:
             # Skip paid tiers to be safe
             continue
             
        user_email = user.email

        # Force deactivate and downgrade user before deletion to satisfy safety checks
        # This is safe because we've already filtered by strict email criteria
        if user.is_active or user.tier not in ["free", "starter", "hobby", ""]:
            try:
                user.is_active = False
                user.tier = "free"  # Downgrade to free to allow deletion
                user.subscription_expires_at = None
                session.add(user)
                session.commit()
                session.refresh(user)
                log.info(f"[ADMIN] Force deactivated and downgraded test user {user_email} for deletion")
            except Exception as e:
                log.error(f"[ADMIN] Failed to deactivate/downgrade user {user_email}: {e}")
                errors.append(f"Failed to deactivate/downgrade {user_email}: {str(e)}")
                continue

        try:
            # Re-fetch user to ensure fresh state
            session.refresh(user)
            delete_user_account(session, admin_user, str(user.id), user_email)
            deleted_count += 1
            log.info(f"[ADMIN] Bulk deleted test user: {user_email}")
        except Exception as e:
            error_msg = str(e)
            # If it's a 403, it might be a race condition or persistent state issue
            if "403" in error_msg:
                from sqlalchemy import text
                log.warning(f"[ADMIN] 403 error deleting {user_email}, retrying with aggressive downgrade...")
                try:
                    # Final attempt: direct SQL update to force state
                    session.execute(
                        text("UPDATE \"user\" SET is_active = false, tier = 'free' WHERE id = :uid"),
                        {"uid": user.id}
                    )
                    session.commit()
                    session.refresh(user) # Refresh after direct update
                    delete_user_account(session, admin_user, str(user.id), user_email)
                    deleted_count += 1
                    log.info(f"[ADMIN] Bulk deleted test user after retry: {user_email}")
                    continue # Successfully deleted, move to next user
                except Exception as retry_err:
                     error_msg = f"{error_msg} | Retry failed: {retry_err}"

            log.error(f"[ADMIN] Failed to bulk delete user {user_email}: {error_msg}")
            errors.append(f"{user_email}: {error_msg}")
            # Continue to next user
            
    return {
        "success": True,
        "found": len(candidates),
        "deleted": deleted_count,
        "errors": errors
    }
    
    # Calculate monthly usage
    from api.services.billing import usage as usage_svc
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_breakdown = usage_svc.month_credits_breakdown(session, user_id, start_of_month, now)
    total_used_this_month = sum(monthly_breakdown.values())
    
    return {
        "balance": balance,
        "tier_allocation": tier_credits,
        "used_this_month": total_used_this_month,
        "history": ledger
    }

def process_refund_credits(
    session: Session,
    admin_user: User,
    user_id: UUID,
    request: RefundCreditsRequest
) -> Dict[str, Any]:
    """
    Refund credits for specific ledger entries (Admin only).
    """
    log.info(f"[ADMIN] Credit refund requested by {admin_user.email} for user_id: {user_id}")
    
    # Verify user exists
    user = crud.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    manual_refund_amount = request.manual_credits
    
    if not request.ledger_entry_ids and manual_refund_amount is None:
        raise HTTPException(status_code=400, detail="Must provide ledger entries or manual amount")

    # Fetch entries to refund
    entries = []
    calculated_total = 0.0
    
    if request.ledger_entry_ids:
        stmt = (
            select(ProcessingMinutesLedger)
            .where(ProcessingMinutesLedger.id.in_(request.ledger_entry_ids))
            .where(ProcessingMinutesLedger.user_id == user_id)
            .where(ProcessingMinutesLedger.direction == LedgerDirection.DEBIT)
        )
        entries = session.exec(stmt).all()
        
        if len(entries) != len(request.ledger_entry_ids):
            # Some entries not found or don't match criteria
            found_ids = {e.id for e in entries}
            missing = set(request.ledger_entry_ids) - found_ids
            log.warning(f"[ADMIN] Refund request included invalid/missing ledger IDs: {missing}")
            # Continue with valid entries
            
        calculated_total = sum(float(e.credits) for e in entries)

    # Determine total refund amount
    total_refund = 0.0
    if manual_refund_amount is not None:
        if manual_refund_amount <= 0:
            raise HTTPException(status_code=400, detail="Manual refund amount must be positive")
        total_refund = manual_refund_amount
    else:
        total_refund = calculated_total
        
    if total_refund <= 0:
         raise HTTPException(status_code=400, detail="Total refund amount must be positive")

    log.info(f"[ADMIN] Processing refund of {total_refund} credits for user {user_id}")

    # Process the refund
    from api.services.billing.credits import refund_credits
    from api.models.usage import LedgerReason
    
    refunded_entries = []
    
    if manual_refund_amount is not None:
        # Create a single refund entry for manual amount
        refund_notes = f"Admin refund (Manual Adjustment)" + (f": {request.notes}" if request.notes else "")
        if entries:
             refund_notes += f" (Ref: {len(entries)} entries)"
        
        refund_entry = refund_credits(
            session=session,
            user_id=user_id,
            credits=manual_refund_amount,
            reason=LedgerReason.MANUAL_ADJUST,
            notes=refund_notes
        )
        refunded_entries.append(refund_entry)
        
        # Mark entries as refunded in optional metadata if needed (not supported by current schema explicitly)
        # But we log it in AdminActionLog
            
    else:
        # Refund each entry individually
        for entry in entries:
            refund_notes = f"Admin refund: {entry.reason.value}" + (f" - {request.notes}" if request.notes else "")
            # Add reference to original entry
            refund_notes += f" (refunded_entry_id: {entry.id})"
            
            refund_entry = refund_credits(
                session=session,
                user_id=user_id,
                credits=float(entry.credits),
                reason=entry.reason,  # Use original reason so refund reduces correct category
                episode_id=entry.episode_id,
                notes=refund_notes
            )
            refunded_entries.append(refund_entry)
    
    # Send email notification
    try:
        from api.services.mailer import mailer
        email_body = f"""Hi {user.first_name or user.email.split('@')[0]},

We've refunded {total_refund:.1f} credits to your account.

"""
        if request.manual_credits is not None:
            email_body += f"Manual adjustment refund: {total_refund:.1f} credits (selected entries total: {calculated_total:.1f} credits)\n\n"
            email_body += "Selected entries (for reference):\n"
            for entry in entries:
                email_body += f"  - {entry.reason.value}: {entry.credits:.1f} credits"
                if entry.episode_id:
                    try:
                        episode = session.get(Episode, entry.episode_id)
                        if episode:
                            email_body += f" (Episode: {episode.title})"
                    except Exception:
                        pass
                email_body += "\n"
        else:
            email_body += "Refunded entries:\n"
            for entry in entries:
                email_body += f"  - {entry.reason.value}: {entry.credits:.1f} credits"
                if entry.episode_id:
                    try:
                        episode = session.get(Episode, entry.episode_id)
                        if episode:
                            email_body += f" (Episode: {episode.title})"
                    except Exception:
                        pass
                email_body += "\n"
        
        if request.notes:
            email_body += f"\nReason: {request.notes}\n"
        
        email_body += """
These credits have been restored to your account and are available for use immediately.

Thank you for using Podcast Plus Plus!

The Podcast Plus Plus Team
"""
        
        mailer.send(
            to=user.email,
            subject=f"Credits Refunded - {total_refund:.1f} credits",
            text=email_body
        )
    except Exception as e:
        log.error(f"[ADMIN] Failed to send refund email: {e}", exc_info=True)
        # Don't fail the refund if email fails
    
    # Update refund request status to "approved" if this was from a refund request
    refund_notification_id = None
    if NOTIFICATION_AVAILABLE:
        try:
            import json
            # Find the user's refund request notification for these entries
            user_notifications = session.exec(
                select(Notification)
                .where(Notification.user_id == user_id)
                .where(Notification.type == "refund_request")
            ).all()
            
            for notif in user_notifications:
                try:
                    # Try to parse as JSON (old format) or check if it's a user-friendly message
                    try:
                        details = json.loads(notif.body)
                        requested_ids = set(details.get("ledger_entry_ids", []))
                    except (json.JSONDecodeError, TypeError):
                        # New format - user-friendly message, skip JSON parsing
                        # We'll update all pending refund requests since we can't match by IDs
                        requested_ids = set()
                    
                    refunded_ids = set(request.ledger_entry_ids)
                    
                    # If all requested entries were refunded (or we can't determine), mark as approved
                    # For new format, we'll update if it's still pending
                    if not requested_ids or refunded_ids.issuperset(requested_ids):
                        # Update with user-friendly approval message
                        approval_message = f"Your refund request has been approved and {total_refund:.1f} credits have been restored to your account."
                        approval_message += "\n\nThese credits are available for use immediately."
                        notif.body = approval_message
                        session.add(notif)
                        refund_notification_id = notif.id
                except (KeyError, TypeError) as e:
                    log.warning(f"[ADMIN] Failed to update refund notification {notif.id}: {e}")
                    continue
            
            session.commit()
        except Exception as e:
            log.warning(f"[ADMIN] Failed to update refund request status: {e}")
            # Don't fail the refund if status update fails
    
    # Log the refund action
    if ADMIN_LOG_AVAILABLE:
        try:
            import json
            action_log = AdminActionLog(
                action_type=AdminActionType.REFUND_APPROVED,
                admin_user_id=admin_user.id,
                target_user_id=user_id,
                refund_notification_id=refund_notification_id,
                refund_amount=total_refund,
                refund_entry_ids=json.dumps(request.ledger_entry_ids) if request.ledger_entry_ids else None,
                notes=request.notes
            )
            session.add(action_log)
            session.commit()
            log.info(f"[ADMIN] Logged refund approval: {total_refund:.2f} credits for user {user_id}")
        except Exception as e:
            log.error(f"[ADMIN] Failed to log refund action: {e}", exc_info=True)
            # Don't fail the refund if logging fails
            session.rollback()
    
    return {
        "success": True,
        "refunded_credits": total_refund,
        "refunded_entries": len(refunded_entries),
        "message": f"Successfully refunded {total_refund:.1f} credits"
    }

def process_award_credits(
    session: Session,
    admin_user: User,
    user_id: UUID,
    request: AwardCreditsRequest
) -> Dict[str, Any]:
    """
    Award credits to a user (Admin only).
    """
    log.info(f"[ADMIN] Credit award requested by {admin_user.email} for user_id: {user_id}, credits: {request.credits}, reason: {request.reason}")
    
    if request.credits <= 0:
        raise HTTPException(status_code=400, detail="Credits must be positive")
    
    # Verify user exists
    user = crud.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Award credits as purchased credits
    from api.services.billing.wallet import add_purchased_credits
    from api.services.billing.credits import refund_credits
    from api.models.usage import LedgerReason
    
    # Add to wallet as purchased credits
    wallet = add_purchased_credits(
        session=session,
        user_id=user_id,
        amount=request.credits
    )
    
    # Create ledger entry
    refund_entry = refund_credits(
        session=session,
        user_id=user_id,
        credits=request.credits,
        reason=LedgerReason.MANUAL_ADJUST,
        notes=f"Admin award: {request.reason}" + (f" - {request.notes}" if request.notes else "")
    )
    
    # Send email notification
    try:
        from api.services.mailer import mailer
        email_body = f"""Hi {user.first_name or user.email.split('@')[0]},

We've awarded {request.credits:.1f} credits to your account!

Reason: {request.reason}
"""
        if request.notes:
            email_body += f"\nNotes: {request.notes}\n"
        
        email_body += """
These credits have been added to your account as add-on credits and are available for use immediately.

Thank you for using Podcast Plus Plus!

The Podcast Plus Plus Team
"""
        
        mailer.send(
            to=user.email,
            subject=f"Credits Awarded - {request.credits:.1f} credits",
            text=email_body
        )
    except Exception as e:
        log.error(f"[ADMIN] Failed to send award email: {e}", exc_info=True)
        # Don't fail the award if email fails
    
    # Log the credit award action
    if ADMIN_LOG_AVAILABLE:
        try:
            action_log = AdminActionLog(
                action_type=AdminActionType.CREDIT_AWARDED,
                admin_user_id=admin_user.id,
                target_user_id=user_id,
                credit_amount=request.credits,
                award_reason=request.reason,
                notes=request.notes
            )
            session.add(action_log)
            session.commit()
            log.info(f"[ADMIN] Logged credit award: {request.credits:.2f} credits for user {user_id}")
        except Exception as e:
            log.error(f"[ADMIN] Failed to log credit award: {e}", exc_info=True)
            # Don't fail the award if logging fails
            session.rollback()
    
    return {
        "success": True,
        "awarded_credits": request.credits,
        "new_balance": wallet.total_available,
        "message": f"Successfully awarded {request.credits:.1f} credits"
    }

def process_deny_refund_request(
    session: Session,
    admin_user: User,
    notification_id: UUID,
    request: DenyRefundRequest
) -> Dict[str, Any]:
    """
    Deny a refund request with a reason (Admin only).
    """
    if not NOTIFICATION_AVAILABLE:
        raise HTTPException(status_code=400, detail="Notifications not available")
    
    # Get the admin notification
    admin_notification = session.get(Notification, notification_id)
    if not admin_notification:
        raise HTTPException(status_code=404, detail="Refund request not found")
    
    # Check authorization? Admin can usually act on any notification, but check logic
    if admin_notification.user_id != admin_user.id:
        # In original code, it checked if notification belonged to admin.
        # Ideally any admin should be able to process any refund request if they can see it.
        # But let's stick to original logic: must be assigned to this admin (or system check).
        # Assuming admin_user passed here is the one who retrieved it.
        if admin_notification.user_id != admin_user.id:
             raise HTTPException(status_code=403, detail="Not authorized to modify this refund request (belongs to another admin)")
    
    if admin_notification.type != "refund_request":
        raise HTTPException(status_code=400, detail="Notification is not a refund request")
    
    try:
        import json
        import re
        
        # Parse admin notification to get user notification ID
        details_match = re.search(r'Details:\s*(\{.*\})', admin_notification.body, re.DOTALL)
        if details_match:
            admin_details = json.loads(details_match.group(1))
            user_notification_id = admin_details.get("user_notification_id")
            
            if user_notification_id:
                # Get and update user's notification with user-friendly message
                user_notification = session.get(Notification, UUID(user_notification_id))
                if user_notification:
                    # Update with user-friendly denial message (don't expose internal details)
                    denial_message = "Your refund request has been reviewed and unfortunately cannot be approved at this time."
                    if request.denial_reason:
                        denial_message += f"\n\nReason: {request.denial_reason}"
                    denial_message += "\n\nIf you have any questions, please contact our support team."
                    user_notification.body = denial_message
                    session.add(user_notification)
                    
                    # Update admin notification
                    admin_details["status"] = "denied"
                    admin_details["denial_reason"] = request.denial_reason
                    admin_details["denied_at"] = datetime.utcnow().isoformat()
                    admin_details["denied_by"] = admin_user.email
                    admin_notification.body = f"User {admin_details.get('user_email', 'Unknown')} requested refund.\n\nReason: {admin_details.get('reason', '')}\n\nStatus: DENIED\nDenial Reason: {request.denial_reason}\n\nDetails:\n{json.dumps(admin_details, indent=2)}"
                    session.add(admin_notification)
                    
                    # Send email to user
                    try:
                        from api.services.mailer import mailer
                        user = crud.get_user_by_id(session, user_notification.user_id)
                        if user:
                            email_body = f"""Hi {user.first_name or user.email.split('@')[0]},

We've reviewed your refund request and unfortunately cannot approve it at this time.

Reason for denial: {request.denial_reason}

If you have any questions or would like to discuss this further, please contact our support team.

Thank you for your understanding.

The Podcast Plus Plus Team
"""
                            mailer.send(
                                to=user.email,
                                subject="Refund Request - Not Approved",
                                text=email_body
                            )
                    except Exception as e:
                        log.error(f"[ADMIN] Failed to send denial email: {e}", exc_info=True)
                    
                    session.commit()
                    
                    log.info(
                        f"[ADMIN] Refund request denied by {admin_user.email}: "
                        f"notification_id={notification_id}, reason={request.denial_reason[:50]}"
                    )
                    
                    # Log the denial action
                    if ADMIN_LOG_AVAILABLE:
                        try:
                            import json
                            # Try to get refund amount from admin_details if available
                            refund_amount = None
                            refund_entry_ids_json = None
                            # admin_details is already defined above in the if details_match block
                            try:
                                # Try to calculate from ledger_entry_ids if available
                                ledger_entry_ids = admin_details.get("ledger_entry_ids", [])
                                if ledger_entry_ids:
                                    refund_entry_ids_json = json.dumps(ledger_entry_ids)
                                    from api.models.usage import ProcessingMinutesLedger, LedgerDirection
                                    entries = session.exec(
                                        select(ProcessingMinutesLedger)
                                        .where(ProcessingMinutesLedger.id.in_(ledger_entry_ids))
                                        .where(ProcessingMinutesLedger.user_id == user_notification.user_id)
                                        .where(ProcessingMinutesLedger.direction == LedgerDirection.DEBIT)
                                    ).all()
                                    if entries:
                                        refund_amount = sum(float(e.credits) for e in entries)
                            except Exception:
                                pass
                            
                            action_log = AdminActionLog(
                                action_type=AdminActionType.REFUND_DENIED,
                                admin_user_id=admin_user.id,
                                target_user_id=user_notification.user_id,
                                refund_notification_id=UUID(user_notification_id),
                                refund_amount=refund_amount,
                                refund_entry_ids=refund_entry_ids_json,
                                denial_reason=request.denial_reason,
                                notes=None
                            )
                            session.add(action_log)
                            session.commit()
                            log.info(f"[ADMIN] Logged refund denial for user {user_notification.user_id}")
                        except Exception as e:
                            log.error(f"[ADMIN] Failed to log refund denial: {e}", exc_info=True)
                            # Don't fail the denial if logging fails
                            try:
                                session.rollback()
                            except:
                                pass
                    
                    return {
                        "success": True,
                        "message": "Refund request denied. User has been notified."
                    }
        
        raise HTTPException(status_code=400, detail="Could not parse refund request details")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid refund request format: {e}")
    except Exception as e:
        log.error(f"[ADMIN] Failed to deny refund request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to deny refund request: {str(e)}")

def get_refund_requests_list(
    session: Session,
    admin_user: User,
    limit: int = 50,
) -> List[RefundRequestResponse]:
    """
    Get all refund requests for admin review.
    """
    if not NOTIFICATION_AVAILABLE:
        log.warning("[refund-requests] Notification model not available")
        return []
    
    try:
        # Get all refund request notifications for admin users
        stmt = (
            select(Notification)
            .where(Notification.type == "refund_request")
            .where(Notification.user_id == admin_user.id)  # Only notifications sent to this admin
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        
        notifications = session.exec(stmt).all()
    except Exception as e:
        log.error(f"[refund-requests] Failed to query notifications: {e}", exc_info=True)
        return []
    
    import json
    import re
    
    refund_requests = []
    for notif in notifications:
        try:
            # Skip if body is None or empty
            if not notif.body:
                log.warning(f"Refund request notification {notif.id} has no body")
                continue
            
            # Parse the body to extract details
            # Body format: "User {email} requested refund for {count} charges. Reason: {reason}. Details: {details_json}"
            
            # Try to extract JSON from body
            details_match = re.search(r'Details:\s*(\{.*\})', notif.body, re.DOTALL)
            if details_match:
                try:
                    details_json = details_match.group(1)
                    details = json.loads(details_json)
                    
                    refund_requests.append(RefundRequestResponse(
                        notification_id=str(notif.id),
                        user_id=details.get("user_id", ""),
                        user_email=details.get("user_email", ""),
                        episode_id=details.get("episode_id"),
                        ledger_entry_ids=details.get("ledger_entry_ids", []),
                        reason=details.get("reason", ""),
                        notes=details.get("notes"),
                        created_at=notif.created_at,
                        read_at=notif.read_at
                    ))
                    continue
                except json.JSONDecodeError as e:
                    log.warning(f"Failed to parse JSON from notification {notif.id}: {e}")
            
            # Fallback: try to extract basic info from body text
            user_match = re.search(r'User\s+([^\s@]+@[^\s]+)', notif.body)
            reason_match = re.search(r'Reason:\s*([^\n]+)', notif.body)
            
            refund_requests.append(RefundRequestResponse(
                notification_id=str(notif.id),
                user_id="",
                user_email=user_match.group(1) if user_match else "Unknown",
                episode_id=None,
                ledger_entry_ids=[],
                reason=reason_match.group(1).strip() if reason_match else (notif.body[:100] if notif.body else "No reason provided"),
                notes=None,
                created_at=notif.created_at,
                read_at=notif.read_at
            ))
        except Exception as e:
            log.error(f"Failed to parse refund request notification {notif.id}: {e}", exc_info=True)
            # Still add a basic entry so admin can see there's a notification
            try:
                refund_requests.append(RefundRequestResponse(
                    notification_id=str(notif.id),
                    user_id="",
                    user_email="Unknown",
                    episode_id=None,
                    ledger_entry_ids=[],
                    reason=f"Error parsing notification: {str(e)[:50]}",
                    notes=None,
                    created_at=notif.created_at,
                    read_at=notif.read_at
                ))
            except Exception:
                continue
    
    return refund_requests

def get_refund_request_details_service(
    session: Session,
    admin_user: User,
    notification_id: UUID,
) -> RefundRequestDetail:
    """
    Get comprehensive details for a refund request.
    """
    if not NOTIFICATION_AVAILABLE:
        raise HTTPException(status_code=400, detail="Notifications not available")
    
    # Get the notification
    notification = session.get(Notification, notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Refund request not found")
    
    if notification.type != "refund_request":
        raise HTTPException(status_code=400, detail="Notification is not a refund request")
    
    # Parse notification body
    import json
    import re
    from datetime import datetime, timezone, timedelta
    tz = timezone  # Alias for clarity
    
    details = {}
    if notification.body:
        # Try to extract JSON from "Details:" section (admin notifications)
        details_match = re.search(r'Details:\s*(\{.*\})', notification.body, re.DOTALL)
        if details_match:
            try:
                details_json = details_match.group(1)
                details = json.loads(details_json)
            except json.JSONDecodeError as e:
                log.warning(f"Failed to parse Details JSON: {e}")
                # Try parsing the whole body as JSON (for user notifications)
                try:
                    details = json.loads(notification.body)
                except json.JSONDecodeError:
                    pass
        else:
            # If no "Details:" section, try parsing the whole body as JSON
            try:
                details = json.loads(notification.body)
            except json.JSONDecodeError:
                pass
    
    user_id_str = details.get("user_id", "")
    if not user_id_str:
        raise HTTPException(status_code=400, detail="Invalid refund request: missing user_id")
    
    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id format")
    
    # Get user
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get user credit context
    from api.services.billing import credits
    from api.services import tier_service
    from api.services.billing import usage as usage_svc
    from datetime import datetime, timezone
    
    balance = credits.get_user_credit_balance(session, user_id)
    tier = getattr(user, 'tier', 'free') or 'free'
    tier_credits = tier_service.get_tier_credits(session, tier)
    
    # Calculate usage stats
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_breakdown = usage_svc.month_credits_breakdown(session, user_id, start_of_month, now)
    total_used_this_month = sum(monthly_breakdown.values())
    
    # Get all-time usage
    from sqlmodel import func
    from api.models.usage import ProcessingMinutesLedger, LedgerDirection
    all_time_stmt = (
        select(func.sum(ProcessingMinutesLedger.credits))
        .where(ProcessingMinutesLedger.user_id == user_id)
        .where(ProcessingMinutesLedger.direction == LedgerDirection.DEBIT)
    )
    total_used_all_time = session.exec(all_time_stmt).one() or 0.0
    
    # Get previous refund history
    from api.models.usage import LedgerReason
    previous_refunds_stmt = (
        select(ProcessingMinutesLedger)
        .where(ProcessingMinutesLedger.user_id == user_id)
        .where(ProcessingMinutesLedger.direction == LedgerDirection.CREDIT)
        .where(
            (ProcessingMinutesLedger.reason == LedgerReason.REFUND_ERROR) |
            (ProcessingMinutesLedger.reason == LedgerReason.MANUAL_ADJUST)
        )
        .order_by(ProcessingMinutesLedger.created_at.desc())
    )
    previous_refunds = session.exec(previous_refunds_stmt).all()
    previous_refund_count = len(previous_refunds)
    previous_refund_total = sum(r.credits for r in previous_refunds)
    last_refund_date = previous_refunds[0].created_at if previous_refunds else None
    
    # Get ledger entries for this refund request
    ledger_entry_ids = details.get("ledger_entry_ids", [])
    episode_id_str = details.get("episode_id")
    
    # If episode_id is provided but no ledger_entry_ids, get all entries for that episode
    if episode_id_str and not ledger_entry_ids:
        try:
            episode_id = UUID(episode_id_str)
            episode_entries_stmt = (
                select(ProcessingMinutesLedger)
                .where(ProcessingMinutesLedger.episode_id == episode_id)
                .where(ProcessingMinutesLedger.user_id == user_id)
                .where(ProcessingMinutesLedger.direction == LedgerDirection.DEBIT)
            )
            episode_entries = session.exec(episode_entries_stmt).all()
            ledger_entry_ids = [e.id for e in episode_entries if e.id]
        except (ValueError, AttributeError) as e:
            log.warning(f"Failed to get episode entries for {episode_id_str}: {e}")
    
    if not ledger_entry_ids:
        raise HTTPException(status_code=400, detail="No ledger entries specified in refund request")
    
    # Check for existing refunds
    existing_refunds_stmt = (
        select(ProcessingMinutesLedger)
        .where(ProcessingMinutesLedger.user_id == user_id)
        .where(ProcessingMinutesLedger.direction == LedgerDirection.CREDIT)
        .where(
            (ProcessingMinutesLedger.notes.like("%refunded_entry_id:%")) | 
            (ProcessingMinutesLedger.notes.like("%(entry %")) |
            (ProcessingMinutesLedger.notes.like("%Admin refund%"))
        )
    )
    existing_refunds = session.exec(existing_refunds_stmt).all()
    refunded_entry_ids = set()
    for refund in existing_refunds:
        # Try to extract entry ID from notes
        import re
        match = re.search(r'refunded_entry_id:\s*(\d+)', refund.notes or "")
        if not match:
             match = re.search(r'\(entry\s+(\d+)\)', refund.notes or "")
        if match:
            refunded_entry_ids.add(int(match.group(1)))
        
        # Fuzzy match
        if refund.episode_id:
            for entry_id in ledger_entry_ids:
                entry = session.get(ProcessingMinutesLedger, entry_id)
                if entry and entry.episode_id == refund.episode_id:
                    if abs(entry.credits - refund.credits) < 0.1 and entry.reason == refund.reason:
                        if refund.created_at > entry.created_at:
                            refunded_entry_ids.add(entry_id)
    
    ledger_entries_list = []
    total_requested = 0.0
    total_already_refunded = 0.0
    earliest_charge_date = None
    
    for entry_id in ledger_entry_ids:
        entry = session.get(ProcessingMinutesLedger, entry_id)
        if not entry:
            continue
        
        if entry.user_id != user_id:
            raise HTTPException(status_code=403, detail="Ledger entry does not belong to user")
        
        cost_breakdown = None
        if entry.cost_breakdown_json:
            try:
                cost_breakdown = json.loads(entry.cost_breakdown_json)
            except json.JSONDecodeError:
                pass
        
        credit_source = "monthly"
        already_refunded = entry.id in refunded_entry_ids if entry.id else False
        
        # Get episode info if applicable
        episode_title = None
        service_delivered = None
        service_details = {}
        
        if entry.episode_id:
            try:
                episode = session.get(Episode, entry.episode_id)
                if episode:
                    episode_title = episode.title
                    if entry.reason in [LedgerReason.TRANSCRIPTION, LedgerReason.ASSEMBLY, LedgerReason.AUPHONIC_PROCESSING]:
                        service_delivered = episode.status in ["processed", "published"]
                        service_details = {
                            "episode_status": episode.status.value if hasattr(episode.status, 'value') else str(episode.status),
                            "has_final_audio": bool(episode.final_audio_path or episode.gcs_audio_path),
                            "is_published": episode.status == "published" if hasattr(episode.status, 'value') else False,
                            "duration_ms": episode.duration_ms,
                            "processed_at": episode.processed_at.isoformat() if episode.processed_at else None,
                        }
                    elif entry.reason == LedgerReason.TTS_GENERATION:
                        service_delivered = True
                        service_details = {"service_type": "TTS Generation"}
            except Exception:
                pass
        elif entry.reason == LedgerReason.TTS_LIBRARY:
            service_delivered = True
            service_details = {"service_type": "TTS Library"}
        elif entry.reason == LedgerReason.STORAGE:
            service_delivered = True
            service_details = {"service_type": "Storage"}
        
        if entry.direction == LedgerDirection.DEBIT:
            if not already_refunded:
                total_requested += entry.credits
            else:
                total_already_refunded += entry.credits
            
            entry_created_at = entry.created_at
            if entry_created_at and entry_created_at.tzinfo is None:
                entry_created_at = entry_created_at.replace(tzinfo=tz.utc)
            if entry_created_at and (earliest_charge_date is None or entry_created_at < earliest_charge_date):
                earliest_charge_date = entry_created_at
        elif entry.direction == LedgerDirection.CREDIT:
             total_already_refunded += entry.credits
        
        entry_detail = LedgerEntryDetail(
            id=entry.id or 0,
            timestamp=entry.created_at,
            direction=entry.direction.value,
            reason=entry.reason.value,
            credits=entry.credits,
            minutes=entry.minutes,
            notes=entry.notes,
            cost_breakdown=cost_breakdown,
            correlation_id=entry.correlation_id,
            credit_source=credit_source,
            episode_id=str(entry.episode_id) if entry.episode_id else None,
            episode_title=episode_title,
            can_refund=entry.direction == LedgerDirection.DEBIT and not already_refunded,
            already_refunded=already_refunded,
            refund_status="approved" if already_refunded else None,
            service_delivered=service_delivered,
            service_details=service_details if service_details else None
        )
        ledger_entries_list.append(entry_detail)
    
    # Group by episode
    from collections import defaultdict
    episodes_dict = defaultdict(lambda: {"entries": [], "episode_id": None})
    non_episode_entries = []
    
    for entry_detail in ledger_entries_list:
        if entry_detail.episode_id:
            episodes_dict[entry_detail.episode_id]["entries"].append(entry_detail)
            episodes_dict[entry_detail.episode_id]["episode_id"] = entry_detail.episode_id
        else:
            non_episode_entries.append(entry_detail)
    
    episodes_list = []
    for episode_id_str, episode_data in episodes_dict.items():
        try:
            episode_id = UUID(episode_id_str)
            episode = session.get(Episode, episode_id)
            if not episode:
                continue
            
            podcast = session.get(Podcast, episode.podcast_id)
            podcast_title = None
            if podcast:
                 podcast_title = getattr(podcast, 'title', None) or getattr(podcast, 'name', None)
            
            episode_entries = episode_data["entries"]
            episode_total_requested = sum(e.credits for e in episode_entries if e.can_refund and not e.already_refunded)
            episode_total_refunded = sum(e.credits for e in episode_entries if e.already_refunded)
            episode_net_refund = episode_total_requested - episode_total_refunded
            
            from api.models.enums import EpisodeStatus
            episode_status_str = episode.status.value if hasattr(episode.status, 'value') else str(episode.status)
            has_final_audio = bool(episode.final_audio_path or episode.gcs_audio_path)
            is_published = episode_status_str == "published"
            service_delivered = episode_status_str in ["processed", "published"]
            can_be_restored = has_final_audio and episode_status_str != "error"
            
            refund_recommendation = None
            if episode_total_requested == 0:
                refund_recommendation = "no_refund"
            elif not service_delivered:
                refund_recommendation = "full_refund"
            elif is_published:
                refund_recommendation = "no_refund"
            elif has_final_audio and service_delivered:
                refund_recommendation = "conditional_refund"
            else:
                refund_recommendation = "partial_refund"
            
            episodes_list.append(EpisodeRefundDetail(
                id=str(episode.id),
                title=episode.title,
                status=episode_status_str,
                created_at=episode.created_at,
                processed_at=episode.processed_at,
                duration_ms=episode.duration_ms,
                episode_number=episode.episode_number,
                season_number=episode.season_number,
                podcast_title=podcast_title,
                has_final_audio=has_final_audio,
                is_published=is_published,
                is_published_to_spreaker=getattr(episode, 'is_published_to_spreaker', False),
                spreaker_episode_id=getattr(episode, 'spreaker_episode_id', None),
                error_message=getattr(episode, 'error_message', None),
                spreaker_publish_error=getattr(episode, 'spreaker_publish_error', None),
                spreaker_publish_error_detail=getattr(episode, 'spreaker_publish_error_detail', None),
                auphonic_processed=getattr(episode, 'auphonic_processed', False),
                auphonic_error=getattr(episode, 'auphonic_error', None),
                gcs_audio_path=getattr(episode, 'gcs_audio_path', None),
                final_audio_path=getattr(episode, 'final_audio_path', None),
                audio_file_size=getattr(episode, 'audio_file_size', None),
                show_notes=getattr(episode, 'show_notes', None),
                brief_summary=getattr(episode, 'brief_summary', None),
                # episode_tags=episode.episode_tags, # Skipping complex parsing for now
                # episode_chapters=episode.episode_chapters,
                ledger_entries=episode_entries,
                total_credits_requested=episode_total_requested,
                total_credits_already_refunded=episode_total_refunded,
                net_credits_to_refund=episode_net_refund,
                service_delivered=service_delivered,
                can_be_restored=can_be_restored,
                refund_recommendation=refund_recommendation
            ))
        except Exception:
            continue

    if earliest_charge_date:
        if earliest_charge_date.tzinfo is None:
            earliest_charge_date = earliest_charge_date.replace(tzinfo=tz.utc)
        days_since_charges = (now - earliest_charge_date).total_seconds() / 86400.0
    else:
        days_since_charges = 0.0
    
    notification_created_at = notification.created_at
    if notification_created_at and notification_created_at.tzinfo is None:
        notification_created_at = notification_created_at.replace(tzinfo=tz.utc)
    hours_since_request = (now - notification_created_at).total_seconds() / 3600.0 if notification_created_at else 0.0
    
    eligibility_notes = []
    if days_since_charges > 30:
        eligibility_notes.append(f"Charges are {days_since_charges:.1f} days old (over 30 days)")
    elif days_since_charges > 7:
         eligibility_notes.append(f"Charges are {days_since_charges:.1f} days old")
    
    if previous_refund_count > 3:
        eligibility_notes.append(f"User has {previous_refund_count} previous refunds (high frequency)")
    
    for ep in episodes_list:
        if ep.service_delivered and ep.is_published:
            eligibility_notes.append(f"Episode '{ep.title}' is published - refund may impact published content")
        elif ep.service_delivered:
            eligibility_notes.append(f"Episode '{ep.title}' was successfully processed")
    
    user_context = UserRefundContext(
        user_id=str(user.id),
        email=user.email,
        tier=tier,
        account_created_at=user.created_at,
        is_active=user.is_active,
        subscription_expires_at=getattr(user, 'subscription_expires_at', None),
        total_credits_used_all_time=total_used_all_time,
        total_credits_used_this_month=total_used_this_month,
        current_credit_balance=balance,
        monthly_credit_allocation=tier_credits,
        previous_refund_count=previous_refund_count,
        previous_refund_total_credits=previous_refund_total,
        last_refund_date=last_refund_date
    )
    
    credit_source_breakdown = {"monthly": total_requested}
    
    return RefundRequestDetail(
        notification_id=str(notification.id),
        request_created_at=notification.created_at,
        request_read_at=notification.read_at,
        user_reason=details.get("reason", ""),
        user_notes=details.get("notes"),
        user=user_context,
        episodes=episodes_list,
        non_episode_charges=non_episode_entries,
        total_credits_requested=total_requested,
        total_credits_already_refunded=total_already_refunded,
        net_credits_to_refund=total_requested - total_already_refunded,
        days_since_charges=days_since_charges,
        hours_since_request=hours_since_request,
        refund_eligibility_notes=eligibility_notes,
        credit_source_breakdown=credit_source_breakdown
    )

def get_refund_logs_service(
    session: Session,
    limit: int = 100,
    offset: int = 0
) -> List[RefundLogEntry]:
    """
    Get log of all approved or denied refund requests (Admin only).
    """
    if not ADMIN_LOG_AVAILABLE:
        return []
    
    try:
        stmt = (
            select(AdminActionLog)
            .where(
                or_(
                    AdminActionLog.action_type == AdminActionType.REFUND_APPROVED,
                    AdminActionLog.action_type == AdminActionType.REFUND_DENIED
                )
            )
            .order_by(AdminActionLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        
        logs = session.exec(stmt).all()
        
        user_ids = set()
        for log_entry in logs:
            user_ids.add(log_entry.admin_user_id)
            user_ids.add(log_entry.target_user_id)
        
        users = {}
        if user_ids:
            user_stmt = select(User).where(User.id.in_(list(user_ids)))
            user_results = session.exec(user_stmt).all()
            users = {user.id: user for user in user_results}
        
        result = []
        for log_entry in logs:
            admin_user_obj = users.get(log_entry.admin_user_id)
            target_user_obj = users.get(log_entry.target_user_id)
            
            refund_entry_ids = None
            if log_entry.refund_entry_ids:
                try:
                    import json
                    refund_entry_ids = json.loads(log_entry.refund_entry_ids)
                except Exception:
                    pass
            
            result.append(RefundLogEntry(
                id=log_entry.id or 0,
                action_type=log_entry.action_type.value,
                admin_email=admin_user_obj.email if admin_user_obj else "Unknown",
                target_user_email=target_user_obj.email if target_user_obj else "Unknown",
                target_user_id=str(log_entry.target_user_id),
                refund_amount=log_entry.refund_amount,
                refund_entry_ids=refund_entry_ids,
                denial_reason=log_entry.denial_reason,
                notes=log_entry.notes,
                created_at=log_entry.created_at
            ))
        
        return result
        
    except Exception as e:
        log.error(f"[ADMIN] Failed to get refund logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get refund logs: {str(e)}")

def get_credit_award_logs_service(
    session: Session,
    limit: int = 100,
    offset: int = 0
) -> List[CreditAwardLogEntry]:
    """
    Get log of all credit awards given away (Admin only).
    """
    if not ADMIN_LOG_AVAILABLE:
        return []
    
    try:
        stmt = (
            select(AdminActionLog)
            .where(AdminActionLog.action_type == AdminActionType.CREDIT_AWARDED)
            .order_by(AdminActionLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        
        logs = session.exec(stmt).all()
        
        user_ids = set()
        for log_entry in logs:
            user_ids.add(log_entry.admin_user_id)
            user_ids.add(log_entry.target_user_id)
        
        users = {}
        if user_ids:
            user_stmt = select(User).where(User.id.in_(list(user_ids)))
            user_results = session.exec(user_stmt).all()
            users = {user.id: user for user in user_results}
        
        result = []
        for log_entry in logs:
            admin_user_obj = users.get(log_entry.admin_user_id)
            target_user_obj = users.get(log_entry.target_user_id)
            
            result.append(CreditAwardLogEntry(
                id=log_entry.id or 0,
                action_type=log_entry.action_type.value,
                admin_email=admin_user_obj.email if admin_user_obj else "Unknown",
                target_user_email=target_user_obj.email if target_user_obj else "Unknown",
                target_user_id=str(log_entry.target_user_id),
                credit_amount=log_entry.credit_amount,
                award_reason=log_entry.award_reason,
                notes=log_entry.notes,
                created_at=log_entry.created_at
            ))
        
        return result
        
    except Exception as e:
        log.error(f"[ADMIN] Failed to get credit award logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get credit award logs: {str(e)}")


