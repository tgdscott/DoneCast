from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import List, Optional
from uuid import UUID

from api.core.database import get_session
from api.routers.admin.deps import get_current_admin_user
from api.models.user import User
from api.models.affiliate_settings import AffiliateProgramSettings

router = APIRouter(prefix="/affiliate-settings", tags=["admin:affiliate-settings"])

@router.get("/", response_model=List[AffiliateProgramSettings])
def list_affiliate_settings(
    session: Session = Depends(get_session),
    admin: User = Depends(get_current_admin_user),
    skip: int = 0,
    limit: int = 100
):
    """List all affiliate settings (Global Default + Overrides)."""
    return session.exec(select(AffiliateProgramSettings).offset(skip).limit(limit)).all()

@router.get("/default", response_model=Optional[AffiliateProgramSettings])
def get_default_settings(
    session: Session = Depends(get_session),
    admin: User = Depends(get_current_admin_user)
):
    """Get the global default settings."""
    return session.exec(select(AffiliateProgramSettings).where(AffiliateProgramSettings.user_id == None)).first()

@router.post("/", response_model=AffiliateProgramSettings)
def upsert_affiliate_settings(
    settings: AffiliateProgramSettings,
    session: Session = Depends(get_session),
    admin: User = Depends(get_current_admin_user)
):
    """Create or Update settings.
    To set Global Default, ensure user_id is null.
    To set User Override, ensure user_id is populated.
    """
    
    # Check if a setting already exists for this scope (user_id or None)
    existing = session.exec(
        select(AffiliateProgramSettings).where(AffiliateProgramSettings.user_id == settings.user_id)
    ).first()
    
    if existing:
        # Update existing
        existing.referrer_reward_credits = settings.referrer_reward_credits
        existing.referee_discount_percent = settings.referee_discount_percent
        existing.referee_discount_duration = settings.referee_discount_duration
        existing.is_active = settings.is_active
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing
    else:
        # Create new
        session.add(settings)
        session.commit()
        session.refresh(settings)
        return settings

@router.delete("/{id}")
def delete_affiliate_setting(
    id: UUID,
    session: Session = Depends(get_session),
    admin: User = Depends(get_current_admin_user)
):
    """Delete a specific setting override."""
    setting = session.get(AffiliateProgramSettings, id)
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    
    session.delete(setting)
    session.commit()
    return {"ok": True}
