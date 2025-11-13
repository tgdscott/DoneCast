"""
Storage limit validation for tier-based raw audio storage.

Enforces tier-based storage limits:
- Maximum hours of raw audio storage
- Retention period (days)
"""
from __future__ import annotations

import logging
from typing import Optional
from sqlmodel import Session, select
from api.models.podcast import MediaItem, MediaCategory
from api.billing.plans import get_storage_hours, has_unlimited_storage
from api.services.episodes.assembler import _estimate_audio_seconds

log = logging.getLogger("storage.validation")


def get_user_storage_hours(session: Session, user_id: str, tier: str) -> float:
    """Calculate total hours of raw audio storage for a user.
    
    Args:
        session: Database session
        user_id: User ID (UUID string)
        tier: User's tier
        
    Returns:
        Total hours of raw audio storage (sum of all main_content files)
    """
    if has_unlimited_storage(tier):
        return 0.0  # Unlimited storage, no need to calculate
    
    try:
        from uuid import UUID
        # Convert user_id to UUID if it's a string
        user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
        
        # Get all main_content items for this user
        query = (
            select(MediaItem)
            .where(MediaItem.user_id == user_uuid)  # type: ignore
            .where(MediaItem.category == MediaCategory.main_content)  # type: ignore
        )
        items = session.exec(query).all()
        
        total_seconds = 0.0
        for item in items:
            filename = getattr(item, "filename", None)
            if not filename:
                continue
            
            # Estimate audio length
            seconds = _estimate_audio_seconds(filename)
            if seconds and seconds > 0:
                total_seconds += seconds
        
        return total_seconds / 3600.0  # Convert to hours
    except Exception as e:
        log.warning("[storage] Failed to calculate storage hours for user %s: %s", user_id, e, exc_info=True)
        return 0.0


def check_storage_limits(
    session: Session,
    user_id: str,
    tier: str,
    new_file_duration_seconds: Optional[float] = None,
    new_file_hours: Optional[float] = None
) -> tuple[bool, Optional[str]]:
    """Check if user can upload a new file without exceeding storage limits.
    
    Args:
        session: Database session
        user_id: User ID
        tier: User's tier
        new_file_duration_seconds: Duration of new file in seconds (optional)
        new_file_hours: Duration of new file in hours (optional, overrides seconds if provided)
        
    Returns:
        Tuple of (allowed: bool, error_message: Optional[str])
    """
    if has_unlimited_storage(tier):
        return True, None
    
    max_hours = get_storage_hours(tier)
    if max_hours is None:
        return True, None  # No limit
    
    # Calculate new file hours
    if new_file_hours is not None:
        new_hours = new_file_hours
    elif new_file_duration_seconds is not None:
        new_hours = new_file_duration_seconds / 3600.0
    else:
        # Can't validate without file duration - allow but log warning
        log.warning("[storage] Cannot validate storage limit without file duration for user %s", user_id)
        return True, None
    
    # Get current storage usage
    current_hours = get_user_storage_hours(session, user_id, tier)
    total_hours = current_hours + new_hours
    
    if total_hours > max_hours:
        error_msg = (
            f"Storage limit exceeded. Your {tier} plan allows {max_hours} hours of raw audio storage. "
            f"You currently have {current_hours:.2f} hours stored. "
            f"This upload would add {new_hours:.2f} hours, bringing total to {total_hours:.2f} hours. "
            f"Please delete some files or upgrade your plan."
        )
        return False, error_msg
    
    return True, None

