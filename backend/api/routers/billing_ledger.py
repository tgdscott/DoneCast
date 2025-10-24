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

router = APIRouter(prefix="/api/billing/ledger", tags=["Billing", "Credits"])


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
    
    class Config:
        from_attributes = True


class LedgerSummaryResponse(BaseModel):
    """Complete ledger view for a user"""
    # Summary stats
    total_credits_available: float
    total_credits_used_this_month: float
    total_credits_remaining: float
    
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
                correlation_id=e.correlation_id
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
    
    # Build account-level charges
    account_charges = [
        AccountLedgerItem(
            id=e.id or 0,  # Handle None case
            timestamp=e.created_at,
            direction=e.direction.value,
            reason=e.reason.value,
            credits=e.credits,
            notes=e.notes,
            cost_breakdown=_parse_cost_breakdown(e.cost_breakdown_json)
        )
        for e in sorted(account_level_entries, key=lambda x: x.created_at, reverse=True)
    ]
    
    # Calculate summary stats
    from api.services.billing import credits
    balance = credits.get_user_credit_balance(session, current_user.id)
    
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


@router.post("/refund-request")
async def request_refund(
    episode_id: Optional[UUID] = None,
    ledger_entry_ids: List[int] = [],
    reason: str = "",
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Submit a refund request for specific charges.
    
    Creates a notification for admin review with all relevant details.
    """
    if not episode_id and not ledger_entry_ids:
        raise HTTPException(status_code=400, detail="Must provide episode_id or ledger_entry_ids")
    
    if not reason or len(reason.strip()) < 10:
        raise HTTPException(
            status_code=400, 
            detail="Please provide a detailed reason (at least 10 characters)"
        )
    
    # Verify entries belong to user
    if ledger_entry_ids:
        from sqlalchemy import column
        entries = session.exec(
            select(ProcessingMinutesLedger)
            .where(column('id').in_(ledger_entry_ids))
            .where(ProcessingMinutesLedger.user_id == current_user.id)
        ).all()
        
        if len(entries) != len(ledger_entry_ids):
            raise HTTPException(status_code=404, detail="Some entries not found or not authorized")
    
    # Create notification for admin
    from api.models.notification import Notification
    
    details = {
        "user_id": str(current_user.id),
        "user_email": current_user.email,
        "episode_id": str(episode_id) if episode_id else None,
        "ledger_entry_ids": ledger_entry_ids,
        "reason": reason,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    notification = Notification(
        user_id=current_user.id,
        type="refund_request",
        title="Credit Refund Request",
        body=f"User {current_user.email} requested refund for {len(ledger_entry_ids) if ledger_entry_ids else 'episode'} charges. Reason: {reason[:100]}. Details: {details}"
    )
    
    session.add(notification)
    session.commit()
    
    log.info(
        f"[billing-ledger] Refund request from user {current_user.id}: "
        f"episode={episode_id}, entries={ledger_entry_ids}, reason={reason[:50]}"
    )
    
    return {
        "success": True,
        "message": "Refund request submitted. Our team will review and respond within 24-48 hours."
    }


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
