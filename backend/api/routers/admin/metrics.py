from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import Session, select

from api.core.database import get_session
from api.models.podcast import Episode, Podcast, PodcastTemplate
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


__all__ = ["router"]
