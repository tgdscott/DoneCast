"""
User Self-Deletion Endpoints

Allows users to request deletion of their own account with a grace period.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlmodel import Session, select, func
from datetime import datetime, timedelta
from typing import Dict, Any
from uuid import UUID
import logging

from ...core.database import get_session
from ...core.auth import get_current_user
from ...models.user import User
from ...models.podcast import Episode, EpisodeStatus

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users/me", tags=["user-deletion"])


def calculate_grace_period_days(published_episode_count: int) -> int:
    """
    Calculate grace period based on episode history.
    
    Base: 2 days
    Bonus: +7 days per published episode
    Max: 30 days
    
    Args:
        published_episode_count: Number of successfully published episodes
        
    Returns:
        Grace period in days (2-30)
    """
    base_days = 2
    bonus_days = published_episode_count * 7
    total_days = base_days + bonus_days
    return min(total_days, 30)


@router.post(
    "/request-deletion",
    status_code=status.HTTP_200_OK,
    summary="Request account deletion (self-service)",
)
def request_account_deletion(
    confirm_email: str = Body(..., embed=True),
    reason: str = Body(None, embed=True),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Request deletion of your own account with automatic grace period.
    
    **Grace Period Calculation**:
    - Base: 2 days
    - Bonus: +7 days per published episode
    - Maximum: 30 days
    
    During the grace period:
    - Your account appears deleted (cannot log in)
    - Data is retained in case of restoration
    - Admins can cancel the deletion
    - You can contact support to restore access
    
    After the grace period expires:
    - Account is permanently deleted
    - All data is removed
    - This action cannot be undone
    
    **Safety Features**:
    - Email confirmation required
    - Admin/superadmin accounts cannot self-delete
    - Paid tier accounts may require admin approval
    
    **Request Body**:
    ```json
    {
        "confirm_email": "your@email.com",
        "reason": "Optional reason for leaving"
    }
    ```
    
    **Response**:
    ```json
    {
        "message": "Account deletion scheduled",
        "deletion_scheduled_for": "2025-11-04T15:30:00Z",
        "grace_period_days": 9,
        "published_episodes": 1
    }
    ```
    """
    log.warning(f"[USER-DELETION] Self-deletion requested by user: {current_user.email} ({current_user.id})")
    
    # Safety check: Confirm email matches
    if current_user.email != confirm_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email confirmation failed. Expected '{current_user.email}' but got '{confirm_email}'"
        )
    
    # Protection: Admin/superadmin accounts cannot self-delete
    if current_user.role in ["admin", "superadmin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin and superadmin accounts cannot be self-deleted. Please contact support."
        )
    
    # Protection: Legacy is_admin flag check
    if current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin accounts cannot be self-deleted. Please contact support."
        )
    
    # Protection: Already pending deletion
    if current_user.is_deleted_view:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account deletion already in progress"
        )
    
    # Count published episodes for grace period calculation
    from api.routers.episodes.common import is_published_condition
    published_count = session.exec(
        select(func.count())
        .select_from(Episode)
        .where(Episode.user_id == current_user.id)
        .where(is_published_condition())
    ).one()
    
    # Calculate grace period
    grace_period_days = calculate_grace_period_days(published_count)
    
    # Calculate scheduled deletion date
    now = datetime.utcnow()
    deletion_scheduled = now + timedelta(days=grace_period_days)
    
    # Update user record with deletion metadata
    current_user.deletion_requested_at = now
    current_user.deletion_scheduled_for = deletion_scheduled
    current_user.deletion_requested_by = "user"
    current_user.deletion_reason = reason
    current_user.is_deleted_view = True
    current_user.is_active = False  # Also mark as inactive
    
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    
    log.warning(
        f"[USER-DELETION] Account deletion scheduled for {current_user.email} "
        f"({current_user.id}) - Grace period: {grace_period_days} days, "
        f"Published episodes: {published_count}, "
        f"Deletion date: {deletion_scheduled.isoformat()}"
    )
    
    # TODO: Send admin notification (only when user-initiated)
    # This will be implemented in the admin notification task
    
    return {
        "message": "Account deletion scheduled",
        "deletion_scheduled_for": deletion_scheduled.isoformat(),
        "grace_period_days": grace_period_days,
        "published_episodes": published_count,
        "can_restore_until": deletion_scheduled.isoformat(),
        "contact_support": "To restore your account during the grace period, please contact support@podcastplusplus.com"
    }


@router.post(
    "/cancel-deletion",
    status_code=status.HTTP_200_OK,
    summary="Cancel pending account deletion (restore access)",
)
def cancel_account_deletion(
    confirm_email: str = Body(..., embed=True),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Cancel a pending account deletion and restore access.
    
    **Only works during grace period** before actual deletion occurs.
    
    **Request Body**:
    ```json
    {
        "confirm_email": "your@email.com"
    }
    ```
    """
    log.info(f"[USER-DELETION] Deletion cancellation requested by user: {current_user.email} ({current_user.id})")
    
    # Safety check: Confirm email matches
    if current_user.email != confirm_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email confirmation failed. Expected '{current_user.email}' but got '{confirm_email}'"
        )
    
    # Check if deletion was actually pending
    if not current_user.is_deleted_view:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending deletion found for this account"
        )
    
    # Clear deletion metadata
    current_user.deletion_requested_at = None
    current_user.deletion_scheduled_for = None
    current_user.deletion_requested_by = None
    current_user.deletion_reason = None
    current_user.is_deleted_view = False
    current_user.is_active = True  # Restore active status
    
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    
    log.warning(
        f"[USER-DELETION] Account deletion cancelled for {current_user.email} "
        f"({current_user.id}) - Account restored"
    )
    
    return {
        "message": "Account deletion cancelled successfully",
        "account_restored": True,
        "email": current_user.email
    }
