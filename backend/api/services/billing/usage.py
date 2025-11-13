from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict
from uuid import UUID

from typing import Any
from sqlmodel import select

from ...models.usage import ProcessingMinutesLedger, LedgerDirection, LedgerReason

log = logging.getLogger(__name__)


def _validate_minutes(minutes: int) -> None:
    if not isinstance(minutes, int) or minutes <= 0:
        raise ValueError("minutes must be a positive integer")


def post_debit(
    session: Any,
    user_id: UUID,
    minutes: int,
    episode_id: Optional[UUID],
    *,
    reason: str = "PROCESS_AUDIO",
    correlation_id: Optional[str] = None,
    notes: str = "",
) -> Optional[ProcessingMinutesLedger]:
    """Create a DEBIT entry. If a correlation_id is supplied and unique index is hit,
    log and return None (idempotent no-op)."""
    _validate_minutes(minutes)
    try:
        # Set credits = minutes * 1.0 for backward compatibility (legacy 1 min = 1 credit)
        # New code should use credits.charge_credits() instead of this function
        credits_value = float(minutes) * 1.0
        
        rec = ProcessingMinutesLedger(
            user_id=user_id,
            episode_id=episode_id,
            minutes=int(minutes),
            credits=credits_value,  # Set credits for backward compatibility
            direction=LedgerDirection.DEBIT,
            reason=LedgerReason(reason) if isinstance(reason, str) else reason,
            correlation_id=correlation_id,
            notes=notes or None,
        )
        session.add(rec)
        session.commit()
        session.refresh(rec)
        log.info("usage.debit posted", extra={
            "user_id": str(user_id),
            "episode_id": str(episode_id) if episode_id else None,
            "minutes": minutes,
            "correlation_id": correlation_id,
            "reason": rec.reason.value,
        })
        return rec
    except Exception as e:
        # Detect uniqueness/idempotency violation
        msg = str(e)
        if "uq_pml_debit_corr" in msg or "UNIQUE constraint failed" in msg:
            log.info("usage.debit duplicate correlation id; treating as no-op", extra={
                "user_id": str(user_id),
                "episode_id": str(episode_id) if episode_id else None,
                "minutes": minutes,
                "correlation_id": correlation_id,
            })
            session.rollback()
            return None
        session.rollback()
        raise


