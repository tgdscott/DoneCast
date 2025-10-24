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
        rec = ProcessingMinutesLedger(
            user_id=user_id,
            episode_id=episode_id,
            minutes=int(minutes),
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
    rec = ProcessingMinutesLedger(
        user_id=user_id,
        episode_id=episode_id,
        minutes=int(minutes),
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
    
    Returns dict with keys: total, tts_generation, transcription, assembly, storage, auphonic_processing
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
    }
    
    for r in rows:
        ts = getattr(r, "created_at", None)
        if ts is None:
            continue
        ts_utc = _normalize_to_utc(ts)
        if ts_utc < norm_start or ts_utc > norm_end:
            continue
        
        # Only count DEBIT entries (charges)
        if r.direction != LedgerDirection.DEBIT:
            continue
        
        # Get credits value (fallback to minutes * 1.5 if credits column not yet populated)
        credits_used = getattr(r, 'credits', None)
        if credits_used is None:
            # Legacy records without credits field
            credits_used = r.minutes * 1.5
        
        # Map reason to category
        reason_str = r.reason.value if hasattr(r.reason, 'value') else str(r.reason)
        
        if reason_str == 'TTS_GENERATION':
            breakdown['tts_generation'] += credits_used
        elif reason_str == 'TRANSCRIPTION':
            breakdown['transcription'] += credits_used
        elif reason_str == 'ASSEMBLY':
            breakdown['assembly'] += credits_used
        elif reason_str == 'STORAGE':
            breakdown['storage'] += credits_used
        elif reason_str == 'AUPHONIC_PROCESSING':
            breakdown['auphonic_processing'] += credits_used
        
        breakdown['total'] += credits_used
    
    return breakdown
