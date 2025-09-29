from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from api.core.database import get_session
from api.models.user import User
from api.models.settings import (
    AdminSettings,
    AppSetting,
    load_admin_settings,
    save_admin_settings,
)

from .deps import get_current_admin_user

router = APIRouter()


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


@router.get("/tiers", response_model=TierConfig)
def get_tier_config(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> TierConfig:
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


@router.put("/tiers", response_model=TierConfig)
def update_tier_config(
    cfg: TierConfig,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> TierConfig:
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


__all__ = ["router"]
