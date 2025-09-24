from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import UUID

from sqlmodel import select

from ..models.usage import TTSUsage
from ..models.podcast import MediaCategory


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _day_window(now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    now = now or _utc_now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def estimate_seconds_from_chars(text: str, speaking_rate: float = 1.0) -> float:
    """
    Lightweight estimate of audio seconds from characters.
    Baseline: ~14 chars/sec at 1.0x speaking, scale inversely with speaking_rate.
    """
    chars = max(0, len((text or "").strip()))
    baseline_cps = 14.0
    rate = speaking_rate if speaking_rate and speaking_rate > 0 else 1.0
    seconds = chars / (baseline_cps * rate)
    # Clamp to minimum 1s for non-empty text to avoid divide-by-zero downstream
    return float(max(1.0 if chars > 0 else 0.0, seconds))


@dataclass
class DailyQuota:
    free_seconds_per_type: int = 60
    free_generations_per_type: int = 3
    spam_window_seconds: int = 30


def daily_usage(session, user_id: UUID, category: MediaCategory) -> tuple[float, int]:
    start, end = _day_window()
    q = (
        select(TTSUsage)
        .where(TTSUsage.user_id == user_id)
        .where(TTSUsage.category == category)
        .where(TTSUsage.created_at >= start)
        .where(TTSUsage.created_at < end)
    )
    rows = session.exec(q).all()
    seconds = 0.0
    count = 0
    for r in rows:
        count += 1
        sec = r.seconds_actual if r.seconds_actual is not None else r.seconds_estimated
        seconds += float(sec or 0.0)
    return seconds, count


def last_created_seconds_ago(session, user_id: UUID, category: MediaCategory) -> Optional[float]:
    from sqlalchemy import text as _sa_text
    q = (
        select(TTSUsage)
        .where(TTSUsage.user_id == user_id)
        .where(TTSUsage.category == category)
        .order_by(_sa_text("created_at DESC"))
    )
    row = session.exec(q).first()
    if not row:
        return None
    delta = _utc_now() - (row.created_at.replace(tzinfo=timezone.utc) if row.created_at.tzinfo is None else row.created_at)
    return max(0.0, delta.total_seconds())


def precheck(
    session,
    user_id: UUID,
    category: MediaCategory,
    *,
    text: str,
    speaking_rate: float,
    quota: DailyQuota = DailyQuota(),
) -> dict:
    """
    Compute whether a generation should be free, warned (may incur minutes), or blocked (spam duplicate).
    Returns a dict the frontend can use to show messaging without exposing policy numbers publicly.
    """
    est_s = estimate_seconds_from_chars(text, speaking_rate)
    used_s, used_count = daily_usage(session, user_id, category)
    last_age = last_created_seconds_ago(session, user_id, category)

    # Anti-spam: if last was within spam window, advise block
    spam_block = last_age is not None and last_age < quota.spam_window_seconds

    # Free allowance logic
    free_left_s = max(0.0, float(quota.free_seconds_per_type) - used_s)
    free_left_generations = max(0, int(quota.free_generations_per_type - used_count))

    # 120% grace on remaining seconds
    threshold_s = free_left_s * 1.2
    will_warn_cost = est_s > threshold_s or free_left_generations <= 0

    return {
        "ok": not spam_block,
        "spam_block": bool(spam_block),
        "estimate_seconds": round(est_s, 2),
        "free_seconds_left": round(free_left_s, 2),
        "free_generations_left": int(free_left_generations),
        "warn_may_cost": bool(will_warn_cost),
    }


def record_request(
    session,
    user_id: UUID,
    category: MediaCategory,
    *,
    text: str,
    speaking_rate: float,
) -> TTSUsage:
    est_s = estimate_seconds_from_chars(text, speaking_rate)
    rec = TTSUsage(
        user_id=user_id,
        category=category,
        characters=len((text or "").strip()),
        seconds_estimated=float(est_s),
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def finalize_actual_seconds(session, usage_id: int, seconds_actual: float) -> None:
    rec = session.get(TTSUsage, usage_id)
    if not rec:
        return
    rec.seconds_actual = float(max(0.0, seconds_actual))
    session.add(rec)
    session.commit()
