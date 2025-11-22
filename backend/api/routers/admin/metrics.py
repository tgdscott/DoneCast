from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import Session, select

from api.core.database import get_session
from api.models.podcast import Episode, EpisodeStatus, Podcast, PodcastTemplate
from api.models.user import User
from api.routers.episodes.common import is_published_condition

from .deps import get_current_admin_user

try:  # pragma: no cover - optional Stripe dependency
    import stripe as stripe_lib
except Exception:  # pragma: no cover
    stripe_lib = None

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/summary", status_code=200)
def admin_summary(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, int]:
    """Simple platform summary for the admin dashboard MVP."""
    del admin_user
    user_count = session.exec(select(func.count(User.id))).one()
    podcast_count = session.exec(select(func.count(Podcast.id))).one()
    template_count = session.exec(select(func.count(PodcastTemplate.id))).one()
    episode_count = session.exec(select(func.count(Episode.id))).one()
    published_count = session.exec(
        select(func.count(Episode.id)).where(is_published_condition())
    ).one()
    return {
        "users": user_count,
        "podcasts": podcast_count,
        "templates": template_count,
        "episodes": episode_count,
        "published_episodes": published_count,
    }


def _date_range_30d() -> List[str]:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=29)
    return [(start + timedelta(days=i)).isoformat() for i in range(30)]


