"""
Trial service for managing free trial periods.

Handles trial status checks, effective tier calculation, and trial restrictions.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlmodel import Session

from api.models.user import User
from api.models.settings import load_admin_settings


def is_on_trial(user: User) -> bool:
    """Check if user is currently on a free trial."""
    if not user.trial_started_at or not user.trial_expires_at:
        return False
    
    now = datetime.now(timezone.utc)
    
    # Ensure datetimes are timezone-aware for comparison
    trial_start = user.trial_started_at
    if trial_start.tzinfo is None:
        trial_start = trial_start.replace(tzinfo=timezone.utc)
    
    trial_end = user.trial_expires_at
    if trial_end.tzinfo is None:
        trial_end = trial_end.replace(tzinfo=timezone.utc)
    
    return trial_start <= now <= trial_end


def is_trial_expired(user: User) -> bool:
    """Check if user's trial has expired."""
    if not user.trial_expires_at:
        return False
    
    now = datetime.now(timezone.utc)
    
    # Ensure datetime is timezone-aware for comparison
    trial_end = user.trial_expires_at
    if trial_end.tzinfo is None:
        trial_end = trial_end.replace(tzinfo=timezone.utc)
    
    return now > trial_end


def get_effective_tier(user: User) -> str:
    """
    Get the effective tier for a user.
    
    During trial: returns "hobby" (trial users get Hobby package benefits)
    After trial: returns user's actual tier
    If trial expired and no subscription: returns "free"
    """
    if is_on_trial(user):
        return "hobby"
    
    # If trial expired and user has no active subscription, they're effectively "free"
    if is_trial_expired(user) and not has_active_subscription(user):
        return "free"
    
    return user.tier


def has_active_subscription(user: User) -> bool:
    """Check if user has an active paid subscription."""
    # Check if user has a subscription that hasn't expired
    if user.subscription_expires_at:
        now = datetime.now(timezone.utc)
        
        # Ensure datetime is timezone-aware for comparison
        sub_expires = user.subscription_expires_at
        if sub_expires.tzinfo is None:
            sub_expires = sub_expires.replace(tzinfo=timezone.utc)
        
        return now < sub_expires
    
    # Check if user has a paid tier (not free)
    paid_tiers = {"hobby", "creator", "pro", "executive", "enterprise"}
    return user.tier in paid_tiers


def start_trial(user: User, session: Session, trial_days: Optional[int] = None) -> None:
    """
    Start a free trial for a user.
    
    Args:
        user: User to start trial for
        session: Database session
        trial_days: Number of days for trial (defaults to admin setting)
    """
    if user.trial_started_at:
        # Trial already started, don't restart
        return
    
    if trial_days is None:
        admin_settings = load_admin_settings(session)
        trial_days = admin_settings.free_trial_days
    
    now = datetime.now(timezone.utc)
    user.trial_started_at = now
    user.trial_expires_at = now + timedelta(days=trial_days)
    session.add(user)
    session.commit()


def can_create_content(user: User) -> bool:
    """
    Check if user can create new content (podcasts/episodes).
    
    All accounts start as "trial" tier. The actual trial period (trial_started_at/trial_expires_at)
    begins when the user creates their first podcast.
    
    Returns True if:
    - User has "trial" tier (all new accounts)
    - User is on trial (trial period has started and not expired)
    - User hasn't started trial yet (onboarding - trial starts when first podcast is created)
    - User has active subscription
    - User has unlimited tier
    
    Returns False if:
    - Trial expired and no active subscription
    """
    # All accounts start as "trial" tier - allow creation
    if user.tier == "trial":
        return True
    
    # Allow creation during onboarding (trial hasn't started yet)
    if not user.trial_started_at:
        return True
    
    if is_on_trial(user):
        return True
    
    if is_trial_expired(user):
        return has_active_subscription(user)
    
    # Not on trial, check subscription
    return has_active_subscription(user) or user.tier in {"unlimited"}


def can_access_rss_feed(user: User) -> bool:
    """
    Check if user's RSS feed should be accessible.
    
    Returns False if trial expired and no subscription.
    """
    if is_on_trial(user):
        return True
    
    if is_trial_expired(user):
        return has_active_subscription(user)
    
    # Not on trial, check subscription
    return has_active_subscription(user) or user.tier in {"unlimited", "free"}


def can_download_episodes(user: User) -> bool:
    """
    Check if user can download episodes.
    
    During trial: returns False (trial users cannot download)
    After trial: returns True if they have active subscription
    """
    if is_on_trial(user):
        return False
    
    if is_trial_expired(user):
        return has_active_subscription(user)
    
    # Not on trial, check subscription
    return has_active_subscription(user) or user.tier in {"unlimited"}


def can_modify_rss_settings(user: User) -> bool:
    """
    Check if user can modify RSS feed redirect/transfer settings.
    
    During trial: returns False (trial users cannot transfer RSS feeds)
    After trial: returns True if they have active subscription
    """
    if is_on_trial(user):
        return False
    
    if is_trial_expired(user):
        return has_active_subscription(user)
    
    # Not on trial, check subscription
    return has_active_subscription(user) or user.tier in {"unlimited"}

