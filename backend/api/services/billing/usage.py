from __future__ import annotations

import logging
from datetime import datetime
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


def month_minutes_used(
    session: Any,
    user_id: UUID,
    period_start: datetime,
    period_end: datetime,
) -> int:
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
        if ts < period_start or ts > period_end:
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
