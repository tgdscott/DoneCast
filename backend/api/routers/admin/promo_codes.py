"""
Admin endpoints for managing promo codes.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func

from api.core.database import get_session
from api.models.promo_code import PromoCode, PromoCodeCreate, PromoCodeUpdate, PromoCodePublic
from api.models.user import User
from .deps import get_current_admin_user, commit_with_retry

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("", response_model=List[PromoCodePublic])
def list_promo_codes(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
    skip: int = 0,
    limit: int = 100,
) -> List[PromoCodePublic]:
    """List all promo codes."""
    del admin_user  # Unused but required for auth
    promo_codes = session.exec(
        select(PromoCode).order_by(PromoCode.created_at.desc()).offset(skip).limit(limit)
    ).all()
    return [PromoCodePublic.model_validate(pc) for pc in promo_codes]


@router.get("/{promo_code_id}", response_model=PromoCodePublic)
def get_promo_code(
    promo_code_id: UUID,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> PromoCodePublic:
    """Get a specific promo code by ID."""
    del admin_user  # Unused but required for auth
    promo_code = session.get(PromoCode, promo_code_id)
    if not promo_code:
        raise HTTPException(status_code=404, detail="Promo code not found")
    return PromoCodePublic.model_validate(promo_code)


@router.post("", response_model=PromoCodePublic, status_code=status.HTTP_201_CREATED)
def create_promo_code(
    promo_code: PromoCodeCreate,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> PromoCodePublic:
    """Create a new promo code."""
    # Normalize code to uppercase
    code_upper = promo_code.code.strip().upper()
    
    # Check if code already exists
    existing = session.exec(
        select(PromoCode).where(PromoCode.code == code_upper)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Promo code already exists")
    
    # Create new promo code
    db_promo_code = PromoCode(
        code=code_upper,
        description=promo_code.description,
        benefit_description=promo_code.benefit_description,
        is_active=promo_code.is_active,
        max_uses=promo_code.max_uses,
        expires_at=promo_code.expires_at,
        created_by=admin_user.email if admin_user else None,
        benefit_type=promo_code.benefit_type,
        benefit_value=promo_code.benefit_value,
    )
    session.add(db_promo_code)
    commit_with_retry(session)
    session.refresh(db_promo_code)
    
    log.info(f"[ADMIN] {admin_user.email} created promo code: {code_upper}")
    
    return PromoCodePublic.model_validate(db_promo_code)


@router.patch("/{promo_code_id}", response_model=PromoCodePublic)
def update_promo_code(
    promo_code_id: UUID,
    update: PromoCodeUpdate,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> PromoCodePublic:
    """Update a promo code."""
    promo_code = session.get(PromoCode, promo_code_id)
    if not promo_code:
        raise HTTPException(status_code=404, detail="Promo code not found")
    
    # Update fields
    if update.description is not None:
        promo_code.description = update.description
    if update.benefit_description is not None:
        promo_code.benefit_description = update.benefit_description
    if update.is_active is not None:
        promo_code.is_active = update.is_active
    if update.max_uses is not None:
        promo_code.max_uses = update.max_uses
    if update.expires_at is not None:
        promo_code.expires_at = update.expires_at
    if update.benefit_type is not None:
        promo_code.benefit_type = update.benefit_type
    if update.benefit_value is not None:
        promo_code.benefit_value = update.benefit_value
    
    promo_code.updated_at = datetime.utcnow()
    session.add(promo_code)
    commit_with_retry(session)
    session.refresh(promo_code)
    
    log.info(f"[ADMIN] {admin_user.email} updated promo code: {promo_code.code}")
    
    return PromoCodePublic.model_validate(promo_code)


@router.delete("/{promo_code_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_promo_code(
    promo_code_id: UUID,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    """Delete a promo code."""
    promo_code = session.get(PromoCode, promo_code_id)
    if not promo_code:
        raise HTTPException(status_code=404, detail="Promo code not found")
    
    code = promo_code.code
    session.delete(promo_code)
    commit_with_retry(session)
    
    log.info(f"[ADMIN] {admin_user.email} deleted promo code: {code}")


class PromoCodeStats(BaseModel):
    """Statistics about a promo code."""
    code: str
    usage_count: int
    max_uses: Optional[int] = None
    user_count: int
    is_active: bool
    expires_at: Optional[datetime] = None


@router.get("/{promo_code_id}/stats", response_model=PromoCodeStats)
def get_promo_code_stats(
    promo_code_id: UUID,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> PromoCodeStats:
    """Get statistics about a promo code usage."""
    del admin_user  # Unused but required for auth
    promo_code = session.get(PromoCode, promo_code_id)
    if not promo_code:
        raise HTTPException(status_code=404, detail="Promo code not found")
    
    # Count users who used this promo code
    from api.models.user import User
    user_count = session.exec(
        select(func.count(User.id)).where(User.promo_code_used == promo_code.code)
    ).one()
    
    return PromoCodeStats(
        code=promo_code.code,
        usage_count=promo_code.usage_count,
        max_uses=promo_code.max_uses,
        user_count=user_count,
        is_active=promo_code.is_active,
        expires_at=promo_code.expires_at,
    )

