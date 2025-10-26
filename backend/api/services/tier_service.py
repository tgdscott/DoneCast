"""
Tier service for database-driven feature gating and credit calculations.

This service replaces hard-coded tier logic throughout the codebase,
providing a centralized, database-driven system for tier management.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional, TYPE_CHECKING
from functools import lru_cache
from datetime import datetime, timedelta

from sqlmodel import Session, select, desc

from api.models.tier_config import TierConfiguration, TierConfigurationHistory, TIER_FEATURE_DEFINITIONS
from api.core.constants import TIER_LIMITS  # Fallback for migration period

if TYPE_CHECKING:
    from api.models.user import User

log = logging.getLogger(__name__)

# In-memory cache for tier configurations (invalidated on updates)
_tier_config_cache: dict[str, dict[str, Any]] = {}
_cache_timestamp: Optional[datetime] = None
_CACHE_TTL_SECONDS = 300  # 5 minutes


def _invalidate_cache():
    """Invalidate the tier configuration cache"""
    global _tier_config_cache, _cache_timestamp
    _tier_config_cache = {}
    _cache_timestamp = None
    log.info("[tier_service] Cache invalidated")


def _is_cache_valid() -> bool:
    """Check if cache is still valid"""
    if not _cache_timestamp:
        return False
    age = (datetime.utcnow() - _cache_timestamp).total_seconds()
    return age < _CACHE_TTL_SECONDS


def load_tier_configs(session: Session, force_reload: bool = False) -> dict[str, dict[str, Any]]:
    """
    Load all tier configurations from database with caching.
    
    Returns:
        Dict mapping tier_name -> features dict
    """
    global _tier_config_cache, _cache_timestamp
    
    # Return cached data if valid
    if not force_reload and _is_cache_valid() and _tier_config_cache:
        return _tier_config_cache
    
    # Load from database
    stmt = select(TierConfiguration)
    tier_records = session.exec(stmt).all()
    
    configs = {}
    for record in tier_records:
        try:
            features = json.loads(record.features_json or '{}')
            configs[record.tier_name.lower()] = features
        except Exception as e:
            log.error(f"[tier_service] Failed to parse features for tier {record.tier_name}: {e}")
            continue
    
    # Update cache
    _tier_config_cache = configs
    _cache_timestamp = datetime.utcnow()
    
    log.info(f"[tier_service] Loaded {len(configs)} tier configurations into cache")
    return configs


def get_tier_config(session: Session, tier_name: str) -> dict[str, Any]:
    """
    Get configuration for a specific tier.
    Falls back to hard-coded TIER_LIMITS if database config not found.
    
    Args:
        session: Database session
        tier_name: Tier identifier (e.g., 'free', 'pro', 'creator')
    
    Returns:
        Dict of feature keys to values
    """
    tier_name = tier_name.lower().strip()
    
    # Special case: admin/superadmin tiers get unlimited everything
    if tier_name in ('admin', 'superadmin'):
        return {
            'monthly_credits': None,  # Unlimited
            'max_episodes_month': None,  # Unlimited
            'audio_pipeline': 'auphonic',  # Best pipeline
            'manual_editor': True,
            'analytics_basic': True,
            'analytics_advanced': True,
            'custom_branding': True,
            'priority_support': True,
            'ai_tts_credits_month': None,  # Unlimited
        }
    
    # Try database first
    configs = load_tier_configs(session)
    if tier_name in configs:
        return configs[tier_name]
    
    # Fallback to hard-coded constants (migration period)
    if tier_name not in ('free', 'creator', 'pro', 'unlimited'):
        log.warning(f"[tier_service] Unknown tier '{tier_name}', defaulting to 'free' tier limits")
        tier_name = 'free'
    
    legacy = TIER_LIMITS.get(tier_name, TIER_LIMITS.get('free', {}))
    
    # Convert legacy format to new format
    return {
        'monthly_credits': legacy.get('max_processing_minutes_month', 0) * 1.5 if legacy.get('max_processing_minutes_month') is not None else None,
        'max_episodes_month': legacy.get('max_episodes_month'),
        # Default values for other features
        'audio_pipeline': 'auphonic' if tier_name == 'pro' else 'assemblyai',
        'manual_editor': True,
        'analytics_basic': True,
    }


def get_feature_value(
    session: Session,
    user: User,
    feature_key: str,
    default: Any = None
) -> Any:
    """
    Get a specific feature value for a user's tier.
    
    Args:
        session: Database session
        user: User object
        feature_key: Feature identifier (e.g., 'monthly_credits', 'audio_pipeline')
        default: Default value if feature not found
    
    Returns:
        Feature value (type depends on feature)
    """
    tier = getattr(user, 'tier', 'free') or 'free'
    config = get_tier_config(session, tier)
    return config.get(feature_key, default)


def check_feature_access(
    session: Session,
    user: User,
    feature_key: str
) -> bool:
    """
    Check if user has access to a boolean feature.
    
    Args:
        session: Database session
        user: User object
        feature_key: Feature identifier (e.g., 'flubber_feature', 'custom_branding')
    
    Returns:
        True if user has access, False otherwise
    """
    value = get_feature_value(session, user, feature_key, default=False)
    return bool(value)


def get_tier_credits(session: Session, tier_name: str) -> Optional[float]:
    """
    Get monthly credit allocation for a tier.
    
    Args:
        session: Database session
        tier_name: Tier identifier
    
    Returns:
        Monthly credits (None for unlimited)
    """
    config = get_tier_config(session, tier_name)
    return config.get('monthly_credits')


def calculate_processing_cost(
    session: Session,
    user: User,
    audio_duration_minutes: float,
    use_auphonic: Optional[bool] = None,
    use_elevenlabs_tts: bool = False,
    tts_duration_minutes: float = 0.0
) -> dict[str, Any]:
    """
    Calculate credit cost for processing audio.
    
    Args:
        session: Database session
        user: User object
        audio_duration_minutes: Duration of main audio in minutes
        use_auphonic: Override pipeline detection (None = auto-detect from tier)
        use_elevenlabs_tts: Whether ElevenLabs TTS is being used
        tts_duration_minutes: Duration of TTS audio in minutes
    
    Returns:
        Dict with breakdown: {
            'base_credits': float,
            'audio_credits': float,
            'tts_credits': float,
            'total_credits': float,
            'pipeline': str,
            'tts_provider': str,
            'multipliers': {...}
        }
    """
    tier = getattr(user, 'tier', 'free') or 'free'
    config = get_tier_config(session, tier)
    
    # Base conversion: 1 minute = 1.5 credits
    BASE_CREDIT_RATE = 1.5
    
    # Determine pipeline
    if use_auphonic is None:
        use_auphonic = config.get('audio_pipeline') == 'auphonic'
    
    # Calculate base audio cost
    base_audio_credits = audio_duration_minutes * BASE_CREDIT_RATE
    
    # Apply Auphonic multiplier if applicable
    if use_auphonic:
        auphonic_multiplier = config.get('auphonic_cost_multiplier', 2.0)
        audio_credits = base_audio_credits * auphonic_multiplier
    else:
        auphonic_multiplier = 1.0
        audio_credits = base_audio_credits
    
    # Calculate TTS cost
    base_tts_credits = tts_duration_minutes * BASE_CREDIT_RATE
    
    if use_elevenlabs_tts:
        elevenlabs_multiplier = config.get('elevenlabs_cost_multiplier', 3.0)
        tts_credits = base_tts_credits * elevenlabs_multiplier
    else:
        elevenlabs_multiplier = 1.0
        tts_credits = base_tts_credits
    
    total_credits = audio_credits + tts_credits
    
    return {
        'base_credits': round(base_audio_credits + base_tts_credits, 2),
        'audio_credits': round(audio_credits, 2),
        'tts_credits': round(tts_credits, 2),
        'total_credits': round(total_credits, 2),
        'pipeline': 'auphonic' if use_auphonic else 'assemblyai',
        'tts_provider': 'elevenlabs' if use_elevenlabs_tts else 'standard',
        'multipliers': {
            'base_rate': BASE_CREDIT_RATE,
            'auphonic': auphonic_multiplier if use_auphonic else None,
            'elevenlabs': elevenlabs_multiplier if use_elevenlabs_tts else None,
        }
    }


def should_use_auphonic(session: Session, user: User) -> bool:
    """
    Determine if user should use Auphonic pipeline based on tier configuration.
    
    This replaces the hard-coded logic in auphonic_helper.py
    
    Args:
        session: Database session
        user: User object
    
    Returns:
        True if Auphonic should be used, False otherwise
    """
    config = get_tier_config(session, getattr(user, 'tier', 'free') or 'free')
    pipeline = config.get('audio_pipeline', 'assemblyai')
    
    result = pipeline == 'auphonic'
    
    log.debug(
        f"[tier_service] user_id={user.id} tier={getattr(user, 'tier', 'free')} "
        f"pipeline={pipeline} → auphonic={result}"
    )
    
    return result


def get_tts_provider(session: Session, user: User) -> str:
    """
    Get TTS provider for user's tier.
    
    Returns:
        'standard' or 'elevenlabs'
    """
    return get_feature_value(session, user, 'tts_provider', default='standard')


def save_tier_config_history(
    session: Session,
    tier_name: str,
    features: dict[str, Any],
    changed_by: Optional[Any] = None,
    reason: Optional[str] = None
):
    """
    Save a historical snapshot of tier configuration.
    
    Args:
        session: Database session
        tier_name: Tier identifier
        features: Feature dict to save
        changed_by: User ID who made the change
        reason: Optional reason for the change
    """
    # Get current version number
    stmt = select(TierConfigurationHistory).where(
        TierConfigurationHistory.tier_name == tier_name
    ).order_by(desc(TierConfigurationHistory.version))
    
    latest = session.exec(stmt).first()
    next_version = (latest.version + 1) if latest else 1
    
    history = TierConfigurationHistory(
        tier_name=tier_name,
        version=next_version,
        features_json=json.dumps(features, indent=2),
        changed_by=changed_by,
        change_reason=reason
    )
    
    session.add(history)
    session.commit()
    
    log.info(f"[tier_service] Saved tier config history: tier={tier_name} version={next_version}")


def update_tier_config(
    session: Session,
    tier_name: str,
    features: dict[str, Any],
    changed_by: Optional[Any] = None,
    reason: Optional[str] = None
) -> TierConfiguration:
    """
    Update tier configuration in database.
    
    Args:
        session: Database session
        tier_name: Tier identifier
        features: Feature dict
        changed_by: User ID who made the change
        reason: Optional reason for the change
    
    Returns:
        Updated TierConfiguration record
    """
    # Save to history before updating
    save_tier_config_history(session, tier_name, features, changed_by, reason)
    
    # Update or create configuration
    stmt = select(TierConfiguration).where(TierConfiguration.tier_name == tier_name)
    record = session.exec(stmt).first()
    
    if record:
        record.features_json = json.dumps(features, indent=2)
        record.updated_at = datetime.utcnow()
    else:
        # Create new tier configuration
        display_name = tier_name.capitalize()
        is_public = tier_name not in ['unlimited', 'admin']
        
        record = TierConfiguration(
            tier_name=tier_name,
            display_name=display_name,
            is_public=is_public,
            features_json=json.dumps(features, indent=2),
            created_by=changed_by
        )
        session.add(record)
    
    session.commit()
    session.refresh(record)
    
    # Invalidate cache
    _invalidate_cache()
    
    log.info(f"[tier_service] Updated tier config: tier={tier_name}")
    return record


def get_all_feature_definitions() -> list[dict[str, Any]]:
    """
    Get all feature definitions for admin UI.
    
    Returns:
        List of feature definition dicts
    """
    return [feature.model_dump() for feature in TIER_FEATURE_DEFINITIONS]


def validate_tier_config(features: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate tier configuration before saving.
    
    Args:
        features: Feature dict to validate
    
    Returns:
        (is_valid, list_of_errors)
    """
    errors = []
    
    # Check for negative values
    for key, value in features.items():
        if isinstance(value, (int, float)) and value < 0:
            errors.append(f"{key}: Cannot be negative")
    
    # Validate pipeline dependencies
    if features.get('auto_filler_removal') and features.get('audio_pipeline') != 'auphonic':
        errors.append("auto_filler_removal requires audio_pipeline='auphonic'")
    
    if features.get('auto_noise_reduction') and features.get('audio_pipeline') != 'auphonic':
        errors.append("auto_noise_reduction requires audio_pipeline='auphonic'")
    
    if features.get('auto_leveling') and features.get('audio_pipeline') != 'auphonic':
        errors.append("auto_leveling requires audio_pipeline='auphonic'")
    
    # Validate ElevenLabs dependencies
    if features.get('elevenlabs_voices', 0) > 0 and features.get('tts_provider') != 'elevenlabs':
        errors.append("elevenlabs_voices > 0 requires tts_provider='elevenlabs'")
    
    # Validate multipliers
    for multiplier_key in ['auphonic_cost_multiplier', 'elevenlabs_cost_multiplier']:
        if multiplier_key in features:
            val = features[multiplier_key]
            if not isinstance(val, (int, float)) or val < 1.0:
                errors.append(f"{multiplier_key}: Must be >= 1.0")
    
    return (len(errors) == 0, errors)


__all__ = [
    "load_tier_configs",
    "get_tier_config",
    "get_feature_value",
    "check_feature_access",
    "get_tier_credits",
    "calculate_processing_cost",
    "should_use_auphonic",
    "get_tts_provider",
    "update_tier_config",
    "save_tier_config_history",
    "get_all_feature_definitions",
    "validate_tier_config",
]
