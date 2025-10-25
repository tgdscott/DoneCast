from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select, desc

from api.core.database import get_session
from api.models.user import User
from api.models.settings import (
    AdminSettings,
    AppSetting,
    LandingPageContent,
    load_admin_settings,
    load_landing_content,
    save_admin_settings,
    save_landing_content,
)
from api.models.tier_config import (
    TierConfiguration,
    TierConfigurationHistory,
    TierFeatureDefinition,
    TIER_FEATURE_DEFINITIONS,
)
from api.services import tier_service
from api.core.constants import TIER_LIMITS

from .deps import get_current_admin_user

router = APIRouter()


# ===== NEW COMPREHENSIVE TIER EDITOR SYSTEM =====

class TierFeatureValue(BaseModel):
    """Feature value for a single tier"""
    tier_name: str
    value: Any


class TierFeatureResponse(BaseModel):
    """Feature definition with values for all tiers"""
    key: str
    label: str
    description: str
    category: str
    type: str
    options: list[str] | None = None
    help_text: str | None = None
    values: dict[str, Any]  # tier_name -> value


class TierConfigResponse(BaseModel):
    """Complete tier configuration for admin editor"""
    tiers: list[dict[str, Any]]  # List of tier metadata
    features: list[TierFeatureResponse]
    feature_definitions: list[dict[str, Any]]
    hard_coded_values: dict[str, dict[str, Any]]  # Comparison with TIER_LIMITS


class TierConfigUpdateRequest(BaseModel):
    """Request to update tier configuration"""
    tier_name: str
    features: dict[str, Any]
    reason: str | None = None


