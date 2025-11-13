# Centralized plan / entitlement constants

TIER_LIMITS = {
    # New minutes-based processing quotas; retain legacy episode counts for transition period
    # processing_minutes = total minutes of source audio processed (not final length) counting drafts & published.
    # Note: "free" is kept for backward compatibility, but "starter" is the new name
    "free": {"max_processing_minutes_month": 60, "max_episodes_month": 5},
    "starter": {"max_processing_minutes_month": 60, "max_episodes_month": 5},  # Alias for "free"
    "creator": {"max_processing_minutes_month": 300, "max_episodes_month": 50},
    "pro": {"max_processing_minutes_month": 1000, "max_episodes_month": 500},
    # Admin-only tier: must be manually assigned; imposes no limits
    "unlimited": {"max_processing_minutes_month": None, "max_episodes_month": None},
}

# Plans that can be purchased/managed via Stripe. Excludes admin-only tiers like 'unlimited'.
ALLOWED_PLANS = {k for k in TIER_LIMITS.keys() if k != 'unlimited'}