@router.get("/metrics", status_code=200)
def admin_metrics(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Operational metrics for the last 30 days. Fast and resilient; Stripe is optional."""
    del admin_user
    days = _date_range_30d()
    since_dt = datetime.strptime(days[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)

    signup_map: Dict[str, int] = {d: 0 for d in days}
    signup_users = session.exec(select(User).where(User.created_at >= since_dt)).all()
    for user in signup_users:
        try:
            created = user.created_at.date().isoformat()
        except Exception:
            continue
        if created in signup_map:
            signup_map[created] += 1

    daily_signups_30d = [{"date": day, "count": signup_map[day]} for day in days]

    active_sets: Dict[str, set] = {d: set() for d in days}
    episodes = session.exec(
        select(Episode).where((Episode.processed_at != None) & (Episode.processed_at >= since_dt))  # noqa: E711
    ).all()
    for ep in episodes:
        try:
            processed = ep.processed_at.date().isoformat()
        except Exception:
            continue
        if processed in active_sets:
            active_sets[processed].add(ep.user_id)

    daily_active_users_30d = [{"date": day, "count": len(active_sets[day])} for day in days]

    mrr_cents: Optional[int] = None
    arr_cents: Optional[int] = None
    revenue_30d_cents: Optional[int] = None

    try:
        if stripe_lib and (os.getenv("STRIPE_SECRET_KEY") or getattr(stripe_lib, "api_key", None)):
            if not getattr(stripe_lib, "api_key", None):
                stripe_lib.api_key = os.getenv("STRIPE_SECRET_KEY", "")

            monthly_total = 0.0
            try:
                subs = stripe_lib.Subscription.list(status="active", limit=100, expand=["data.items.data.price"])  # type: ignore
                for subscription in subs.auto_paging_iter():  # type: ignore[attr-defined]
                    items = getattr(subscription, "items", {}).get("data", []) if hasattr(subscription, "items") else []
                    for item in items:
                        price = getattr(item, "price", None)
                        quantity = int(getattr(item, "quantity", 1) or 1)
                        unit = None
                        interval = None
                        if price:
                            unit = getattr(price, "unit_amount", None)
                            recurring = getattr(price, "recurring", None)
                            if recurring:
                                interval = getattr(recurring, "interval", None)
                        if unit is None or interval is None:
                            continue
                        amount = float(unit) * quantity
                        if interval == "month":
                            monthly_total += amount
                        elif interval == "year":
                            monthly_total += amount / 12.0
                mrr_cents = int(round(monthly_total))
                arr_cents = int(round(monthly_total * 12.0))
            except Exception:
                mrr_cents = None
                arr_cents = None

            try:
                since_ts = int(since_dt.timestamp())
                net = 0
                charges = stripe_lib.Charge.list(created={"gte": since_ts}, limit=100)
                for charge in charges.auto_paging_iter():  # type: ignore[attr-defined]
                    if getattr(charge, "status", "") == "succeeded":
                        amount = int(getattr(charge, "amount", 0) or 0)
                        refunded = int(getattr(charge, "amount_refunded", 0) or 0)
                        net += max(amount - refunded, 0)
                revenue_30d_cents = int(net)
            except Exception:
                revenue_30d_cents = None
    except Exception:
        mrr_cents = mrr_cents if mrr_cents is not None else None
        arr_cents = arr_cents if arr_cents is not None else None
        revenue_30d_cents = revenue_30d_cents if revenue_30d_cents is not None else None

    return {
        "daily_signups_30d": daily_signups_30d,
        "daily_active_users_30d": daily_active_users_30d,
        "mrr_cents": mrr_cents,
        "arr_cents": arr_cents,
        "revenue_30d_cents": revenue_30d_cents,
    }


@router.get("/episodes-today", status_code=200)
def episodes_today(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, int]:
    """Get episodes created today, broken down by published vs drafts."""
    del admin_user
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # Count all episodes created today
    total_today = session.exec(
        select(func.count(Episode.id)).where(
            Episode.created_at >= today_start,
            Episode.created_at < today_end
        )
    ).one()

    # Count published episodes created today
    published_today = session.exec(
        select(func.count(Episode.id)).where(
            Episode.created_at >= today_start,
            Episode.created_at < today_end,
            is_published_condition()
        )
    ).one()

    drafts_today = total_today - published_today

    return {
        "total": total_today,
        "published": published_today,
        "drafts": drafts_today,
    }


@router.get("/recent-activity", status_code=200)
def recent_activity(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Get recent platform activity (user signups, episode publications, etc.)."""
    del admin_user
    now = datetime.now(timezone.utc)
    activities = []

    # Recent user signups (last 24 hours)
    one_day_ago = now - timedelta(days=1)
    recent_users = session.exec(
        select(User).where(
            User.created_at >= one_day_ago
        ).order_by(User.created_at.desc()).limit(limit)
    ).all()

    for user in recent_users:
        hours_ago = (now - user.created_at).total_seconds() / 3600
        if hours_ago < 1:
            time_str = f"{int(hours_ago * 60)} minutes ago"
        elif hours_ago < 24:
            time_str = f"{int(hours_ago)} hours ago"
        else:
            time_str = f"{int(hours_ago / 24)} days ago"

        activities.append({
            "type": "user_signup",
            "title": "New user registration",
            "description": f"{user.email or 'New user'} signed up",
            "time": time_str,
            "timestamp": user.created_at.isoformat(),
        })

    # Recent episode publications (last 24 hours)
    recent_episodes = session.exec(
        select(Episode).where(
            Episode.publish_at >= one_day_ago,
            Episode.publish_at <= now,
            is_published_condition()
        ).order_by(Episode.publish_at.desc()).limit(limit)
    ).all()

    for episode in recent_episodes:
        hours_ago = (now - episode.publish_at).total_seconds() / 3600
        if hours_ago < 1:
            time_str = f"{int(hours_ago * 60)} minutes ago"
        elif hours_ago < 24:
            time_str = f"{int(hours_ago)} hours ago"
        else:
            time_str = f"{int(hours_ago / 24)} days ago"

        activities.append({
            "type": "episode_published",
            "title": "Episode published",
            "description": f'"{episode.title or "Untitled"}" was published',
            "time": time_str,
            "timestamp": episode.publish_at.isoformat(),
        })

    # Sort by timestamp and return most recent
    activities.sort(key=lambda x: x["timestamp"], reverse=True)
    return activities[:limit]


@router.get("/system-health", status_code=200)
def system_health(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Get system health metrics."""
    del admin_user
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    # Calculate uptime percentage (simplified - based on successful operations)
    # In a real system, this would come from monitoring/observability tools
    total_episodes_30d = session.exec(
        select(func.count(Episode.id)).where(
            Episode.created_at >= thirty_days_ago
        )
    ).one()

    failed_episodes_30d = session.exec(
        select(func.count(Episode.id)).where(
            Episode.created_at >= thirty_days_ago,
            Episode.status == EpisodeStatus.error
        )
    ).one()

    success_rate = 0.0
    if total_episodes_30d > 0:
        success_rate = ((total_episodes_30d - failed_episodes_30d) / total_episodes_30d) * 100

    # For now, return a simplified health status
    # In production, this would integrate with actual monitoring systems
    return {
        "uptime_percentage": min(99.9, max(95.0, success_rate)),  # Clamp between 95-99.9%
        "status": "operational" if success_rate > 95 else "degraded",
    }


@router.get("/growth-metrics", status_code=200)
def growth_metrics(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Calculate month-over-month growth percentages."""
    del admin_user
    now = datetime.now(timezone.utc)
    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)
    last_month_end = this_month_start

    # Active users this month vs last month
    dau_this_month = session.exec(
        select(func.count(func.distinct(Episode.user_id))).where(
            Episode.processed_at >= this_month_start,
            Episode.processed_at < now
        )
    ).one()

    dau_last_month = session.exec(
        select(func.count(func.distinct(Episode.user_id))).where(
            Episode.processed_at >= last_month_start,
            Episode.processed_at < last_month_end
        )
    ).one()

    active_users_change = 0.0
    if dau_last_month > 0:
        active_users_change = ((dau_this_month - dau_last_month) / dau_last_month) * 100

    # New signups this month vs last month
    signups_this_month = session.exec(
        select(func.count(User.id)).where(
            User.created_at >= this_month_start,
            User.created_at < now
        )
    ).one()

    signups_last_month = session.exec(
        select(func.count(User.id)).where(
            User.created_at >= last_month_start,
            User.created_at < last_month_end
        )
    ).one()

    signups_change = 0.0
    if signups_last_month > 0:
        signups_change = ((signups_this_month - signups_last_month) / signups_last_month) * 100

    # Episodes published this month vs last month
    episodes_this_month = session.exec(
        select(func.count(Episode.id)).where(
            Episode.publish_at >= this_month_start,
            Episode.publish_at < now,
            is_published_condition()
        )
    ).one()

    episodes_last_month = session.exec(
        select(func.count(Episode.id)).where(
            Episode.publish_at >= last_month_start,
            Episode.publish_at < last_month_end,
            is_published_condition()
        )
    ).one()

    episodes_change = 0.0
    if episodes_last_month > 0:
        episodes_change = ((episodes_this_month - episodes_last_month) / episodes_last_month) * 100

    # Revenue change (if available)
    revenue_change = None
    try:
        if stripe_lib and (os.getenv("STRIPE_SECRET_KEY") or getattr(stripe_lib, "api_key", None)):
            if not getattr(stripe_lib, "api_key", None):
                stripe_lib.api_key = os.getenv("STRIPE_SECRET_KEY", "")

            this_month_ts = int(this_month_start.timestamp())
            last_month_ts = int(last_month_start.timestamp())
            last_month_end_ts = int(last_month_end.timestamp())

            this_month_revenue = 0
            charges_this = stripe_lib.Charge.list(created={"gte": this_month_ts}, limit=100)
            for charge in charges_this.auto_paging_iter():
                if getattr(charge, "status", "") == "succeeded":
                    amount = int(getattr(charge, "amount", 0) or 0)
                    refunded = int(getattr(charge, "amount_refunded", 0) or 0)
                    this_month_revenue += max(amount - refunded, 0)

            last_month_revenue = 0
            charges_last = stripe_lib.Charge.list(
                created={"gte": last_month_ts, "lt": last_month_end_ts},
                limit=100
            )
            for charge in charges_last.auto_paging_iter():
                if getattr(charge, "status", "") == "succeeded":
                    amount = int(getattr(charge, "amount", 0) or 0)
                    refunded = int(getattr(charge, "amount_refunded", 0) or 0)
                    last_month_revenue += max(amount - refunded, 0)

            if last_month_revenue > 0:
                revenue_change = ((this_month_revenue - last_month_revenue) / last_month_revenue) * 100
    except Exception:
        revenue_change = None

    return {
        "active_users_change": round(active_users_change, 1),
        "signups_change": round(signups_change, 1),
        "episodes_change": round(episodes_change, 1),
        "revenue_change": round(revenue_change, 1) if revenue_change is not None else None,
    }


__all__ = ["router"]