@router.get("/tiers/v2", response_model=TierConfigResponse)
def get_comprehensive_tier_config(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> TierConfigResponse:
    """
    Get comprehensive tier configuration for admin editor.
    Includes feature definitions, current values, and comparison with hard-coded values.
    """
    del admin_user
    
    # Define tiers
    tier_names = ["free", "starter", "creator", "pro", "unlimited"]
    tiers_metadata = [
        {"tier_name": "free", "display_name": "Free", "is_public": True, "sort_order": 0},
        {"tier_name": "starter", "display_name": "Starter", "is_public": True, "sort_order": 1},
        {"tier_name": "creator", "display_name": "Creator", "is_public": True, "sort_order": 2},
        {"tier_name": "pro", "display_name": "Pro", "is_public": True, "sort_order": 3},
        {"tier_name": "unlimited", "display_name": "Unlimited", "is_public": False, "sort_order": 4},
    ]
    
    # Load current configurations from database
    configs = tier_service.load_tier_configs(session, force_reload=True)
    
    # Build feature responses
    feature_responses = []
    for feature_def in TIER_FEATURE_DEFINITIONS:
        values = {}
        for tier_name in tier_names:
            tier_config = configs.get(tier_name, {})
            values[tier_name] = tier_config.get(feature_def.key, feature_def.default_value)
        
        feature_responses.append(TierFeatureResponse(
            key=feature_def.key,
            label=feature_def.label,
            description=feature_def.description,
            category=feature_def.category,
            type=feature_def.type,
            options=feature_def.options,
            help_text=feature_def.help_text,
            values=values
        ))
    
    # Get hard-coded values for comparison
    hard_coded = {}
    for tier_name in tier_names:
        legacy = TIER_LIMITS.get(tier_name, {})
        hard_coded[tier_name] = {
            'monthly_credits': legacy.get('max_processing_minutes_month', 0) * 1.5 if legacy.get('max_processing_minutes_month') is not None else None,
            'max_episodes_month': legacy.get('max_episodes_month'),
            'audio_pipeline': 'auphonic' if tier_name == 'pro' else 'assemblyai',
        }
    
    return TierConfigResponse(
        tiers=tiers_metadata,
        features=feature_responses,
        feature_definitions=[f.model_dump() for f in TIER_FEATURE_DEFINITIONS],
        hard_coded_values=hard_coded
    )


@router.put("/tiers/v2", response_model=dict[str, Any])
def update_comprehensive_tier_config(
    request: TierConfigUpdateRequest,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> dict[str, Any]:
    """
    Update tier configuration in database.
    Validates before saving and records history.
    """
    # Validate configuration
    is_valid, errors = tier_service.validate_tier_config(request.features)
    if not is_valid:
        raise HTTPException(
            status_code=400,
            detail={"message": "Invalid tier configuration", "errors": errors}
        )
    
    # Update configuration
    try:
        tier_service.update_tier_config(
            session=session,
            tier_name=request.tier_name,
            features=request.features,
            changed_by=admin_user.id,
            reason=request.reason
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update tier configuration: {str(e)}"
        )
    
    return {
        "success": True,
        "tier_name": request.tier_name,
        "message": "Tier configuration updated successfully"
    }


@router.get("/tiers/v2/history/{tier_name}")
def get_tier_config_history(
    tier_name: str,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
    limit: int = 20
) -> list[dict[str, Any]]:
    """Get historical versions of tier configuration"""
    del admin_user
    
    stmt = (
        select(TierConfigurationHistory)
        .where(TierConfigurationHistory.tier_name == tier_name)
        .order_by(desc(TierConfigurationHistory.created_at))
        .limit(limit)
    )
    
    history_records = session.exec(stmt).all()
    
    return [
        {
            "version": record.version,
            "features": json.loads(record.features_json or "{}"),
            "changed_by": str(record.changed_by) if record.changed_by else None,
            "change_reason": record.change_reason,
            "created_at": record.created_at.isoformat()
        }
        for record in history_records
    ]


@router.get("/tiers/v2/definitions")
def get_feature_definitions(
    admin_user: User = Depends(get_current_admin_user),
) -> list[dict[str, Any]]:
    """Get all feature definitions for UI"""
    del admin_user
    return tier_service.get_all_feature_definitions()


# ===== LEGACY TIER EDITOR (KEEP FOR BACKWARD COMPATIBILITY) =====

class TierFeature(BaseModel):
    key: str
    label: str
    type: str
    values: dict[str, object]


class TierConfig(BaseModel):
    tiers: list[str]
    features: list[TierFeature]


def _default_tier_config() -> TierConfig:
    return TierConfig(
        tiers=["Free", "Creator", "Pro"],
        features=[
            TierFeature(
                key="can_use_elevenlabs",
                label="Can use ElevenLabs",
                type="boolean",
                values={"Free": False, "Creator": True, "Pro": True},
            ),
            TierFeature(
                key="can_use_flubber",
                label="Can use Flubber",
                type="boolean",
                values={"Free": False, "Creator": False, "Pro": True},
            ),
            TierFeature(
                key="processing_minutes",
                label="Processing minutes allowed",
                type="number",
                values={"Free": 30, "Creator": 300, "Pro": 3000},
            ),
        ],
    )


@router.get("/tiers", response_model=TierConfig, deprecated=True)
def get_tier_config_legacy(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> TierConfig:
    """Legacy tier config endpoint - use /tiers/v2 instead"""
    del admin_user
    record = session.get(AppSetting, "tier_config")
    if not record:
        cfg = _default_tier_config()
        try:
            record = AppSetting(key="tier_config", value_json=cfg.model_dump_json())
            session.add(record)
            session.commit()
        except Exception:
            session.rollback()
            return cfg
        return cfg
    try:
        data = json.loads(record.value_json or "{}")
        return TierConfig(**data)
    except Exception:
        return _default_tier_config()


@router.put("/tiers", response_model=TierConfig, deprecated=True)
def update_tier_config_legacy(
    cfg: TierConfig,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> TierConfig:
    """Legacy tier config endpoint - use /tiers/v2 instead"""
    del admin_user
    record = session.get(AppSetting, "tier_config")
    payload = cfg.model_dump_json()
    try:
        if record:
            record.value_json = payload
            record.updated_at = datetime.utcnow()
            session.add(record)
        else:
            record = AppSetting(key="tier_config", value_json=payload)
            session.add(record)
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save tier config: {exc}")
    return cfg


@router.get("/settings", response_model=AdminSettings)
def get_admin_settings(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> AdminSettings:
    del admin_user
    return load_admin_settings(session)


@router.put("/settings", response_model=AdminSettings)
def update_admin_settings(
    payload: AdminSettings,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> AdminSettings:
    del admin_user
    return save_admin_settings(session, payload)


@router.get("/landing", response_model=LandingPageContent)
def get_landing_page_content(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> LandingPageContent:
    del admin_user
    return load_landing_content(session)


@router.put("/landing", response_model=LandingPageContent)
def update_landing_page_content(
    payload: LandingPageContent,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> LandingPageContent:
    del admin_user
    return save_landing_content(session, payload)


__all__ = ["router"]