def post_credit(
    session: Any,
    user_id: UUID,
    minutes: int,
    episode_id: Optional[UUID],
    *,
    reason: str = "REFUND_ERROR",
    correlation_id: Optional[str] = None,
    notes: str = "",
) -> ProcessingMinutesLedger:
    _validate_minutes(minutes)
    # Set credits = minutes * 1.0 for backward compatibility (legacy 1 min = 1 credit)
    # New code should use credits.refund_credits() instead of this function
    credits_value = float(minutes) * 1.0
    
    rec = ProcessingMinutesLedger(
        user_id=user_id,
        episode_id=episode_id,
        minutes=int(minutes),
        credits=credits_value,  # Set credits for backward compatibility
        direction=LedgerDirection.CREDIT,
        reason=LedgerReason(reason) if isinstance(reason, str) else reason,
        correlation_id=correlation_id,
        notes=notes or None,
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    log.info("usage.credit posted", extra={
        "user_id": str(user_id),
        "episode_id": str(episode_id) if episode_id else None,
        "minutes": minutes,
        "correlation_id": correlation_id,
        "reason": rec.reason.value,
    })
    return rec


def balance_minutes(session: Any, user_id: UUID) -> int:
    rows = session.exec(select(ProcessingMinutesLedger).where(ProcessingMinutesLedger.user_id == user_id)).all()
    deb = sum(r.minutes for r in rows if r.direction == LedgerDirection.DEBIT)
    cred = sum(r.minutes for r in rows if r.direction == LedgerDirection.CREDIT)
    return cred - deb


def _normalize_to_utc(dt: datetime) -> datetime:
    """Ensure the datetime has timezone info and is expressed in UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def month_minutes_used(
    session: Any,
    user_id: UUID,
    period_start: datetime,
    period_end: datetime,
) -> int:
    norm_start = _normalize_to_utc(period_start)
    norm_end = _normalize_to_utc(period_end)
    q = (
        select(ProcessingMinutesLedger)
        .where(ProcessingMinutesLedger.user_id == user_id)
    )
    rows = session.exec(q).all()
    used = 0
    for r in rows:
        ts = getattr(r, "created_at", None)
        if ts is None:
            continue
        ts_utc = _normalize_to_utc(ts)
        if ts_utc < norm_start or ts_utc > norm_end:
            continue
        if r.direction == LedgerDirection.DEBIT:
            used += int(r.minutes)
        else:
            used -= int(r.minutes)
    return max(0, used)


def user_ledger(session: Any, user_id: UUID, limit: int = 100, offset: int = 0) -> List[Dict]:
    # Order by created_at descending. Using text() to avoid mypy confusion around datetime columns.
    from sqlalchemy import text as _sa_text
    q = (
        select(ProcessingMinutesLedger)
        .where(ProcessingMinutesLedger.user_id == user_id)
        .order_by(_sa_text("created_at DESC"))
    )
    rows = session.exec(q).all()
    sliced = rows[offset: offset + limit]
    items: List[Dict] = []
    for r in sliced:
        items.append({
            "id": r.id,
            "episode_id": str(r.episode_id) if r.episode_id else None,
            "minutes": int(r.minutes),
            "direction": r.direction.value,
            "reason": r.reason.value,
            "correlation_id": r.correlation_id,
            "notes": r.notes,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return items


def month_credits_breakdown(
    session: Any,
    user_id: UUID,
    period_start: datetime,
    period_end: datetime,
) -> Dict[str, float]:
    """
    Get breakdown of credits used this month by action type.
    
    Returns dict with keys: total, tts_generation, transcription, assembly, storage, auphonic_processing, ai_metadata
    """
    norm_start = _normalize_to_utc(period_start)
    norm_end = _normalize_to_utc(period_end)
    
    q = (
        select(ProcessingMinutesLedger)
        .where(ProcessingMinutesLedger.user_id == user_id)
    )
    rows = session.exec(q).all()
    
    breakdown: Dict[str, float] = {
        'total': 0.0,
        'tts_generation': 0.0,
        'transcription': 0.0,
        'assembly': 0.0,
        'storage': 0.0,
        'auphonic_processing': 0.0,
        'ai_metadata': 0.0,
    }
    
    for r in rows:
        ts = getattr(r, "created_at", None)
        if ts is None:
            continue
        ts_utc = _normalize_to_utc(ts)
        if ts_utc < norm_start or ts_utc > norm_end:
            continue
        
        # Get credits value (fallback to minutes * 1.0 if credits column not yet populated)
        credits_amount = getattr(r, 'credits', None)
        if credits_amount is None:
            # Legacy records without credits field (1 minute = 1 credit)
            credits_amount = r.minutes * 1.0
        
        # DEBIT entries add to usage, CREDIT entries (refunds) subtract from usage
        if r.direction == LedgerDirection.DEBIT:
            multiplier = 1.0
        elif r.direction == LedgerDirection.CREDIT:
            # Refunds reduce usage, but only if they're refunds of charges from this month
            # For now, we'll subtract all CREDIT entries in the period (refunds reduce usage)
            multiplier = -1.0
        else:
            continue
        
        # Map reason to category
        reason_str = r.reason.value if hasattr(r.reason, 'value') else str(r.reason)
        
        # For refunds, we need to map them back to the original category if possible
        # For REFUND_ERROR, we'll subtract from total but not from specific categories
        # (since we don't know which category the original charge was)
        if reason_str == 'REFUND_ERROR' or reason_str == 'MANUAL_ADJUST':
            # Refunds reduce total usage but we can't attribute to specific categories
            breakdown['total'] += credits_amount * multiplier
        elif reason_str == 'TTS_GENERATION':
            breakdown['tts_generation'] += credits_amount * multiplier
            breakdown['total'] += credits_amount * multiplier
        elif reason_str == 'TRANSCRIPTION':
            breakdown['transcription'] += credits_amount * multiplier
            breakdown['total'] += credits_amount * multiplier
        elif reason_str == 'ASSEMBLY':
            breakdown['assembly'] += credits_amount * multiplier
            breakdown['total'] += credits_amount * multiplier
        elif reason_str == 'STORAGE':
            breakdown['storage'] += credits_amount * multiplier
            breakdown['total'] += credits_amount * multiplier
        elif reason_str == 'AUPHONIC_PROCESSING':
            breakdown['auphonic_processing'] += credits_amount * multiplier
            breakdown['total'] += credits_amount * multiplier
        elif reason_str == 'AI_METADATA_GENERATION':
            breakdown['ai_metadata'] += credits_amount * multiplier
            breakdown['total'] += credits_amount * multiplier
        else:
            # Other reasons (like PROCESS_AUDIO) just add to total
            breakdown['total'] += credits_amount * multiplier
    
    return breakdown
