from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Body, status
from sqlalchemy import func, or_
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from api.core import crud
from api.core.database import get_session
from api.models.podcast import Episode, Podcast, MediaItem, PodcastTemplate, EpisodeSection, PodcastDistributionStatus
from api.models.user import User, UserPublic, UserTermsAcceptance
from api.models.transcription import MediaTranscript
from api.core.config import settings

# Import additional models for cascade deletion
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
    log.warning("[ADMIN] Admin action log not available - logging will be skipped")

from .deps import commit_with_retry, get_current_admin_user, get_current_superadmin_user

router = APIRouter()


class RefundRequestResponse(BaseModel):
    """Refund request item for admin view"""
    notification_id: str
    user_id: str
    user_email: str
    episode_id: Optional[str] = None
    ledger_entry_ids: List[int] = []
    reason: str
    notes: Optional[str] = None
    created_at: datetime
    read_at: Optional[datetime] = None

log = logging.getLogger(__name__)

# GCS cleanup for user deletion
try:
    from infrastructure.gcs import _get_gcs_client
    GCS_AVAILABLE = True
except Exception as e:
    GCS_AVAILABLE = False
    log.warning(f"[ADMIN] GCS client not available - user deletion will skip GCS cleanup: {e}")

# Special tiers that are admin-related
ADMIN_TIERS = {"admin", "superadmin"}
PROTECTED_SUPERADMIN_EMAIL = getattr(settings, 'ADMIN_EMAIL', '').lower()


@router.get("/users", response_model=List[UserPublic])
def get_all_users(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> List[UserPublic]:
    del admin_user
    return crud.get_all_users(session=session)


class UserAdminOut(BaseModel):
    id: str
    email: str
    tier: Optional[str]
    is_active: bool
    created_at: str
    episode_count: int
    last_activity: Optional[str] = None
    subscription_expires_at: Optional[str] = None
    last_login: Optional[str] = None
    email_verified: bool = False  # NEW: Track email verification status


class UserAdminUpdate(BaseModel):
    tier: Optional[str] = None
    is_active: Optional[bool] = None
    subscription_expires_at: Optional[str] = None


@router.get("/users/full", response_model=List[UserAdminOut])
def admin_users_full(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> List[UserAdminOut]:
    del admin_user
    counts: Dict[UUID, int] = dict(
        session.exec(select(Episode.user_id, func.count(Episode.id)).group_by(Episode.user_id)).all()
    )
    latest: Dict[UUID, Optional[datetime]] = dict(
        session.exec(select(Episode.user_id, func.max(Episode.processed_at)).group_by(Episode.user_id)).all()
    )
    
    # Get email verification status for each user
    # A user is email-verified if they have ANY verified EmailVerification record
    # OR if they signed in via Google (Google users are auto-verified)
    verified_user_ids: set[UUID] = set()
    if VERIFICATION_AVAILABLE:
        verified_records = session.exec(
            select(EmailVerification.user_id)
            .where(EmailVerification.verified_at != None)  # noqa: E711
            .distinct()
        ).all()
        verified_user_ids = set(verified_records)

    users = crud.get_all_users(session)
    out: List[UserAdminOut] = []
    for user in users:
        last_activity = latest.get(user.id) or user.created_at
        # User is verified if they have a verified EmailVerification OR if they have a google_id
        # (Google users are automatically verified since Google already verified their email)
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
                email_verified=is_verified,  # Check if user email is verified (via EmailVerification or Google OAuth)
            )
        )
    return out


