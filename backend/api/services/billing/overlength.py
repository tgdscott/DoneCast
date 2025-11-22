"""
Overlength episode surcharge logic.

Handles episodes that exceed plan max_minutes limits.
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple
from uuid import UUID

from sqlmodel import Session

from api.billing.plans import (
    get_plan_max_minutes,
    allows_overlength,
    requires_overlength_surcharge,
    RATES,
)
from api.models.user import User

log = logging.getLogger(__name__)


def check_overlength(
    session: Session,
    user: User,
    episode_duration_minutes: float
) -> Tuple[bool, Optional[str], Optional[float]]:
    """
    Check if episode exceeds plan max_minutes and determine action.
    
    Args:
        session: Database session
        user: User object
        episode_duration_minutes: Episode duration in minutes
    
    Returns:
        (is_allowed, error_message, surcharge_credits)
        - is_allowed: True if episode can proceed
        - error_message: Error message if blocked (None if allowed)
        - surcharge_credits: Additional credits to charge for overlength (None if no surcharge)
    """
    plan_key = getattr(user, 'tier', 'free') or 'free'
    max_minutes = get_plan_max_minutes(plan_key)
    
    # If no max_minutes limit, always allowed
    if max_minutes is None:
        return (True, None, None)
    
    # If episode is within limit, no issue
    if episode_duration_minutes <= max_minutes:
        return (True, None, None)
    
    # Episode exceeds limit - check plan rules
    if not allows_overlength(plan_key):
        # Hobby: hard block
        error_msg = (
            f"Episode length ({episode_duration_minutes:.1f} min) exceeds your plan limit "
            f"({max_minutes} min). Please upgrade to Creator or higher to process longer episodes."
        )
        return (False, error_msg, None)
    
    # Creator/Pro: allow with surcharge
    if requires_overlength_surcharge(plan_key):
        # Calculate surcharge for portion beyond limit
        overlength_minutes = episode_duration_minutes - max_minutes
        overlength_seconds = overlength_minutes * 60.0
        surcharge_rate = RATES["overlength_surcharge_per_sec"]
        surcharge_credits = overlength_seconds * surcharge_rate
        
        log.info(
            f"[overlength] Episode exceeds limit: user={user.id}, "
            f"duration={episode_duration_minutes:.1f}min, max={max_minutes}min, "
            f"surcharge={surcharge_credits:.1f} credits"
        )
        
        return (True, None, surcharge_credits)
    
    # Executive/Enterprise/Unlimited: allowed, no surcharge
    return (True, None, None)


def apply_overlength_surcharge(
    session: Session,
    user: User,
    episode_id: UUID,
    episode_duration_minutes: float,
    correlation_id: Optional[str] = None
) -> Optional[float]:
    """
    Apply overlength surcharge if episode exceeds plan limit.
    
    Args:
        session: Database session
        user: User object
        episode_id: Episode ID
        episode_duration_minutes: Episode duration in minutes
        correlation_id: Optional idempotency key
    
    Returns:
        Surcharge credits applied (None if no surcharge)
    """
    is_allowed, error_msg, surcharge_credits = check_overlength(
        session, user, episode_duration_minutes
    )
    
    if not is_allowed:
        # Should not happen if called after check_overlength
        log.error(f"[overlength] Episode blocked but surcharge called: {error_msg}")
        return None
    
    if surcharge_credits is None or surcharge_credits <= 0:
        return None
    
    # Charge surcharge
    from api.services.billing.credits import charge_credits
    from api.models.usage import LedgerReason
    
    charge_credits(
        session=session,
        user_id=user.id,
        credits=surcharge_credits,
        reason=LedgerReason.PROCESS_AUDIO,  # Use same reason as processing
        episode_id=episode_id,
        notes=f"Overlength surcharge ({episode_duration_minutes:.1f} min exceeds plan limit)",
        cost_breakdown={
            'episode_duration_minutes': episode_duration_minutes,
            'overlength_minutes': episode_duration_minutes - get_plan_max_minutes(getattr(user, 'tier', 'free') or 'free'),
            'surcharge_rate_per_sec': RATES["overlength_surcharge_per_sec"],
            'surcharge_credits': surcharge_credits
        },
        correlation_id=correlation_id
    )
    
    return surcharge_credits


__all__ = [
    "check_overlength",
    "apply_overlength_surcharge",
]

