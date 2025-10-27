"""
Migration 027: Initialize Tier Configuration System

Creates TierConfiguration and TierConfigurationHistory tables and populates
with default values converted from TIER_LIMITS constants (including credits calculation).
"""
import json
import logging
from sqlalchemy import text
from sqlmodel import Session, select

from api.models.tier_config import TierConfiguration, TIER_FEATURE_DEFINITIONS

log = logging.getLogger(__name__)


def _get_default_features_for_tier(tier_name: str) -> dict:
    """Get default feature values for a tier based on legacy TIER_LIMITS and current behavior"""
    
    # Base features from feature definitions
    features = {feature.key: feature.default_value for feature in TIER_FEATURE_DEFINITIONS}
    
    # Tier-specific overrides
    if tier_name == "free":
        features.update({
            'monthly_credits': 60,  # 60 minutes * 1
            'max_episodes_month': 3,
            'audio_pipeline': 'assemblyai',
            'tts_provider': 'standard',
            'manual_editor': True,
            'analytics_basic': True,
            'support_level': 'community',
            # All other boolean features default to False
        })
    
    elif tier_name == "creator":
        features.update({
            'monthly_credits': 300,  # 300 minutes * 1
            'max_episodes_month': 10,
            'audio_pipeline': 'assemblyai',
            'tts_provider': 'elevenlabs',
            'elevenlabs_voices': 1,
            'manual_editor': True,
            'flubber_feature': True,
            'intern_feature': True,
            'custom_branding': True,
            'analytics_basic': True,
            'analytics_advanced': True,
            'support_level': 'email',
            'api_access': True,
        })
    
    elif tier_name == "pro":
        features.update({
            'monthly_credits': 1000,  # 1000 minutes * 1
            'max_episodes_month': 500,
            'audio_pipeline': 'auphonic',  # Pro uses Auphonic!
            'auto_filler_removal': True,
            'auto_noise_reduction': True,
            'auto_leveling': True,
            'tts_provider': 'elevenlabs',
            'elevenlabs_voices': 3,
            'ai_enhancement': True,
            'manual_editor': True,
            'flubber_feature': True,
            'intern_feature': True,
            'custom_branding': True,
            'custom_domain': True,
            'rss_customization': True,
            'analytics_basic': True,
            'analytics_advanced': True,
            'op3_analytics': True,
            'support_level': 'priority',
            'priority_processing': True,
            'api_access': True,
            'rollover_credits': True,
        })
    
    elif tier_name == "unlimited":
        features.update({
            'monthly_credits': None,  # Unlimited credits
            'max_episodes_month': None,  # Unlimited episodes
            'audio_pipeline': 'auphonic',
            'auto_filler_removal': True,
            'auto_noise_reduction': True,
            'auto_leveling': True,
            'tts_provider': 'elevenlabs',
            'elevenlabs_voices': 100,
            'ai_enhancement': True,
            'manual_editor': True,
            'flubber_feature': True,
            'intern_feature': True,
            'custom_branding': True,
            'custom_domain': True,
            'white_label': True,
            'rss_customization': True,
            'analytics_basic': True,
            'analytics_advanced': True,
            'op3_analytics': True,
            'support_level': 'dedicated',
            'priority_processing': True,
            'api_access': True,
            'rollover_credits': True,
        })
    
    return features


def run_migration(session: Session) -> None:
    """Run the migration to initialize tier configuration system"""
    
    log.info("[migration_027] Starting tier configuration system initialization...")
    
    try:
        # Create tables if they don't exist (PostgreSQL)
        from sqlalchemy import inspect
        inspector = inspect(session.get_bind())
        existing_tables = inspector.get_table_names()
        
        if 'tierconfiguration' not in existing_tables:
            log.info("[migration_027] Creating TierConfiguration table...")
            TierConfiguration.metadata.create_all(bind=session.get_bind())
        
        if 'tierconfigurationhistory' not in existing_tables:
            log.info("[migration_027] Creating TierConfigurationHistory table...")
            from api.models.tier_config import TierConfigurationHistory
            TierConfigurationHistory.metadata.create_all(bind=session.get_bind())
        
        # Initialize tier configurations if they don't exist
        tiers = [
            {"tier_name": "free", "display_name": "Free", "is_public": True, "sort_order": 0},
            {"tier_name": "creator", "display_name": "Creator", "is_public": True, "sort_order": 1},
            {"tier_name": "pro", "display_name": "Pro", "is_public": True, "sort_order": 2},
            {"tier_name": "unlimited", "display_name": "Unlimited", "is_public": False, "sort_order": 3},
        ]
        
        for tier_def in tiers:
            # Check if tier already exists
            stmt = select(TierConfiguration).where(
                TierConfiguration.tier_name == tier_def["tier_name"]
            )
            existing = session.exec(stmt).first()
            
            if existing:
                log.info(f"[migration_027] Tier '{tier_def['tier_name']}' already exists, skipping...")
                continue
            
            # Create tier configuration
            features = _get_default_features_for_tier(tier_def["tier_name"])
            
            tier_config = TierConfiguration(
                tier_name=tier_def["tier_name"],
                display_name=tier_def["display_name"],
                is_public=tier_def["is_public"],
                sort_order=tier_def["sort_order"],
                features_json=json.dumps(features, indent=2)
            )
            
            session.add(tier_config)
            log.info(f"[migration_027] Created tier configuration for '{tier_def['tier_name']}'")
        
        session.commit()
        log.info("[migration_027] ✅ Tier configuration system initialized successfully")
        
    except Exception as e:
        log.error(f"[migration_027] ❌ Failed to initialize tier configuration system: {e}")
        session.rollback()
        raise


__all__ = ["run_migration"]