@router.patch("/users/{user_id}", response_model=UserAdminOut)
def admin_update_user(
    user_id: UUID,
    update: UserAdminUpdate,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> UserAdminOut:
    log.debug("admin_update_user payload user_id=%s %s", str(user_id), update.model_dump())
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
            # Normalize "starter" to "free" for backward compatibility
            # Frontend uses "starter" but backend still uses "free" internally
            if norm_tier == "starter":
                norm_tier = "free"
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid tier value")
        
        # Special handling for admin/superadmin tiers
        if norm_tier in ADMIN_TIERS:
            # Only superadmin can assign admin/superadmin tiers
            if not admin_is_superadmin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only superadmin can assign admin or superadmin tiers."
                )
            # Cannot assign superadmin tier to anyone (it's reserved)
            if norm_tier == "superadmin":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Superadmin tier cannot be assigned. It is reserved for the primary admin account."
                )
            # When setting tier to 'admin', also set role to 'admin'
            if norm_tier == "admin":
                user.role = "admin"
                user.is_admin = True
                log.info("Setting user %s role to 'admin' and is_admin=True", user_id)
        else:
            # When setting to a regular tier, clear admin role if user isn't superadmin
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
                log.warning(
                    "Bad subscription_expires_at '%s' for user %s: %s", raw, user_id, exc
                )
                raise HTTPException(
                    status_code=400,
                    detail="Invalid subscription_expires_at format; use YYYY-MM-DD or ISO8601",
                )

    if changed:
        log.info(
            "Admin %s updating user %s; fields changed tier=%s is_active=%s subscription_expires_at=%s",
            admin_user.email,
            user_id,
            update.tier is not None,
            update.is_active is not None,
            update.subscription_expires_at is not None,
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
    
    # Check email verification status
    email_verified = False
    if VERIFICATION_AVAILABLE:
        verified_check = session.exec(
            select(EmailVerification.user_id)
            .where(
                EmailVerification.user_id == user.id,
                EmailVerification.verified_at != None  # noqa: E711
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


@router.post("/users/{user_id}/verify-email", status_code=status.HTTP_200_OK)
def admin_verify_user_email(
    user_id: UUID,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    Manually verify a user's email address (Admin only).
    
    Creates a verified EmailVerification record for the user if one doesn't exist.
    This allows admins to manually verify users who are having trouble with
    the automated verification process.
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
            EmailVerification.verified_at != None  # noqa: E711
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
    # Use a special admin code to indicate manual verification
    now = datetime.utcnow()
    verification = EmailVerification(
        user_id=user.id,
        code="ADMIN-VER",  # Must be <= 12 chars to fit database column
        jwt_token=None,
        expires_at=now,  # Already expired since it's pre-verified
        verified_at=now,  # Mark as verified immediately
        used=True,  # Mark as used
        created_at=now,
    )
    
    # CRITICAL: Set user.is_active = True so they can actually log in
    # This is what the normal verification flow does (see verification.py line 136)
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


@router.post("/users/{user_id}/password-reset", status_code=status.HTTP_200_OK)
def admin_trigger_password_reset(
    user_id: UUID,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    Trigger a password reset email for a user (Admin only).
    
    This generates a valid password reset token and sends the standard
    "Reset your password" email to the user, just as if they had
    requested it themselves via the forgot password page.
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
                PasswordReset.used_at == None,  # noqa: E711
            )
        ).all()
        for reset in resets:
            reset.used_at = datetime.utcnow()
            session.add(reset)
        session.commit()
    except Exception:
        session.rollback()

    # Generate new token
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits
    token = "".join(secrets.choice(alphabet) for _ in range(40))
    expires = datetime.utcnow() + timedelta(minutes=30)
    
    # Record the reset request (attributed to admin action implicitly via logs)
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
        # We still return success because the token was generated, but warn about email
        return {
            "success": True, 
            "message": "Token generated but email failed to send", 
            "token": token, # Return token to admin as fallback if email fails
            "error": str(e)
        }

    return {
        "success": True,
        "message": f"Password reset email sent to {user.email}",
        "user_id": str(user.id)
    }


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a user and all their data (Superadmin only)",
)
def delete_user(
    user_id: str,
    confirm_email: str = Body(..., embed=True),
    session: Session = Depends(get_session),
    admin: User = Depends(get_current_superadmin_user),  # Changed to superadmin only
) -> Dict[str, Any]:
    """
    Delete a user and ALL their associated data.
    
    **SUPERADMIN ONLY**: Only superadmin can delete users. Regular admins can only deactivate.
    
    **WARNING**: This is permanent and irreversible!
    
    **Deletes**:
    - User account
    - All podcasts
    - All episodes  
    - All media items & transcripts
    - All templates
    - All subscriptions & notifications
    - All assistant conversations
    - All verification records
    - All database records
    
    **Does NOT delete** (manual cleanup required):
    - GCS files (gs://ppp-media-us-west1/{user_id}/...)
    
    **Parameters**:
    - user_id: UUID of user to delete
    - confirm_email: Must match user's email (safety check)
    
    **Body**:
    ```json
    {
        "confirm_email": "user@example.com"
    }
    ```
    """
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
    # This prevents accidental deletion of active or paying customers
    if user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot delete active user. Please set user to inactive first. (Current status: Active)"
        )
    
    user_tier = (user.tier or "free").strip().lower()
    # Normalize "starter" to "free" (frontend uses "starter", backend uses "free")
    if user_tier == "starter":
        user_tier = "free"
    # Allow deletion of free/starter tier and admin tier (but not superadmin, protected, or paid tiers)
    if user_tier not in ["free", "", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot delete paid user. User must be on 'starter' or 'admin' tier. (Current tier: {user.tier})"
        )
    
    log.warning(f"[ADMIN] Safety checks passed (inactive + free tier). Confirmed deletion of user: {user.email} ({user.id})")
    
    # Capture user details BEFORE deletion (object will be detached after delete)
    user_id_hex = user.id.hex
    user_email_copy = user.email
    user_id_str = str(user.id)
    
    # Count items before deletion (for summary)
    # Count transcripts (need to join through media items)
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
        
        # 1. Media transcripts (before media items due to foreign key)
        transcripts = session.exec(select(MediaTranscript).join(MediaItem).where(MediaItem.user_id == user.id)).all()
        for transcript in transcripts:
            session.delete(transcript)
        log.info(f"[ADMIN] Deleted {transcript_count} media transcripts for user {user.id}")
        
        # 2. Media items
        # Use savepoint to prevent transaction abort if media item fetch fails (e.g. missing column)
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
            # If ORM fails due to missing columns, try raw SQL deletion as fallback
            try:
                log.info("[ADMIN] Attempting raw SQL deletion for media items...")
                session.execute(text("DELETE FROM mediaitem WHERE user_id = :uid"), {"uid": user.id})
                session.commit() # Commit immediately to ensure it sticks
                log.info(f"[ADMIN] Deleted media items via raw SQL for user {user.id}")
            except Exception as sql_err:
                log.error(f"[ADMIN] Raw SQL deletion failed too: {sql_err}")
        
        # 3. Episode sections (before episodes due to foreign key)
        sections = session.exec(select(EpisodeSection).where(EpisodeSection.user_id == user.id)).all()
        for section in sections:
            session.delete(section)
        log.info(f"[ADMIN] Deleted {section_count} episode sections for user {user.id}")
        
        # 4. Episodes
        episodes = session.exec(select(Episode).where(Episode.user_id == user.id)).all()
        for episode in episodes:
            session.delete(episode)
        log.info(f"[ADMIN] Deleted {episode_count} episodes for user {user.id}")
        
        # 5. Templates (must delete before podcasts due to foreign key to podcast)
        templates = session.exec(select(PodcastTemplate).where(PodcastTemplate.user_id == user.id)).all()
        for template in templates:
            session.delete(template)
        log.info(f"[ADMIN] Deleted {template_count} templates for user {user.id}")
        
        # 5b. Get podcasts first (before deleting related records to avoid autoflush issues)
        podcasts = session.exec(select(Podcast).where(Podcast.user_id == user.id)).all()
        podcast_ids = [podcast.id for podcast in podcasts]
        
        # 5c. Podcast distribution status (must delete before podcasts due to foreign key podcastdistributionstatus_podcast_id_fkey)
        # Delete FIRST before websites to avoid autoflush issues
        dist_status_count = 0
        if podcast_ids:
            # Delete by user_id first
            dist_status_by_user = session.exec(
                select(PodcastDistributionStatus).where(PodcastDistributionStatus.user_id == user.id)
            ).all()
            deleted_dist_ids = {d.id for d in dist_status_by_user}
            for dist_status in dist_status_by_user:
                session.delete(dist_status)
            
            # Also delete by podcast_id to catch any edge cases
            dist_status_by_podcast = session.exec(
                select(PodcastDistributionStatus).where(PodcastDistributionStatus.podcast_id.in_(podcast_ids))
            ).all()
            # Only delete if not already deleted
            for dist_status in dist_status_by_podcast:
                if dist_status.id not in deleted_dist_ids:
                    session.delete(dist_status)
                    deleted_dist_ids.add(dist_status.id)
            
            dist_status_count = len(deleted_dist_ids)
            if dist_status_count > 0:
                log.info(f"[ADMIN] Marked {dist_status_count} distribution status records for deletion for user {user.id}")
        
        # 5d. Podcast websites (must delete before podcasts due to foreign key podcastwebsite_podcast_id_fkey)
        # Delete by both user_id and podcast_id to ensure we catch all websites
        website_count = 0
        if WEBSITE_AVAILABLE:
            # Delete by user_id
            websites_by_user = session.exec(
                select(PodcastWebsite).where(PodcastWebsite.user_id == user.id)
            ).all()
            deleted_website_ids = {w.id for w in websites_by_user}
            for website in websites_by_user:
                session.delete(website)
            
            # Also delete by podcast_id to catch any edge cases
            if podcast_ids:
                websites_by_podcast = session.exec(
                    select(PodcastWebsite).where(PodcastWebsite.podcast_id.in_(podcast_ids))
                ).all()
                # Only delete if not already deleted
                for website in websites_by_podcast:
                    if website.id not in deleted_website_ids:
                        session.delete(website)
                        deleted_website_ids.add(website.id)
            
            website_count = len(deleted_website_ids)
            if website_count > 0:
                log.info(f"[ADMIN] Marked {website_count} website records for deletion for user {user.id}")
        
        # Flush all related record deletions (distribution status + websites) before deleting podcasts
        if dist_status_count > 0 or (WEBSITE_AVAILABLE and website_count > 0):
            session.flush()
            if dist_status_count > 0:
                log.info(f"[ADMIN] Deleted {dist_status_count} distribution status records for user {user.id}")
            if WEBSITE_AVAILABLE and website_count > 0:
                log.info(f"[ADMIN] Deleted {website_count} website records for user {user.id}")
        
        # 6. Podcasts (now safe to delete since all referencing records are gone)
        for podcast in podcasts:
            session.delete(podcast)
        log.info(f"[ADMIN] Deleted {podcast_count} podcasts for user {user.id}")
        
        # 7. Terms acceptance records (must delete before user due to foreign key)
        terms_acceptances = session.exec(select(UserTermsAcceptance).where(UserTermsAcceptance.user_id == user.id)).all()
        terms_count = len(terms_acceptances)
        for terms in terms_acceptances:
            session.delete(terms)
        log.info(f"[ADMIN] Deleted {terms_count} terms acceptance records for user {user.id}")
        
        # 8. Verification records (email verifications, password resets, etc.)
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
            verification_count = len(email_verifications) + len(ownership_verifications) + len(password_resets)
            log.info(f"[ADMIN] Deleted {verification_count} verification records for user {user.id}")
        
        # 9. Subscriptions
        if SUBSCRIPTION_AVAILABLE:
            subscriptions = session.exec(select(Subscription).where(Subscription.user_id == user.id)).all()
            subscription_count = len(subscriptions)
            for sub in subscriptions:
                session.delete(sub)
            log.info(f"[ADMIN] Deleted {subscription_count} subscription records for user {user.id}")
        
        # 10. Notifications
        if NOTIFICATION_AVAILABLE:
            notifications = session.exec(select(Notification).where(Notification.user_id == user.id)).all()
            notification_count = len(notifications)
            for notif in notifications:
                session.delete(notif)
            log.info(f"[ADMIN] Deleted {notification_count} notification records for user {user.id}")
        
        # 11. Assistant conversations and messages
        if ASSISTANT_AVAILABLE:
            conversations = session.exec(select(AssistantConversation).where(AssistantConversation.user_id == user.id)).all()
            conversation_count = len(conversations)
            message_count = 0
            
            # First pass: Delete ALL messages from ALL conversations
            for conv in conversations:
                messages = session.exec(select(AssistantMessage).where(AssistantMessage.conversation_id == conv.id)).all()
                for msg in messages:
                    session.delete(msg)
                    message_count += 1
            
            # Flush to commit message deletions before deleting conversations
            session.flush()
            
            # Second pass: Now safe to delete conversations (no more message references)
            for conv in conversations:
                session.delete(conv)
            
            # Delete guidance records
            guidances = session.exec(select(AssistantGuidance).where(AssistantGuidance.user_id == user.id)).all()
            for guide in guidances:
                session.delete(guide)
            
            assistant_count = conversation_count + len(guidances) + message_count
            log.info(f"[ADMIN] Deleted {assistant_count} assistant records for user {user.id} ({message_count} messages, {conversation_count} conversations, {len(guidances)} guidance)")
        
        # 12. User account (finally!)
        session.delete(user)
        log.warning(f"[ADMIN] Deleted user account: {user_email_copy} ({user_id_str})")
        
        # Commit all deletions
        commit_with_retry(session)
        
        # 14. GCS cleanup (automatic for inactive/free users)
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
                    
                    # List and delete all blobs with this user's prefix
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


@router.get("/users/{user_id}/credits")
async def get_user_credits(
    user_id: UUID,
    page: int = 1,
    per_page: int = 20,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    Get credit usage details for a specific user (Admin only).
    
    Args:
        page: Page number (1-indexed)
        per_page: Items per page (20, 50, or 100)
    
    Returns:
        - Credit balance
        - Monthly usage breakdown
        - Recent charges (paginated)
        - Tier allocation
    """
    log.info(f"[ADMIN] Credit check requested by {admin_user.email} for user_id: {user_id}, page={page}, per_page={per_page}")
    
    # Validate per_page
    if per_page not in [20, 50, 100]:
        per_page = 20
    
    # Verify user exists
    user = crud.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get credit balance
    from api.services.billing import credits
    balance = credits.get_user_credit_balance(session, user_id)
    
    # Get tier allocation
    from api.services import tier_service
    tier = getattr(user, 'tier', 'free') or 'free'
    tier_credits = tier_service.get_tier_credits(session, tier)
    
    # Get monthly breakdown
    from datetime import datetime, timezone
    from api.services.billing import usage as usage_svc
    
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    breakdown = usage_svc.month_credits_breakdown(session, user_id, start_of_month, now)
    
    # Get paginated charges
    from sqlmodel import select, desc as sqlmodel_desc, func
    from api.models.usage import ProcessingMinutesLedger
    
    # Count total charges
    count_stmt = (
        select(func.count(ProcessingMinutesLedger.id))
        .where(ProcessingMinutesLedger.user_id == user_id)
    )
    total_count = session.exec(count_stmt).one()
    
    # Get paginated charges
    offset = (page - 1) * per_page
    stmt = (
        select(ProcessingMinutesLedger)
        .where(ProcessingMinutesLedger.user_id == user_id)
        .order_by(sqlmodel_desc(ProcessingMinutesLedger.created_at))
        .limit(per_page)
        .offset(offset)
    )
    recent = session.exec(stmt).all()
    
    recent_charges = []
    for entry in recent:
        charge = {
            "id": entry.id,
            "timestamp": entry.created_at.isoformat() if entry.created_at else None,
            "episode_id": str(entry.episode_id) if entry.episode_id else None,
            "direction": entry.direction.value if hasattr(entry.direction, 'value') else str(entry.direction),
            "reason": entry.reason.value if hasattr(entry.reason, 'value') else str(entry.reason),
            "credits": float(entry.credits),
            "minutes": entry.minutes,
            "notes": entry.notes
        }
        
        # Try to get episode title if episode_id exists
        if entry.episode_id:
            try:
                episode = session.get(Episode, entry.episode_id)
                if episode:
                    charge["episode_title"] = episode.title
            except Exception:
                pass
        
        recent_charges.append(charge)
    
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
    
    return {
        "user_id": str(user_id),
        "email": user.email,
        "first_name": getattr(user, 'first_name', None),
        "last_name": getattr(user, 'last_name', None),
        "tier": tier,
        "credits_balance": float(balance),
        "credits_allocated": float(tier_credits) if tier_credits is not None else None,
        "credits_used_this_month": float(breakdown.get('total', 0)),
        "credits_breakdown": {
            "transcription": float(breakdown.get('transcription', 0)),
            "assembly": float(breakdown.get('assembly', 0)),
            "tts_generation": float(breakdown.get('tts_generation', 0)),
            "auphonic_processing": float(breakdown.get('auphonic_processing', 0)),
            "storage": float(breakdown.get('storage', 0)),
            "ai_metadata": float(breakdown.get('ai_metadata', 0)),
        },
        "recent_charges": recent_charges,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total_count,
            "total_pages": total_pages
        }
    }


class RefundCreditsRequest(BaseModel):
    ledger_entry_ids: List[int]
    notes: Optional[str] = None
    manual_credits: Optional[float] = Field(None, description="Optional manual refund amount. If provided, refunds this amount as a single adjustment instead of per-entry refunds.")


class AwardCreditsRequest(BaseModel):
    credits: float
    reason: str
    notes: Optional[str] = None


@router.post("/users/{user_id}/credits/refund")
async def refund_user_credits(
    user_id: UUID,
    request: RefundCreditsRequest,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    Refund credits for specific ledger entries (Admin only).
    
    Credits are refunded back to their original bank (monthly or add-on).
    """
    log.info(f"[ADMIN] Credit refund requested by {admin_user.email} for user_id: {user_id}, entries: {request.ledger_entry_ids}")
    
    # Verify user exists
    user = crud.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get ledger entries
    from sqlmodel import select
    from api.models.usage import ProcessingMinutesLedger, LedgerDirection
    
    stmt = select(ProcessingMinutesLedger).where(
        ProcessingMinutesLedger.id.in_(request.ledger_entry_ids),
        ProcessingMinutesLedger.user_id == user_id,
        ProcessingMinutesLedger.direction == LedgerDirection.DEBIT
    )
    entries = session.exec(stmt).all()
    
    if not entries:
        raise HTTPException(status_code=404, detail="No valid debit entries found to refund")
    
    # Check for already refunded entries
    found_entry_ids = {entry.id for entry in entries}
    missing_entry_ids = set(request.ledger_entry_ids) - found_entry_ids
    
    if missing_entry_ids:
        # Some entries weren't found - check if they're already refunded or invalid
        from sqlmodel import select
        all_requested = session.exec(
            select(ProcessingMinutesLedger)
            .where(ProcessingMinutesLedger.id.in_(list(missing_entry_ids)))
            .where(ProcessingMinutesLedger.user_id == user_id)
        ).all()
        
        invalid_entries = []
        for req_id in missing_entry_ids:
            found = any(e.id == req_id for e in all_requested)
            if not found:
                invalid_entries.append(req_id)
            else:
                # Check if it's a credit (already refunded) or belongs to different user
                entry = next((e for e in all_requested if e.id == req_id), None)
                if entry:
                    if entry.direction == LedgerDirection.CREDIT:
                        invalid_entries.append(f"{req_id} (already refunded)")
                    elif entry.user_id != user_id:
                        invalid_entries.append(f"{req_id} (wrong user)")
        
        if invalid_entries:
            raise HTTPException(
                status_code=400, 
                detail=f"Some entries cannot be refunded: {', '.join(map(str, invalid_entries))}"
            )
    
    # Allow partial refunds - only refund the entries we found
    if len(entries) < len(request.ledger_entry_ids):
        log.info(f"[ADMIN] Partial refund: {len(entries)} of {len(request.ledger_entry_ids)} entries will be refunded")
    
    # Calculate total credits to refund
    calculated_total = sum(float(entry.credits) for entry in entries)
    
    # Check if manual amount is provided
    if request.manual_credits is not None:
        # Manual adjustment mode - refund a custom amount
        if request.manual_credits <= 0:
            raise HTTPException(status_code=400, detail="Manual refund amount must be positive")
        
        if request.manual_credits > calculated_total:
            raise HTTPException(
                status_code=400, 
                detail=f"Manual refund amount ({request.manual_credits:.1f}) cannot exceed selected charges total ({calculated_total:.1f})"
            )
        
        total_refund = request.manual_credits
        is_partial_adjustment = request.manual_credits < calculated_total
        
        # Refund credits using wallet system
        from api.services.billing.wallet import refund_to_wallet
        from api.services.billing.credits import refund_credits
        from api.models.usage import LedgerReason
        
        # Refund to wallet (use earliest entry's period for wallet tracking)
        earliest_entry = min(entries, key=lambda e: e.created_at) if entries else None
        refund_to_wallet(
            session=session,
            user_id=user_id,
            amount=total_refund,
            original_period=earliest_entry.created_at.strftime("%Y-%m") if earliest_entry and earliest_entry.created_at else None
        )
        
        # Create single manual adjustment refund entry
        entry_ids_str = ", ".join(str(e.id) for e in entries)
        refund_notes = f"Admin manual adjustment refund for entries: {entry_ids_str}"
        if is_partial_adjustment:
            refund_notes += f" (partial: {total_refund:.1f} of {calculated_total:.1f} credits)"
        if request.notes:
            refund_notes += f" - {request.notes}"
        
        # Use MANUAL_ADJUST reason for manual adjustments
        refund_entry = refund_credits(
            session=session,
            user_id=user_id,
            credits=total_refund,
            reason=LedgerReason.MANUAL_ADJUST,
            episode_id=entries[0].episode_id if len(entries) == 1 else None,  # Use episode_id if all entries are for same episode
            notes=refund_notes
        )
        refunded_entries = [refund_entry]
        
        log.info(f"[ADMIN] Manual adjustment refund: {total_refund:.1f} credits (selected entries total: {calculated_total:.1f})")
    else:
        # Standard refund mode - refund each entry individually
        total_refund = calculated_total
        
        # Refund credits using wallet system
        from api.services.billing.wallet import refund_to_wallet
        from api.services.billing.credits import refund_credits
        from api.models.usage import LedgerReason
        
        refunded_entries = []
        for entry in entries:
            # Refund to wallet (tracks which bank to refund to)
            refund_to_wallet(
                session=session,
                user_id=user_id,
                amount=float(entry.credits),
                original_period=entry.created_at.strftime("%Y-%m") if entry.created_at else None
            )
            
            # Create refund ledger entry
            # Include entry ID in notes for tracking which entry was refunded
            refund_notes = f"Admin refund for {entry.reason.value} (refunded_entry_id: {entry.id})"
            if request.notes:
                refund_notes += f" - {request.notes}"
            if entry.episode_id:
                refund_notes += f" (episode: {entry.episode_id})"
            
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


@router.post("/users/{user_id}/credits/award")
async def award_user_credits(
    user_id: UUID,
    request: AwardCreditsRequest,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    Award credits to a user (Admin only).
    
    Awarded credits are added as add-on (purchased) credits.
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


class DenyRefundRequest(BaseModel):
    """Request to deny a refund"""
    notification_id: str
    denial_reason: str = Field(..., min_length=10, description="Reason for denial (minimum 10 characters)")


@router.post("/users/refund-requests/{notification_id}/deny")
async def deny_refund_request(
    notification_id: UUID,
    request: DenyRefundRequest,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    Deny a refund request with a reason (Admin only).
    
    Updates the refund request status to "denied" and notifies the user.
    """
    if not NOTIFICATION_AVAILABLE:
        raise HTTPException(status_code=400, detail="Notifications not available")
    
    # Get the admin notification
    admin_notification = session.get(Notification, notification_id)
    if not admin_notification:
        raise HTTPException(status_code=404, detail="Refund request not found")
    
    if admin_notification.user_id != admin_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this refund request")
    
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


@router.get("/users/refund-requests", response_model=List[RefundRequestResponse])
async def get_refund_requests(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
    limit: int = 50,
) -> List[RefundRequestResponse]:
    """
    Get all refund requests for admin review.
    
    Returns notifications of type "refund_request" with parsed details.
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


# Enhanced refund request detail models
class LedgerEntryDetail(BaseModel):
    """Detailed ledger entry for refund analysis"""
    id: int
    timestamp: datetime
    direction: str  # DEBIT or CREDIT
    reason: str
    credits: float
    minutes: int
    notes: Optional[str] = None
    cost_breakdown: Optional[Dict[str, Any]] = None
    correlation_id: Optional[str] = None
    credit_source: Optional[str] = None  # "monthly", "add-on", "rollover"
    episode_id: Optional[str] = None
    episode_title: Optional[str] = None
    can_refund: bool = True  # Whether this entry can be refunded (not already refunded)
    already_refunded: bool = False  # Whether this entry has already been refunded
    refund_status: Optional[str] = None  # "pending", "approved", "denied"
    service_delivered: Optional[bool] = None  # Whether the service was actually delivered (episode processed, TTS generated, etc.)
    service_details: Optional[Dict[str, Any]] = None  # Details about what was delivered


class EpisodeRefundDetail(BaseModel):
    """Comprehensive episode information for refund decision"""
    id: str
    title: str
    status: str
    created_at: datetime
    processed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    episode_number: Optional[int] = None
    season_number: Optional[int] = None
    podcast_title: Optional[str] = None
    has_final_audio: bool = False
    is_published: bool = False
    is_published_to_spreaker: bool = False
    spreaker_episode_id: Optional[str] = None
    error_message: Optional[str] = None
    spreaker_publish_error: Optional[str] = None
    spreaker_publish_error_detail: Optional[str] = None
    auphonic_processed: bool = False
    auphonic_error: Optional[str] = None
    gcs_audio_path: Optional[str] = None
    final_audio_path: Optional[str] = None
    audio_file_size: Optional[int] = None
    show_notes: Optional[str] = None
    brief_summary: Optional[str] = None
    episode_tags: Optional[List[str]] = None
    episode_chapters: Optional[List[Dict[str, Any]]] = None
    # Charges for this episode in the refund request
    ledger_entries: List[LedgerEntryDetail]
    total_credits_requested: float
    total_credits_already_refunded: float
    net_credits_to_refund: float
    # Service delivery status
    service_delivered: bool
    can_be_restored: bool
    refund_recommendation: Optional[str] = None  # "full_refund", "partial_refund", "no_refund", "conditional_refund"


class UserRefundContext(BaseModel):
    """User context for refund decision"""
    user_id: str
    email: str
    tier: Optional[str] = None
    account_created_at: datetime
    is_active: bool
    subscription_expires_at: Optional[datetime] = None
    total_credits_used_all_time: float = 0.0
    total_credits_used_this_month: float = 0.0
    current_credit_balance: float = 0.0
    monthly_credit_allocation: Optional[float] = None
    previous_refund_count: int = 0
    previous_refund_total_credits: float = 0.0
    last_refund_date: Optional[datetime] = None


class RefundRequestDetail(BaseModel):
    """Comprehensive refund request detail for admin decision-making"""
    # Request basics
    notification_id: str
    request_created_at: datetime
    request_read_at: Optional[datetime] = None
    user_reason: str
    user_notes: Optional[str] = None
    
    # User context
    user: UserRefundContext
    
    # Episodes with refund requests (grouped by episode)
    episodes: List[EpisodeRefundDetail] = []
    
    # Non-episode charges (TTS library, storage, etc. - not tied to an episode)
    non_episode_charges: List[LedgerEntryDetail] = []
    
    # Summary totals
    total_credits_requested: float
    total_credits_already_refunded: float
    net_credits_to_refund: float
    
    # Time analysis
    days_since_charges: float
    hours_since_request: float
    
    # Business context
    refund_eligibility_notes: List[str] = []
    credit_source_breakdown: Dict[str, float] = {}  # "monthly": 100.0, "add-on": 50.0


@router.get("/users/refund-requests/{notification_id}/detail", response_model=RefundRequestDetail)
async def get_refund_request_detail(
    notification_id: UUID,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> RefundRequestDetail:
    """
    Get comprehensive details for a refund request to help with decision-making.
    
    Provides all context needed to evaluate a refund request:
    - User account history and usage patterns
    - Episode details and processing status
    - Detailed ledger entries with cost breakdowns
    - Refund history for the user
    - Time analysis and eligibility notes
    """
    if not NOTIFICATION_AVAILABLE:
        raise HTTPException(status_code=400, detail="Notifications not available")
    
    # Get the notification
    notification = session.get(Notification, notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Refund request not found")
    
    if notification.type != "refund_request":
        raise HTTPException(status_code=400, detail="Notification is not a refund request")
    
    # Parse notification body to extract request details
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
                log.debug(f"Parsed details from Details section: {details}")
            except json.JSONDecodeError as e:
                log.warning(f"Failed to parse Details JSON: {e}, body snippet: {notification.body[:200]}")
                # Try parsing the whole body as JSON (for user notifications)
                try:
                    details = json.loads(notification.body)
                    log.debug(f"Parsed details from full body: {details}")
                except json.JSONDecodeError:
                    log.error(f"Could not parse notification body as JSON: {notification.body[:500]}")
        else:
            # If no "Details:" section, try parsing the whole body as JSON (for user notifications)
            try:
                details = json.loads(notification.body)
                log.debug(f"Parsed details from full body (no Details section): {details}")
            except json.JSONDecodeError as e:
                log.warning(f"Failed to parse notification body as JSON: {e}, body: {notification.body[:500]}")
    
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
    
    # Get previous refund history (credits are refunds)
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
    
    # Check for existing refunds for these entries
    # Look for refund entries that reference the original entry IDs
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
        # Try to extract entry ID from notes - look for "refunded_entry_id: X" pattern first
        import re
        match = re.search(r'refunded_entry_id:\s*(\d+)', refund.notes or "")
        if not match:
            # Fallback: look for "(entry X)" pattern
            match = re.search(r'\(entry\s+(\d+)\)', refund.notes or "")
        if match:
            refunded_entry_ids.add(int(match.group(1)))
        
        # Also check if refund matches by episode_id, reason, and credits (fuzzy match)
        # This handles cases where notes don't have the entry ID
        if refund.episode_id:
            for entry_id in ledger_entry_ids:
                entry = session.get(ProcessingMinutesLedger, entry_id)
                if entry and entry.episode_id == refund.episode_id:
                    # Check if credits match (within 0.1 tolerance) and reason matches
                    if abs(entry.credits - refund.credits) < 0.1 and entry.reason == refund.reason:
                        # Check if refund was created after the charge
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
        
        # Parse cost breakdown
        cost_breakdown = None
        if entry.cost_breakdown_json:
            try:
                cost_breakdown = json.loads(entry.cost_breakdown_json)
            except json.JSONDecodeError:
                pass
        
        # Determine credit source (simplified - would need wallet tracking for accuracy)
        credit_source = "monthly"  # Default assumption
        
        # Check if already refunded
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
                    # Determine if service was delivered
                    if entry.reason in [LedgerReason.TRANSCRIPTION, LedgerReason.ASSEMBLY, LedgerReason.AUPHONIC_PROCESSING]:
                        service_delivered = episode.status in ["processed", "published"]
                        service_details = {
                            "episode_status": episode.status.value if hasattr(episode.status, 'value') else str(episode.status),
                            "has_final_audio": bool(episode.final_audio_path or episode.gcs_audio_path),
                            "is_published": episode.status == "published" if hasattr(episode.status, 'value') else False,
                            "duration_ms": episode.duration_ms,
                            "processed_at": episode.processed_at.isoformat() if episode.processed_at else None,
                            "error_message": getattr(episode, 'error_message', None) or getattr(episode, 'spreaker_publish_error', None),
                            "auphonic_processed": getattr(episode, 'auphonic_processed', False),
                        }
                    elif entry.reason == LedgerReason.TTS_GENERATION:
                        # For TTS, check if media item exists and was used
                        service_delivered = True  # Assume delivered if charged
                        service_details = {
                            "service_type": "TTS Generation",
                            "note": "TTS files may have been saved to media library"
                        }
            except Exception as e:
                log.warning(f"Failed to get episode details for entry {entry.id}: {e}")
        elif entry.reason == LedgerReason.TTS_LIBRARY:
            # TTS library charges - service was delivered if charged
            service_delivered = True
            service_details = {
                "service_type": "TTS Library",
                "note": "TTS file saved to media library"
            }
        elif entry.reason == LedgerReason.STORAGE:
            # Storage charges - service was delivered (storage was used)
            service_delivered = True
            service_details = {
                "service_type": "Storage",
                "note": "Cloud storage was used"
            }
        
        if entry.direction == LedgerDirection.DEBIT:
            if not already_refunded:
                total_requested += entry.credits
            else:
                total_already_refunded += entry.credits
            # Ensure entry.created_at is timezone-aware for comparison
            entry_created_at = entry.created_at
            if entry_created_at and entry_created_at.tzinfo is None:
                entry_created_at = entry_created_at.replace(tzinfo=tz.utc)
            if entry_created_at and (earliest_charge_date is None or entry_created_at < earliest_charge_date):
                earliest_charge_date = entry_created_at
        elif entry.direction == LedgerDirection.CREDIT:
            total_already_refunded += entry.credits
        
        # Store entry detail for grouping
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
    
    # Group ledger entries by episode_id
    from collections import defaultdict
    episodes_dict = defaultdict(lambda: {"entries": [], "episode_id": None})
    non_episode_entries = []
    
    for entry_detail in ledger_entries_list:
        if entry_detail.episode_id:
            episodes_dict[entry_detail.episode_id]["entries"].append(entry_detail)
            episodes_dict[entry_detail.episode_id]["episode_id"] = entry_detail.episode_id
        else:
            non_episode_entries.append(entry_detail)
    
    # Build episode details for each episode in the refund request
    episodes_list = []
    for episode_id_str, episode_data in episodes_dict.items():
        try:
            episode_id = UUID(episode_id_str)
            episode = session.get(Episode, episode_id)
            
            if not episode:
                continue
            
            # Get podcast title
            podcast = session.get(Podcast, episode.podcast_id)
            podcast_title = None
            if podcast:
                # Podcast model might use 'name' or 'title' - try both
                podcast_title = getattr(podcast, 'title', None) or getattr(podcast, 'name', None)
            
            # Get episode entries
            episode_entries = episode_data["entries"]
            
            # Calculate totals for this episode
            episode_total_requested = sum(e.credits for e in episode_entries if e.can_refund and not e.already_refunded)
            episode_total_refunded = sum(e.credits for e in episode_entries if e.already_refunded)
            episode_net_refund = episode_total_requested - episode_total_refunded
            
            # Determine service delivery status
            from api.models.enums import EpisodeStatus
            episode_status_str = episode.status.value if hasattr(episode.status, 'value') else str(episode.status)
            has_final_audio = bool(episode.final_audio_path or episode.gcs_audio_path)
            is_published = episode_status_str == "published"
            is_published_to_spreaker = getattr(episode, 'is_published_to_spreaker', False)
            service_delivered = episode_status_str in ["processed", "published"]
            can_be_restored = has_final_audio and episode_status_str != "error"
            
            # Parse episode tags and chapters
            episode_tags = None
            try:
                if episode.episode_tags:
                    episode_tags = json.loads(episode.episode_tags) if isinstance(episode.episode_tags, str) else episode.episode_tags
            except (json.JSONDecodeError, TypeError):
                episode_tags = None
            
            episode_chapters = None
            try:
                if episode.episode_chapters:
                    episode_chapters = json.loads(episode.episode_chapters) if isinstance(episode.episode_chapters, str) else episode.episode_chapters
            except (json.JSONDecodeError, TypeError):
                episode_chapters = None
            
            # Determine refund recommendation
            refund_recommendation = None
            if episode_total_requested == 0:
                refund_recommendation = "no_refund"  # Already refunded
            elif not service_delivered:
                refund_recommendation = "full_refund"  # Service failed
            elif is_published:
                refund_recommendation = "no_refund"  # Published - don't refund
            elif has_final_audio and service_delivered:
                refund_recommendation = "conditional_refund"  # Service delivered but user wants refund
            else:
                refund_recommendation = "partial_refund"  # Some service delivered
            
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
                is_published_to_spreaker=is_published_to_spreaker,
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
                episode_tags=episode_tags,
                episode_chapters=episode_chapters,
                ledger_entries=episode_entries,
                total_credits_requested=episode_total_requested,
                total_credits_already_refunded=episode_total_refunded,
                net_credits_to_refund=episode_net_refund,
                service_delivered=service_delivered,
                can_be_restored=can_be_restored,
                refund_recommendation=refund_recommendation
            ))
        except (ValueError, AttributeError, Exception) as e:
            log.warning(f"Failed to get episode details for {episode_id_str}: {e}")
            continue
    
    # Calculate time metrics
    # Ensure both datetimes are timezone-aware for comparison
    if earliest_charge_date:
        # If earliest_charge_date is naive, make it timezone-aware (assume UTC)
        if earliest_charge_date.tzinfo is None:
            earliest_charge_date = earliest_charge_date.replace(tzinfo=tz.utc)
        days_since_charges = (now - earliest_charge_date).total_seconds() / 86400.0
    else:
        days_since_charges = 0.0
    
    # Ensure notification.created_at is timezone-aware
    notification_created_at = notification.created_at
    if notification_created_at and notification_created_at.tzinfo is None:
        notification_created_at = notification_created_at.replace(tzinfo=tz.utc)
    hours_since_request = (now - notification_created_at).total_seconds() / 3600.0 if notification_created_at else 0.0
    
    # Build eligibility notes
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
    
    # Build user context
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
    
    # Build credit source breakdown (simplified)
    credit_source_breakdown = {"monthly": total_requested}  # Would need wallet tracking for accuracy
    
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


# Admin action log models and endpoints
class RefundLogEntry(BaseModel):
    """Refund log entry for admin view"""
    id: int
    action_type: str
    admin_email: str
    target_user_email: str
    target_user_id: str
    refund_amount: Optional[float] = None
    refund_entry_ids: Optional[List[int]] = None
    denial_reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime


class CreditAwardLogEntry(BaseModel):
    """Credit award log entry for admin view"""
    id: int
    action_type: str
    admin_email: str
    target_user_email: str
    target_user_id: str
    credit_amount: Optional[float] = None
    award_reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime


@router.get("/admin-action-logs/refunds", response_model=List[RefundLogEntry])
async def get_refund_logs(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
    limit: int = 100,
    offset: int = 0,
) -> List[RefundLogEntry]:
    """
    Get log of all approved or denied refund requests (Admin only).
    
    Returns a list of refund actions with amounts and details.
    """
    if not ADMIN_LOG_AVAILABLE:
        return []
    
    try:
        # Get refund logs (both approved and denied)
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
        
        # Get user emails for admin and target users
        user_ids = set()
        for log_entry in logs:
            user_ids.add(log_entry.admin_user_id)
            user_ids.add(log_entry.target_user_id)
        
        users = {}
        if user_ids:
            user_stmt = select(User).where(User.id.in_(list(user_ids)))
            user_results = session.exec(user_stmt).all()
            users = {user.id: user for user in user_results}
        
        # Build response
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


@router.get("/admin-action-logs/credits", response_model=List[CreditAwardLogEntry])
async def get_credit_award_logs(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
    limit: int = 100,
    offset: int = 0,
) -> List[CreditAwardLogEntry]:
    """
    Get log of all credit awards given away (Admin only).
    
    Returns a list of credit award actions with amounts and reasons.
    """
    if not ADMIN_LOG_AVAILABLE:
        return []
    
    try:
        # Get credit award logs
        stmt = (
            select(AdminActionLog)
            .where(AdminActionLog.action_type == AdminActionType.CREDIT_AWARDED)
            .order_by(AdminActionLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        
        logs = session.exec(stmt).all()
        
        # Get user emails for admin and target users
        user_ids = set()
        for log_entry in logs:
            user_ids.add(log_entry.admin_user_id)
            user_ids.add(log_entry.target_user_id)
        
        users = {}
        if user_ids:
            user_stmt = select(User).where(User.id.in_(list(user_ids)))
            user_results = session.exec(user_stmt).all()
            users = {user.id: user for user in user_results}
        
        # Build response
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


__all__ = ["router"]
