"""
Admin Deletion Management Endpoints

Manage pending user account deletions requested by users.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlmodel import Session, select
from datetime import datetime
from typing import Dict, Any, List
from uuid import UUID
import logging

from ...core.database import get_session
from ...models.user import User
from ...models.podcast import Episode, EpisodeStatus
from .deps import get_current_admin_user, get_current_superadmin_user

# Import the existing delete_user function from admin/users.py
# We'll call it for expedited deletions
from .users import delete_user as _admin_delete_user

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin-deletions"])


@router.get(
    "/pending-deletions",
    status_code=status.HTTP_200_OK,
    summary="List all pending account deletions",
)
def get_pending_deletions(
    session: Session = Depends(get_session),
    admin: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    List all user accounts pending deletion with grace period details.
    
    Shows:
    - User email and tier
    - Deletion requested date/time
    - Scheduled deletion date/time
    - Days remaining
    - Who requested (user vs admin)
    - Published episode count
    - Account age
    
    **Admin Only**
    """
    log.info(f"[ADMIN-DELETION] Pending deletions list requested by {admin.email}")
    
    # Find all users with pending deletion
    pending_users = session.exec(
        select(User)
        .where(User.is_deleted_view == True)
        .where(User.deletion_scheduled_for != None)
    ).all()
    
    now = datetime.utcnow()
    pending_deletions = []
    
    for user in pending_users:
        # Calculate days remaining
        if user.deletion_scheduled_for:
            time_remaining = user.deletion_scheduled_for - now
            days_remaining = max(0, time_remaining.days)
        else:
            days_remaining = 0
        
        # Count published episodes
        published_count = session.exec(
            select(Episode)
            .where(Episode.user_id == user.id)
            .where(Episode.status == EpisodeStatus.published)
        ).all()
        
        # Calculate account age
        account_age_days = (now - user.created_at).days if user.created_at else 0
        
        pending_deletions.append({
            "user_id": str(user.id),
            "email": user.email,
            "tier": user.tier or "free",
            "deletion_requested_at": user.deletion_requested_at.isoformat() if user.deletion_requested_at else None,
            "deletion_scheduled_for": user.deletion_scheduled_for.isoformat() if user.deletion_scheduled_for else None,
            "days_remaining": days_remaining,
            "requested_by": user.deletion_requested_by or "unknown",
            "deletion_reason": user.deletion_reason,
            "published_episodes": len(published_count),
            "account_age_days": account_age_days,
            "is_active": user.is_active,
        })
    
    log.info(f"[ADMIN-DELETION] Found {len(pending_deletions)} pending deletions")
    
    return {
        "pending_deletions": pending_deletions,
        "total_count": len(pending_deletions)
    }


@router.post(
    "/users/{user_id}/cancel-deletion",
    status_code=status.HTTP_200_OK,
    summary="Cancel pending account deletion and restore access",
)
def cancel_user_deletion(
    user_id: str,
    session: Session = Depends(get_session),
    admin: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    Cancel a pending account deletion and restore user access.
    
    This will:
    - Clear all deletion metadata
    - Restore is_active to True
    - Clear is_deleted_view flag
    - User can immediately log in again
    
    **Admin Only**
    
    **Use Cases:**
    - User contacted support to restore account
    - Suspected bad actor prevented
    - Accidental deletion request
    """
    log.warning(f"[ADMIN-DELETION] Deletion cancellation requested by {admin.email} for user_id: {user_id}")
    
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
    
    # Check if deletion was actually pending
    if not user.is_deleted_view:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User {user.email} has no pending deletion"
        )
    
    # Capture email for logging
    user_email = user.email
    
    # Clear deletion metadata
    user.deletion_requested_at = None
    user.deletion_scheduled_for = None
    user.deletion_requested_by = None
    user.deletion_reason = None
    user.is_deleted_view = False
    user.is_active = True  # Restore active status
    
    session.add(user)
    session.commit()
    session.refresh(user)
    
    log.warning(
        f"[ADMIN-DELETION] Account deletion cancelled by {admin.email} "
        f"for user {user_email} ({user_id}) - Account restored"
    )
    
    return {
        "message": "Account deletion cancelled successfully",
        "user_email": user_email,
        "user_id": user_id,
        "account_restored": True,
        "cancelled_by": admin.email
    }


@router.post(
    "/users/{user_id}/expedite-deletion",
    status_code=status.HTTP_200_OK,
    summary="Expedite account deletion (bypass grace period) - Superadmin only",
)
def expedite_user_deletion(
    user_id: str,
    confirm_email: str = Body(..., embed=True),
    session: Session = Depends(get_session),
    admin: User = Depends(get_current_superadmin_user),  # Superadmin only for immediate deletion
) -> Dict[str, Any]:
    """
    Immediately delete a user account, bypassing the grace period.
    
    **SUPERADMIN ONLY** - This permanently deletes the account immediately.
    
    **Use Cases:**
    - User explicitly requests immediate deletion
    - Security incident requires immediate removal
    - Legal/compliance requirement
    
    **Safety:**
    - Requires email confirmation
    - Uses same deletion logic as admin delete_user endpoint
    - All safety checks apply (cannot delete admins, etc.)
    
    **Request Body:**
    ```json
    {
        "confirm_email": "user@example.com"
    }
    ```
    """
    log.warning(f"[ADMIN-DELETION] Expedited deletion requested by {admin.email} for user_id: {user_id}")
    
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
    
    # Safety check: Confirm email matches
    if user.email != confirm_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email confirmation failed. Expected '{user.email}' but got '{confirm_email}'"
        )
    
    log.warning(
        f"[ADMIN-DELETION] Expediting deletion for {user.email} ({user_id}) "
        f"- Bypassing grace period, immediate deletion by {admin.email}"
    )
    
    # Clear the is_deleted_view flag and set is_active=False so the 
    # existing delete_user function's safety checks will pass
    user.is_deleted_view = False
    user.is_active = False
    session.add(user)
    session.commit()
    
    # Call the existing admin delete_user function
    # It handles all the cascade deletions, GCS cleanup, etc.
    try:
        result = _admin_delete_user(
            user_id=user_id,
            confirm_email=confirm_email,
            session=session,
            admin=admin
        )
        
        log.warning(f"[ADMIN-DELETION] Expedited deletion completed for {confirm_email}")
        
        return {
            **result,
            "expedited": True,
            "expedited_by": admin.email,
            "message": "Account deleted immediately (grace period bypassed)"
        }
    
    except HTTPException as e:
        # Re-raise HTTP exceptions from delete_user
        raise
    except Exception as e:
        log.error(f"[ADMIN-DELETION] Expedited deletion failed for {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete user: {str(e)}"
        )
