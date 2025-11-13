"""
Credit Ledger API - User-facing credit spending transparency

Provides invoice-like views of credit charges grouped by episode,
with detailed line items and timestamps for refund processing.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func, col as sqlmodel_col
from sqlalchemy import extract, desc as sa_desc, Column, case

from api.core.database import get_session
from api.models.user import User
from api.models.usage import ProcessingMinutesLedger, LedgerDirection, LedgerReason
from api.models.podcast import Episode
from api.routers.auth import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix="/billing/ledger", tags=["Billing", "Credits"])


class LedgerLineItem(BaseModel):
    """Single credit charge/refund line item"""
    id: int
    timestamp: datetime
    direction: str  # DEBIT or CREDIT
    reason: str
    credits: float
    minutes: int  # Legacy field
    notes: Optional[str] = None
    cost_breakdown: Optional[dict] = None
    correlation_id: Optional[str] = None
    refund_status: Optional[str] = None  # pending, approved, denied
    refund_denial_reason: Optional[str] = None
    
    class Config:
        from_attributes = True


class EpisodeInvoice(BaseModel):
    """Invoice-like view of all charges for a single episode"""
    episode_id: UUID
    episode_number: Optional[int] = None
    episode_title: Optional[str] = None
    podcast_title: Optional[str] = None
    total_credits_charged: float
    total_credits_refunded: float
    net_credits: float  # charged - refunded
    line_items: List[LedgerLineItem]
    created_at: datetime  # Episode creation timestamp
    
    class Config:
        from_attributes = True


class AccountLedgerItem(BaseModel):
    """Charges not associated with a specific episode"""
    id: int
    timestamp: datetime
    direction: str
    reason: str
    credits: float
    notes: Optional[str] = None
    cost_breakdown: Optional[dict] = None
    refund_status: Optional[str] = None  # pending, approved, denied
    refund_denial_reason: Optional[str] = None
    
    class Config:
        from_attributes = True


class LedgerSummaryResponse(BaseModel):
    """Complete ledger view for a user"""
    # Summary stats
    total_credits_available: float
    total_credits_used_this_month: float
    total_credits_remaining: float
    
    # Wallet breakdown
    purchased_credits_available: float = Field(default=0.0, description="Available purchased credits (never expire)")
    monthly_allocation_available: float = Field(default=0.0, description="Available monthly + rollover credits")
    monthly_credits: float = Field(default=0.0, description="Monthly credits from plan")
    rollover_credits: float = Field(default=0.0, description="Rolled over credits")
    
    # Episode-based charges (grouped by episode)
    episode_invoices: List[EpisodeInvoice]
    
    # Account-level charges (not tied to episodes)
    account_charges: List[AccountLedgerItem]
    
    # Time period
    period_start: datetime
    period_end: datetime


@router.get("/summary", response_model=LedgerSummaryResponse)
async def get_ledger_summary(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    months_back: int = Query(default=1, ge=1, le=12, description="Number of months to look back"),
) -> LedgerSummaryResponse:
    """
    Get complete credit ledger for the user, grouped by episode.
    
    This is the "invoice view" - each episode is like an invoice with line items
    showing all associated charges (transcription, TTS, assembly, etc.)
    """
    # Calculate time period
    now = datetime.utcnow()
    period_end = now
    period_start = now - timedelta(days=30 * months_back)
    
    # Get all ledger entries in the period
    stmt = (
        select(ProcessingMinutesLedger)
        .where(ProcessingMinutesLedger.user_id == current_user.id)
        .where(ProcessingMinutesLedger.created_at >= period_start)
        .where(ProcessingMinutesLedger.created_at <= period_end)
        .order_by(sqlmodel_col(ProcessingMinutesLedger.created_at).desc())
    )
    
    all_entries = session.exec(stmt).all()
    
    # Group by episode_id
    episode_map: dict[UUID, List[ProcessingMinutesLedger]] = {}
    account_level_entries: List[ProcessingMinutesLedger] = []
    
    for entry in all_entries:
        if entry.episode_id:
            if entry.episode_id not in episode_map:
                episode_map[entry.episode_id] = []
            episode_map[entry.episode_id].append(entry)
        else:
            account_level_entries.append(entry)
    
    # Build episode invoices
    episode_invoices: List[EpisodeInvoice] = []
    
    for episode_id, entries in episode_map.items():
        # Get episode details
        episode = session.get(Episode, episode_id)
        
        # Calculate totals
        total_charged = sum(
            e.credits for e in entries 
            if e.direction == LedgerDirection.DEBIT
        )
        total_refunded = sum(
            e.credits for e in entries 
            if e.direction == LedgerDirection.CREDIT
        )
        
        # Get refund statuses for episode entries
        episode_refund_statuses = {}
        try:
            from api.models.notification import Notification
            refund_notifications = session.exec(
                select(Notification)
                .where(Notification.user_id == current_user.id)
                .where(Notification.type == "refund_request")
            ).all()
            
            for notif in refund_notifications:
                try:
                    import json
                    details = json.loads(notif.body)
                    entry_ids = details.get("ledger_entry_ids", [])
                    status = details.get("status", "pending")
                    denial_reason = details.get("denial_reason")
                    
                    for entry_id in entry_ids:
                        episode_refund_statuses[entry_id] = {
                            "status": status,
                            "denial_reason": denial_reason
                        }
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
        except Exception:
            pass
        
        # Convert entries to line items
        line_items = [
            LedgerLineItem(
                id=e.id or 0,  # Handle None case
                timestamp=e.created_at,
                direction=e.direction.value,
                reason=e.reason.value,
                credits=e.credits,
                minutes=e.minutes,
                notes=e.notes,
                cost_breakdown=_parse_cost_breakdown(e.cost_breakdown_json),
                correlation_id=e.correlation_id,
                refund_status=episode_refund_statuses.get(e.id or 0, {}).get("status"),
                refund_denial_reason=episode_refund_statuses.get(e.id or 0, {}).get("denial_reason")
            )
            for e in sorted(entries, key=lambda x: x.created_at, reverse=True)
        ]
        
        episode_invoices.append(EpisodeInvoice(
            episode_id=episode_id,
            episode_number=episode.episode_number if episode else None,
            episode_title=episode.title if episode else f"Episode {episode_id}",
            podcast_title=None,  # Could join Podcast table if needed
            total_credits_charged=total_charged,
            total_credits_refunded=total_refunded,
            net_credits=total_charged - total_refunded,
            line_items=line_items,
            created_at=episode.created_at if episode else entries[0].created_at
        ))
    
    # Sort invoices by date (newest first)
    episode_invoices.sort(key=lambda x: x.created_at, reverse=True)
    
    # Get refund request statuses for account-level entries
    account_refund_statuses = {}
    try:
        from api.models.notification import Notification
        refund_notifications = session.exec(
            select(Notification)
            .where(Notification.user_id == current_user.id)
            .where(Notification.type == "refund_request")
        ).all()
        
        for notif in refund_notifications:
            try:
                import json
                details = json.loads(notif.body)
                entry_ids = details.get("ledger_entry_ids", [])
                status = details.get("status", "pending")
                denial_reason = details.get("denial_reason")
                
                for entry_id in entry_ids:
                    account_refund_statuses[entry_id] = {
                        "status": status,
                        "denial_reason": denial_reason
                    }
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
    except Exception:
        pass
    
    # Build account-level charges
    account_charges = [
        AccountLedgerItem(
            id=e.id or 0,  # Handle None case
            timestamp=e.created_at,
            direction=e.direction.value,
            reason=e.reason.value,
            credits=e.credits,
            notes=e.notes,
            cost_breakdown=_parse_cost_breakdown(e.cost_breakdown_json),
            refund_status=account_refund_statuses.get(e.id or 0, {}).get("status"),
            refund_denial_reason=account_refund_statuses.get(e.id or 0, {}).get("denial_reason")
        )
        for e in sorted(account_level_entries, key=lambda x: x.created_at, reverse=True)
    ]
    
    # Calculate summary stats
    from api.services.billing import credits
    balance = credits.get_user_credit_balance(session, current_user.id)
    
    # Get wallet details
    from api.services.billing.wallet import get_wallet_details
    wallet_details = get_wallet_details(session, current_user.id)
    
    # Get current month usage
    current_month = now.month
    current_year = now.year
    
    month_stmt = (
        select(func.sum(
            case(
                (ProcessingMinutesLedger.direction == LedgerDirection.DEBIT, ProcessingMinutesLedger.credits),
                else_=0
            )
        ))
        .where(ProcessingMinutesLedger.user_id == current_user.id)
        .where(extract('month', sqlmodel_col(ProcessingMinutesLedger.created_at)) == current_month)
        .where(extract('year', sqlmodel_col(ProcessingMinutesLedger.created_at)) == current_year)
    )
    
    used_this_month = session.exec(month_stmt).one() or 0.0
    
    # Get tier allocation
    from api.services import tier_service
    tier_credits = tier_service.get_tier_credits(
        session, 
        getattr(current_user, 'tier', 'free') or 'free'
    )
    
    available = tier_credits if tier_credits else 999999.0
    remaining = balance
    
    return LedgerSummaryResponse(
        total_credits_available=available,
        total_credits_used_this_month=used_this_month,
        total_credits_remaining=remaining,
        purchased_credits_available=wallet_details.get("purchased_credits_available", 0.0),
        monthly_allocation_available=wallet_details.get("monthly_allocation_available", 0.0),
        monthly_credits=wallet_details.get("monthly_credits", 0.0),
        rollover_credits=wallet_details.get("rollover_credits", 0.0),
        episode_invoices=episode_invoices,
        account_charges=account_charges,
        period_start=period_start,
        period_end=period_end
    )


@router.get("/episode/{episode_id}", response_model=EpisodeInvoice)
async def get_episode_invoice(
    episode_id: UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> EpisodeInvoice:
    """
    Get detailed invoice for a specific episode.
    
    Shows all credit charges associated with this episode,
    useful for refund requests or billing disputes.
    """
    # Verify episode belongs to user
    episode = session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    if episode.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this episode")
    
    # Get all ledger entries for this episode
    stmt = (
        select(ProcessingMinutesLedger)
        .where(ProcessingMinutesLedger.episode_id == episode_id)
        .where(ProcessingMinutesLedger.user_id == current_user.id)
        .order_by(sqlmodel_col(ProcessingMinutesLedger.created_at).desc())
    )
    
    entries = session.exec(stmt).all()
    
    if not entries:
        raise HTTPException(status_code=404, detail="No charges found for this episode")
    
    # Calculate totals
    total_charged = sum(
        e.credits for e in entries 
        if e.direction == LedgerDirection.DEBIT
    )
    total_refunded = sum(
        e.credits for e in entries 
        if e.direction == LedgerDirection.CREDIT
    )
    
    # Convert to line items
    line_items = [
        LedgerLineItem(
            id=e.id or 0,  # Handle None case
            timestamp=e.created_at,
            direction=e.direction.value,
            reason=e.reason.value,
            credits=e.credits,
            minutes=e.minutes,
            notes=e.notes,
            cost_breakdown=_parse_cost_breakdown(e.cost_breakdown_json),
            correlation_id=e.correlation_id
        )
        for e in entries
    ]
    
    return EpisodeInvoice(
        episode_id=episode_id,
        episode_number=episode.episode_number,
        episode_title=episode.title,
        podcast_title=None,  # Could join if needed
        total_credits_charged=total_charged,
        total_credits_refunded=total_refunded,
        net_credits=total_charged - total_refunded,
        line_items=line_items,
        created_at=episode.created_at
    )


class RefundRequest(BaseModel):
    """Request model for refund requests"""
    episode_id: Optional[UUID] = None
    ledger_entry_ids: List[int] = Field(default_factory=list)
    reason: str = Field(..., min_length=10, description="Reason for refund request (minimum 10 characters)")
    notes: Optional[str] = None


@router.post("/refund-request")
async def request_refund(
    request: RefundRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Submit a refund request for specific charges.
    
    Creates a notification for admin review with all relevant details.
    """
    if not request.episode_id and not request.ledger_entry_ids:
        raise HTTPException(status_code=400, detail="Must provide episode_id or ledger_entry_ids")
    
    if not request.reason or len(request.reason.strip()) < 10:
        raise HTTPException(
            status_code=400, 
            detail="Please provide a detailed reason (at least 10 characters)"
        )
    
    # Verify entries belong to user
    if request.ledger_entry_ids:
        from sqlalchemy import column
        entries = session.exec(
            select(ProcessingMinutesLedger)
            .where(column('id').in_(request.ledger_entry_ids))
            .where(ProcessingMinutesLedger.user_id == current_user.id)
        ).all()
        
        if len(entries) != len(request.ledger_entry_ids):
            raise HTTPException(status_code=404, detail="Some entries not found or not authorized")
    
    # Create notification for admin
    from api.models.notification import Notification
    from api.routers.auth import is_admin_email
    from sqlmodel import select as sqlmodel_select
    
    # Find all admin users to notify
    admin_users = session.exec(
        sqlmodel_select(User).where(User.is_admin == True)  # noqa: E712
    ).all()
    
    import json
    
    # Create notification for requesting user with status tracking
    request_details = {
        "user_id": str(current_user.id),
        "user_email": current_user.email,
        "episode_id": str(request.episode_id) if request.episode_id else None,
        "ledger_entry_ids": request.ledger_entry_ids,
        "reason": request.reason,
        "notes": request.notes,
        "timestamp": datetime.utcnow().isoformat(),
        "status": "pending"  # pending, approved, denied
    }
    
    # Create user-friendly message (don't expose internal details)
    user_message = f"Your refund request has been submitted and is under review."
    if request.reason:
        user_message += f"\n\nReason: {request.reason}"
    user_message += "\n\nYou will be notified once your request has been processed."
    
    user_notification = Notification(
        user_id=current_user.id,
        type="refund_request",
        title="Credit Refund Request Submitted",
        body=user_message  # User-friendly message, not raw JSON
    )
    session.add(user_notification)
    session.flush()  # Get the notification ID
    
    # Create notifications for all admin users
    admin_details = {
        "user_id": str(current_user.id),
        "user_email": current_user.email,
        "episode_id": str(request.episode_id) if request.episode_id else None,
        "ledger_entry_ids": request.ledger_entry_ids,
        "reason": request.reason,
        "notes": request.notes,
        "timestamp": datetime.utcnow().isoformat(),
        "status": "pending",
        "user_notification_id": str(user_notification.id)  # Link to user's notification
    }
    
    admin_details_json = json.dumps(admin_details, indent=2)
    
    for admin_user in admin_users:
        admin_notification = Notification(
            user_id=admin_user.id,
            type="refund_request",
            title=f"Credit Refund Request from {current_user.email}",
            body=f"User {current_user.email} requested refund for {len(request.ledger_entry_ids) if request.ledger_entry_ids else 'episode'} charges.\n\nReason: {request.reason}\n\nDetails:\n{admin_details_json}"
        )
        session.add(admin_notification)
    
    session.commit()
    
    log.info(
        f"[billing-ledger] Refund request from user {current_user.id}: "
        f"episode={request.episode_id}, entries={request.ledger_entry_ids}, reason={request.reason[:50]}"
    )
    
    return {
        "success": True,
        "message": "Refund request submitted. Our team will review and respond within 24-48 hours.",
        "notification_id": str(user_notification.id)
    }


