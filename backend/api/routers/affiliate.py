"""
Endpoints for user affiliate/referral codes.
"""
from __future__ import annotations

import logging
import random
import string
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select, func

from datetime import datetime

from api.core.database import get_session
from api.core.config import settings
from api.models.affiliate_code import UserAffiliateCode, UserAffiliateCodePublic
from api.models.user import User
from api.models.promo_code import PromoCode
from api.routers.auth.utils import get_current_user

router = APIRouter()
log = logging.getLogger(__name__)


def generate_affiliate_code(length: int = 8) -> str:
    """Generate a random affiliate code."""
    # Use uppercase letters and numbers, exclude similar-looking characters
    chars = string.ascii_uppercase.replace('I', '').replace('O', '').replace('0', '') + string.digits.replace('0', '').replace('1', '')
    return ''.join(random.choice(chars) for _ in range(length))


@router.get("/me", response_model=UserAffiliateCodePublic)
def get_my_affiliate_code(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> UserAffiliateCodePublic:
    """Get the current user's affiliate code, creating one if it doesn't exist."""
    # Check if user already has an affiliate code
    affiliate_code = session.exec(
        select(UserAffiliateCode).where(UserAffiliateCode.user_id == current_user.id)
    ).first()
    
    if not affiliate_code:
        # Generate a unique code
        max_attempts = 100
        for _ in range(max_attempts):
            code = generate_affiliate_code()
            # Check if code already exists (in affiliate codes or promo codes)
            existing_affiliate = session.exec(
                select(UserAffiliateCode).where(UserAffiliateCode.code == code)
            ).first()
            existing_promo = session.exec(
                select(PromoCode).where(PromoCode.code == code)
            ).first()
            
            if not existing_affiliate and not existing_promo:
                # Create new affiliate code
                affiliate_code = UserAffiliateCode(
                    user_id=current_user.id,
                    code=code
                )
                session.add(affiliate_code)
                session.commit()
                session.refresh(affiliate_code)
                log.info(f"[AFFILIATE] Created affiliate code {code} for user {current_user.email}")
                break
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate unique affiliate code"
            )
    
    # Count referrals
    referral_count = session.exec(
        select(func.count(User.id)).where(User.referred_by_user_id == current_user.id)
    ).one() or 0
    
    # Generate referral link
    app_base = (settings.APP_BASE_URL or "https://app.podcastplusplus.com").rstrip("/")
    referral_link = f"{app_base}/signup?ref={affiliate_code.code}"
    
    return UserAffiliateCodePublic(
        id=affiliate_code.id,
        code=affiliate_code.code,
        created_at=affiliate_code.created_at,
        referral_count=referral_count,
        referral_link=referral_link
    )


@router.post("/me/regenerate", response_model=UserAffiliateCodePublic)
def regenerate_affiliate_code(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> UserAffiliateCodePublic:
    """Regenerate the user's affiliate code (admin only for now, or if no referrals yet)."""
    # Check if user has an affiliate code
    affiliate_code = session.exec(
        select(UserAffiliateCode).where(UserAffiliateCode.user_id == current_user.id)
    ).first()
    
    # Check if user has any referrals
    referral_count = session.exec(
        select(func.count(User.id)).where(User.referred_by_user_id == current_user.id)
    ).one() or 0
    
    if referral_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot regenerate affiliate code after referrals have been made"
        )
    
    # Generate a new unique code
    max_attempts = 100
    new_code = None
    for _ in range(max_attempts):
        code = generate_affiliate_code()
        # Check if code already exists
        existing_affiliate = session.exec(
            select(UserAffiliateCode).where(UserAffiliateCode.code == code)
        ).first()
        existing_promo = session.exec(
            select(PromoCode).where(PromoCode.code == code)
        ).first()
        
        if not existing_affiliate and not existing_promo:
            new_code = code
            break
    
    if not new_code:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate unique affiliate code"
        )
    
    # Update or create affiliate code
    if affiliate_code:
        affiliate_code.code = new_code
        affiliate_code.updated_at = datetime.utcnow()
        session.add(affiliate_code)
    else:
        affiliate_code = UserAffiliateCode(
            user_id=current_user.id,
            code=new_code
        )
        session.add(affiliate_code)
    
    session.commit()
    session.refresh(affiliate_code)
    
    log.info(f"[AFFILIATE] Regenerated affiliate code {new_code} for user {current_user.email}")
    
    # Generate referral link
    app_base = (settings.APP_BASE_URL or "https://app.podcastplusplus.com").rstrip("/")
    referral_link = f"{app_base}/signup?ref={affiliate_code.code}"
    
    return UserAffiliateCodePublic(
        id=affiliate_code.id,
        code=affiliate_code.code,
        created_at=affiliate_code.created_at,
        referral_count=referral_count,
        referral_link=referral_link
    )

