"""
Plan definitions and billing constants.

Single source of truth for plan tiers, credit rates, and billing rules.
"""
import os
from typing import Optional, Dict, Any

# Plan definitions
PLANS: Dict[str, Dict[str, Any]] = {
    "starter": {
        "price": 19,
        "monthly_credits": 28_800,  # 480 hours = 28,800 minutes
        "max_minutes": 40,
        "analytics": "basic",
        "priority": 1,
    },
    "creator": {
        "price": 39,
        "monthly_credits": 72_000,  # 1,200 hours = 72,000 minutes
        "max_minutes": 80,
        "analytics": "advanced",
        "priority": 2,
    },
    "pro": {
        "price": 79,
        "monthly_credits": 172_800,  # 2,880 hours = 172,800 minutes
        "max_minutes": 120,
        "analytics": "full",
        "priority": 3,
    },
    "executive": {
        "price": 129,
        "monthly_credits": 288_000,  # 4,800 hours = 288,000 minutes
        "max_minutes": 240,
        "analytics": "full",
        "priority": 4,
        "allow_manual_override": True,  # Can manually override max_minutes
    },
    "enterprise": {
        "contact_only": True,
        "analytics": "full",
        "priority": 5,
        # No public limits - use contract flags
    },
    "unlimited": {
        "internal": True,
        "monthly_credits": None,  # Unlimited
        "analytics": "full",
        "priority": 6,
    },
}

# Credit rollover rate (10%)
ROLLOVER_RATE = 0.10

# Per-activity credit rates (per second)
RATES: Dict[str, int] = {
    "processing_per_sec": 1,
    "assembly_per_sec": 3,
    "auphonic_per_sec": int(os.getenv("AUPHONIC_CREDITS_PER_SEC", "1")),
    "overlength_surcharge_per_sec": 1,
}

# ElevenLabs TTS rates per plan (credits per second)
RATES_ELEVENLABS: Dict[str, int] = {
    "starter": 15,
    "creator": 14,
    "pro": 13,
    "executive": 12,
    "enterprise": 12,  # Same as executive
    "unlimited": 12,  # Same as executive
}

# Analytics levels
ANALYTICS_LEVELS = {
    "basic": 1,
    "advanced": 2,
    "full": 3,
}


def get_plan(plan_key: str) -> Optional[Dict[str, Any]]:
    """Get plan configuration by key."""
    return PLANS.get(plan_key.lower())


def get_plan_priority(plan_key: str) -> int:
    """Get queue priority for a plan (higher = more priority)."""
    plan = get_plan(plan_key)
    if not plan:
        return 0
    return plan.get("priority", 0)


def get_plan_max_minutes(plan_key: str) -> Optional[int]:
    """Get maximum episode length in minutes for a plan."""
    plan = get_plan(plan_key)
    if not plan:
        return None
    return plan.get("max_minutes")


def get_analytics_level(plan_key: str) -> str:
    """Get analytics access level for a plan."""
    plan = get_plan(plan_key)
    if not plan:
        return "basic"
    return plan.get("analytics", "basic")


def can_access_analytics(plan_key: str, required_level: str) -> bool:
    """Check if plan can access analytics at required level."""
    plan_level = get_analytics_level(plan_key)
    plan_level_num = ANALYTICS_LEVELS.get(plan_level, 0)
    required_level_num = ANALYTICS_LEVELS.get(required_level, 0)
    return plan_level_num >= required_level_num


def is_unlimited_plan(plan_key: str) -> bool:
    """Check if plan is unlimited (internal/admin)."""
    plan = get_plan(plan_key)
    if not plan:
        return False
    return plan.get("internal", False)


def is_enterprise_plan(plan_key: str) -> bool:
    """Check if plan is enterprise (contact-only)."""
    plan = get_plan(plan_key)
    if not plan:
        return False
    return plan.get("contact_only", False)


def get_elevenlabs_rate(plan_key: str) -> int:
    """Get ElevenLabs TTS rate (credits per second) for a plan."""
    return RATES_ELEVENLABS.get(plan_key.lower(), 15)  # Default to starter rate


def allows_overlength(plan_key: str) -> bool:
    """Check if plan allows episodes exceeding max_minutes (with surcharge or override)."""
    plan = get_plan(plan_key)
    if not plan:
        return False
    
    # Executive, Enterprise, Unlimited allow overlength
    if plan_key.lower() in ("executive", "enterprise", "unlimited"):
        return True
    
    # Creator and Pro allow with surcharge
    if plan_key.lower() in ("creator", "pro"):
        return True
    
    # Starter blocks at hard cap
    return False


def requires_overlength_surcharge(plan_key: str) -> bool:
    """Check if plan requires surcharge for overlength episodes."""
    plan = get_plan(plan_key)
    if not plan:
        return False
    
    # Creator and Pro require surcharge
    return plan_key.lower() in ("creator", "pro")


__all__ = [
    "PLANS",
    "ROLLOVER_RATE",
    "RATES",
    "RATES_ELEVENLABS",
    "ANALYTICS_LEVELS",
    "get_plan",
    "get_plan_priority",
    "get_plan_max_minutes",
    "get_analytics_level",
    "can_access_analytics",
    "is_unlimited_plan",
    "is_enterprise_plan",
    "get_elevenlabs_rate",
    "allows_overlength",
    "requires_overlength_surcharge",
]

