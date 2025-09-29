from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlmodel import Session

from api.core.database import get_session
from api.models.user import User

from .deps import get_current_admin_user

try:  # pragma: no cover - optional dependency
    import stripe as stripe_lib
except Exception:  # pragma: no cover
    stripe_lib = None


router = APIRouter()


@router.get("/billing/overview", status_code=200)
def admin_billing_overview(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    del session, admin_user
    out: Dict[str, Any] = {
        "active_subscriptions": 0,
        "trialing": 0,
        "canceled_last_30d": 0,
        "trial_expiring_7d": 0,
        "gross_mrr_cents": None,
    }
    dash_url = os.getenv("STRIPE_DASHBOARD_URL")
    if dash_url:
        out["dashboard_url"] = dash_url

    if not stripe_lib or not (os.getenv("STRIPE_SECRET_KEY") or getattr(stripe_lib, "api_key", None)):
        return out

    try:
        if not getattr(stripe_lib, "api_key", None):
            stripe_lib.api_key = os.getenv("STRIPE_SECRET_KEY", "")
    except Exception:
        return out

    now = datetime.now(timezone.utc)
    since_30 = int((now - timedelta(days=30)).timestamp())
    in_7d = int((now + timedelta(days=7)).timestamp())

    try:
        active_count = 0
        monthly_total = 0.0
        try:
            subs = stripe_lib.Subscription.list(status="active", limit=100, expand=["data.items.data.price"])  # type: ignore
            for subscription in subs.auto_paging_iter():  # type: ignore[attr-defined]
                active_count += 1
                items = getattr(subscription, "items", {}).get("data", []) if hasattr(subscription, "items") else []
                for item in items:
                    price = getattr(item, "price", None)
                    qty = int(getattr(item, "quantity", 1) or 1)
                    unit = None
                    interval = None
                    if price:
                        unit = getattr(price, "unit_amount", None)
                        recurring = getattr(price, "recurring", None)
                        if recurring:
                            interval = getattr(recurring, "interval", None)
                    if unit is None or interval is None:
                        continue
                    amount = float(unit) * qty
                    if interval == "month":
                        monthly_total += amount
                    elif interval == "year":
                        monthly_total += amount / 12.0
        except Exception:
            pass

        out["active_subscriptions"] = int(active_count)
        out["gross_mrr_cents"] = int(round(monthly_total)) if monthly_total > 0 else 0 if active_count > 0 else None

        trialing = 0
        trial_expiring = 0
        try:
            trials = stripe_lib.Subscription.list(status="trialing", limit=100)
            for trial in trials.auto_paging_iter():  # type: ignore[attr-defined]
                trialing += 1
                try:
                    trial_end = int(getattr(trial, "trial_end", 0) or 0)
                    if trial_end and trial_end <= in_7d and trial_end >= int(now.timestamp()):
                        trial_expiring += 1
                except Exception:
                    continue
        except Exception:
            pass
        out["trialing"] = int(trialing)
        out["trial_expiring_7d"] = int(trial_expiring)

        canceled_30d = 0
        try:
            canceled = stripe_lib.Subscription.list(status="canceled", limit=100)
            for subscription in canceled.auto_paging_iter():  # type: ignore[attr-defined]
                try:
                    canceled_at = int(getattr(subscription, "canceled_at", 0) or 0)
                    if canceled_at and canceled_at >= since_30:
                        canceled_30d += 1
                except Exception:
                    continue
        except Exception:
            pass
        out["canceled_last_30d"] = int(canceled_30d)
    except Exception:
        return out

    return out


__all__ = ["router"]
