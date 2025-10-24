"""Auphonic integration helper functions for tiered audio processing.

PRODUCTION TIER ROUTING (DO NOT CHANGE WITHOUT USER APPROVAL):
- Pro → Auphonic pipeline (professional audio processing)
- Free/Creator/Unlimited → AssemblyAI pipeline (custom processing)

CRITICAL: Only Pro tier uses Auphonic. Do not assume or hallucinate other tier mappings.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from api.models.user import User
    from api.models.podcast import Episode

log = logging.getLogger(__name__)


def should_use_auphonic(user: "User", episode: Optional["Episode"] = None) -> bool:
    """Determine if user/episode should use Auphonic professional audio processing.
    
    PRODUCTION TIER ROUTING (FINAL - DO NOT CHANGE WITHOUT USER APPROVAL):
    - Pro ($79/mo): YES - Auphonic pipeline
    - Free (30 min): NO - AssemblyAI pipeline
    - Creator ($39/mo): NO - AssemblyAI pipeline
    - Unlimited/Enterprise: NO - AssemblyAI pipeline
    
    CRITICAL: Only Pro tier uses Auphonic. All other tiers use AssemblyAI + custom processing.
    
    Args:
        user: User model instance
        episode: Optional episode model (for per-episode overrides in future)
        
    Returns:
        True if should use Auphonic, False for AssemblyAI pipeline
    """
    # Get user's subscription plan from 'tier' field (not 'subscription_plan')
    tier = getattr(user, "tier", None)
    
    if not tier:
        log.debug("[auphonic_routing] user_id=%s no_tier using_current_stack", user.id)
        return False
    
    # Normalize plan name (handle case variations)
    tier_lower = tier.lower().strip()
    
    # PRODUCTION ROUTING: Only Pro tier uses Auphonic
    # All other tiers (Free, Creator, Unlimited, Enterprise) use AssemblyAI pipeline
    if tier_lower == "pro":
        log.info(
            "[auphonic_routing] 🎯 user_id=%s tier=%s → Auphonic pipeline",
            user.id,
            tier,
        )
        return True
    
    # All other tiers → AssemblyAI pipeline
    log.debug(
        "[auphonic_routing] user_id=%s tier=%s → AssemblyAI pipeline",
        user.id,
        tier,
    )
    return False


def get_audio_processing_tier_name(user: "User") -> str:
    """Get human-friendly audio processing tier name for user.
    
    Args:
        user: User model instance
        
    Returns:
        "Professional Audio Processing" or "Standard Audio Processing"
    """
    if should_use_auphonic(user):
        return "Professional Audio Processing"
    return "Standard Audio Processing"


__all__ = [
    "should_use_auphonic",
    "get_audio_processing_tier_name",
]
