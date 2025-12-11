from __future__ import annotations

import logging
from typing import Dict, List, Optional, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Body
from sqlmodel import Session

from api.core.database import get_session
from api.models.user import User, UserPublic
from .deps import get_current_admin_user, get_current_superadmin_user

# Import new package modules
from .users_pkg import services, schemas

router = APIRouter()
log = logging.getLogger(__name__)

@router.get("/", response_model=List[UserPublic])
async def get_all_users(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    return services.get_all_users(session)

@router.get("/full", response_model=List[schemas.UserAdminOut])
async def admin_users_full(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    """
    Get users with extra stats (admin dashboard).
    """
    return services.get_users_full(session)

@router.patch("/{user_id}", response_model=schemas.UserAdminOut)
async def admin_update_user(
    user_id: UUID,
    update: schemas.UserAdminUpdate,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    """
    Update user tier, active status, or subscription dates.
    """
    return services.update_user(session, admin_user, user_id, update)

@router.post("/{user_id}/verify-email")
async def admin_verify_user_email(
    user_id: UUID,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    Manually verify a user's email address (Admin only).
    """
    return services.verify_user_email(session, admin_user, user_id)

@router.post("/{user_id}/trigger-password-reset")
async def admin_trigger_password_reset(
    user_id: UUID,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    Trigger a password reset email for a user (Admin only).
    """
    return services.trigger_password_reset(session, admin_user, user_id)

@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    confirm_email: str = Body(..., embed=True),
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_superadmin_user), # Keep superadmin requirement
) -> Dict[str, Any]:
    """
    Delete a user and ALL their associated data.
    """
    # Note: services.delete_user_account accepts 'admin_user' but router uses 'admin_user' (aliased from Depends)
    return services.delete_user_account(session, admin_user, user_id, confirm_email)

@router.get("/{user_id}/credits")
async def get_user_credits(
    user_id: UUID, 
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    Get detailed credit history and balance for a user.
    """
    return services.get_user_credits_data(session, user_id)

@router.post("/{user_id}/credits/refund")
async def refund_user_credits(
    user_id: UUID,
    request: schemas.RefundCreditsRequest,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    Refund credits for specific ledger entries or manual amount (Admin only).
    """
    return services.process_refund_credits(session, admin_user, user_id, request)

@router.post("/{user_id}/credits/award")
async def award_user_credits(
    user_id: UUID,
    request: schemas.AwardCreditsRequest,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    Award credits to a user (Admin only).
    """
    return services.process_award_credits(session, admin_user, user_id, request)

@router.post("/refund-requests/{notification_id}/deny")
async def deny_refund_request(
    notification_id: UUID,
    request: schemas.DenyRefundRequest,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    Deny a refund request with a reason (Admin only).
    """
    return services.process_deny_refund_request(session, admin_user, notification_id, request)

@router.get("/refund-requests", response_model=List[schemas.RefundRequestResponse])
async def get_refund_requests(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
    limit: int = 50,
) -> List[schemas.RefundRequestResponse]:
    """
    Get all refund requests for admin review.
    """
    return services.get_refund_requests_list(session, admin_user, limit)

@router.get("/refund-requests/{notification_id}/detail", response_model=schemas.RefundRequestDetail)
async def get_refund_request_detail(
    notification_id: UUID,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> schemas.RefundRequestDetail:
    """
    Get comprehensive details for a refund request to help with decision-making.
    """
    return services.get_refund_request_details_service(session, admin_user, notification_id)

@router.get("/admin-action-logs/refunds", response_model=List[schemas.RefundLogEntry])
async def get_refund_logs(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
    limit: int = 100,
    offset: int = 0,
) -> List[schemas.RefundLogEntry]:
    """
    Get log of all approved or denied refund requests (Admin only).
    """
    return services.get_refund_logs_service(session, limit, offset)

@router.get("/admin-action-logs/credits", response_model=List[schemas.CreditAwardLogEntry])
async def get_credit_award_logs(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
    limit: int = 100,
    offset: int = 0,
) -> List[schemas.CreditAwardLogEntry]:
    """
    Get log of all credit awards given away (Admin only).
    """
    return services.get_credit_award_logs_service(session, limit, offset)