class CreditChargeItem(BaseModel):
    """Single credit charge/refund item for line item view"""
    id: int
    timestamp: datetime
    episode_id: Optional[UUID] = None
    episode_title: Optional[str] = None
    direction: str  # DEBIT or CREDIT
    reason: str
    credits: float
    minutes: int
    notes: Optional[str] = None
    
    class Config:
        from_attributes = True


class CreditChargesResponse(BaseModel):
    """Paginated credit charges response"""
    charges: List[CreditChargeItem]
    pagination: dict
    credits_balance: float
    credits_allocated: Optional[float]
    credits_used_this_month: float
    credits_breakdown: dict
    purchased_credits_available: float = Field(default=0.0, description="Available purchased credits (never expire)")
    monthly_allocation_available: float = Field(default=0.0, description="Available monthly + rollover credits")
    monthly_credits: float = Field(default=0.0, description="Monthly credits from plan")
    rollover_credits: float = Field(default=0.0, description="Rolled over credits")


@router.get("/charges", response_model=CreditChargesResponse)
async def get_credit_charges(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    per_page: int = Query(default=20, ge=1, le=100, description="Items per page (20, 50, or 100)"),
) -> CreditChargesResponse:
    """
    Get paginated credit charges for the current user.
    
    Similar to admin view but for the user's own charges.
    Returns a simple line-item list with pagination.
    """
    # Validate per_page
    if per_page not in [20, 50, 100]:
        per_page = 20
    
    # Get credit balance
    from api.services.billing import credits
    balance = credits.get_user_credit_balance(session, current_user.id)
    
    # Get wallet details
    from api.services.billing.wallet import get_wallet_details
    wallet_details = get_wallet_details(session, current_user.id)
    
    # Get tier allocation
    from api.services import tier_service
    tier = getattr(current_user, 'tier', 'free') or 'free'
    tier_credits = tier_service.get_tier_credits(session, tier)
    
    # Get monthly breakdown
    from datetime import datetime, timezone
    from api.services.billing import usage as usage_svc
    
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    breakdown = usage_svc.month_credits_breakdown(session, current_user.id, start_of_month, now)
    
    # Get paginated charges
    from sqlmodel import select, func
    from sqlalchemy import desc as sa_desc
    
    # Count total charges
    count_stmt = (
        select(func.count(ProcessingMinutesLedger.id))
        .where(ProcessingMinutesLedger.user_id == current_user.id)
    )
    total_count = session.exec(count_stmt).one()
    
    # Get paginated charges
    offset = (page - 1) * per_page
    stmt = (
        select(ProcessingMinutesLedger)
        .where(ProcessingMinutesLedger.user_id == current_user.id)
        .order_by(sa_desc(ProcessingMinutesLedger.created_at))
        .limit(per_page)
        .offset(offset)
    )
    recent = session.exec(stmt).all()
    
    # Get refund request statuses for these entries
    from api.models.notification import Notification
    refund_statuses = {}
    try:
        # Get all refund request notifications for this user
        refund_notifications = session.exec(
            select(Notification)
            .where(Notification.user_id == current_user.id)
            .where(Notification.type == "refund_request")
        ).all()
        
        # Parse each notification to extract status
        for notif in refund_notifications:
            try:
                import json
                details = json.loads(notif.body)
                entry_ids = details.get("ledger_entry_ids", [])
                status = details.get("status", "pending")
                denial_reason = details.get("denial_reason")
                
                for entry_id in entry_ids:
                    refund_statuses[entry_id] = {
                        "status": status,
                        "denial_reason": denial_reason,
                        "notification_id": str(notif.id)
                    }
            except (json.JSONDecodeError, KeyError, TypeError):
                # Old format or invalid JSON, skip
                continue
    except Exception:
        # Notifications not available or error, continue without status
        pass
    
    charges = []
    for entry in recent:
        entry_id = entry.id or 0
        refund_info = refund_statuses.get(entry_id, {})
        
        charge = CreditChargeItem(
            id=entry_id,
            timestamp=entry.created_at,
            episode_id=entry.episode_id,
            direction=entry.direction.value if hasattr(entry.direction, 'value') else str(entry.direction),
            reason=entry.reason.value if hasattr(entry.reason, 'value') else str(entry.reason),
            credits=float(entry.credits),
            minutes=entry.minutes,
            notes=entry.notes,
            refund_status=refund_info.get("status"),
            refund_denial_reason=refund_info.get("denial_reason")
        )
        
        # Try to get episode title if episode_id exists
        if entry.episode_id:
            try:
                episode = session.get(Episode, entry.episode_id)
                if episode:
                    charge.episode_title = episode.title
            except Exception:
                pass
        
        charges.append(charge)
    
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
    
    return CreditChargesResponse(
        charges=charges,
        pagination={
            "page": page,
            "per_page": per_page,
            "total": total_count,
            "total_pages": total_pages
        },
        credits_balance=float(balance),
        credits_allocated=float(tier_credits) if tier_credits is not None else None,
        credits_used_this_month=float(breakdown.get('total', 0)),
        credits_breakdown={
            "transcription": float(breakdown.get('transcription', 0)),
            "assembly": float(breakdown.get('assembly', 0)),
            "tts_generation": float(breakdown.get('tts_generation', 0)),
            "auphonic_processing": float(breakdown.get('auphonic_processing', 0)),
            "storage": float(breakdown.get('storage', 0)),
        },
        purchased_credits_available=float(wallet_details.get("purchased_credits_available", 0.0)),
        monthly_allocation_available=float(wallet_details.get("monthly_allocation_available", 0.0)),
        monthly_credits=float(wallet_details.get("monthly_credits", 0.0)),
        rollover_credits=float(wallet_details.get("rollover_credits", 0.0)),
    )


def _parse_cost_breakdown(json_str: Optional[str]) -> Optional[dict]:
    """Parse cost_breakdown_json string to dict"""
    if not json_str:
        return None
    
    try:
        import json
        return json.loads(json_str)
    except Exception:
        return None


__all__ = ["router"]
