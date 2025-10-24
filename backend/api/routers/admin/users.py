from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Body, status
from sqlalchemy import func
from pydantic import BaseModel
from sqlmodel import Session, select

from api.core import crud
from api.core.database import get_session
from api.models.podcast import Episode, Podcast, MediaItem, PodcastTemplate, EpisodeSection
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

from .deps import commit_with_retry, get_current_admin_user, get_current_superadmin_user

router = APIRouter()
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
                email_verified=user.id in verified_user_ids,  # NEW: Check if user email is verified
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
        code="ADMIN-VERIFIED",
        jwt_token=None,
        expires_at=now,  # Already expired since it's pre-verified
        verified_at=now,  # Mark as verified immediately
        used=True,  # Mark as used
        created_at=now,
    )
    
    session.add(verification)
    commit_with_retry(session)
    session.refresh(verification)
    
    log.info(f"[ADMIN] Created manual email verification for user {user.email} by admin {admin_user.email}")
    
    return {
        "success": True,
        "user_id": str(user.id),
        "email": user.email,
        "already_verified": False,
        "verified_at": verification.verified_at.isoformat() if verification.verified_at else None,
        "verified_by_admin": admin_user.email,
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
    # Allow deletion of free tier and admin tier (but not superadmin, protected, or paid tiers)
    if user_tier not in ["free", "", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot delete paid user. User must be on 'free' or 'admin' tier. (Current tier: {user.tier})"
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
        media_items = session.exec(select(MediaItem).where(MediaItem.user_id == user.id)).all()
        for item in media_items:
            session.delete(item)
        log.info(f"[ADMIN] Deleted {media_count} media items for user {user.id}")
        
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
        
        # 6. Podcasts
        podcasts = session.exec(select(Podcast).where(Podcast.user_id == user.id)).all()
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
        
        # 12. Podcast websites
        if WEBSITE_AVAILABLE:
            websites = session.exec(select(PodcastWebsite).where(PodcastWebsite.user_id == user.id)).all()
            website_count = len(websites)
            for website in websites:
                session.delete(website)
            log.info(f"[ADMIN] Deleted {website_count} website records for user {user.id}")
        
        # 13. User account (finally!)
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


__all__ = ["router"]
