# Centralized plan / entitlement constants

TIER_LIMITS = {
    # New minutes-based processing quotas; retain legacy episode counts for transition period
    # processing_minutes = total minutes of source audio processed (not final length) counting drafts & published.
    
    # Legacy / Aliases
    "free": {"max_processing_minutes_month": 60, "max_episodes_month": 5},
    "starter": {"max_processing_minutes_month": 60, "max_episodes_month": 5},

    # Current Paid Tiers
    "hobby": {"max_processing_minutes_month": 60, "max_episodes_month": 5},
    "creator": {"max_processing_minutes_month": 300, "max_episodes_month": 50},
    "pro": {"max_processing_minutes_month": 1000, "max_episodes_month": 500},
    "executive": {"max_processing_minutes_month": 2000, "max_episodes_month": 1000},
    
    # Negotiated / Admin-only
    "enterprise": {"max_processing_minutes_month": None, "max_episodes_month": None},
    "unlimited": {"max_processing_minutes_month": None, "max_episodes_month": None},
}

# Plans that can be purchased/managed via Stripe. Excludes admin-only tiers like 'unlimited'.
ALLOWED_PLANS = {k for k in TIER_LIMITS.keys() if k != 'unlimited'}
