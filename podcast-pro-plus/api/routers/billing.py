from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session
from ..core.database import get_session
from ..models.user import User
from api.core.auth import get_current_user
import os, stripe
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from ..core.constants import TIER_LIMITS
from ..core import crud
from uuid import UUID
from sqlmodel import select
from sqlalchemy import func
from ..services.billing import usage as usage_svc
from ..core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter(prefix="/billing", tags=["Billing"])

PRICE_MAP = {
    "pro": {
        "monthly": os.getenv("PRICE_PRO_MONTHLY", "price_pro_monthly_placeholder"),
        "annual": os.getenv("PRICE_PRO_ANNUAL", "price_pro_annual_placeholder"),
    },
    # Renamed from 'premium' to 'creator'; fall back to legacy env vars if new ones missing
    "creator": {
        "monthly": (
            os.getenv("PRICE_CREATOR_MONTHLY")
            or os.getenv("PRICE_PREMIUM_MONTHLY")
            or "price_creator_monthly_placeholder"
        ),
        "annual": (
            os.getenv("PRICE_CREATOR_ANNUAL")
            or os.getenv("PRICE_PREMIUM_ANNUAL")
            or "price_creator_annual_placeholder"
        ),
    },
}

# --- Price ID resolution (allows friendlier lookup keys) ---------------------
_PRICE_CACHE: dict[str,str] = {}

def _resolve_price_id(raw: str) -> str:
    """Return a real Stripe price ID. If 'raw' already looks like price_*, return it.
    Otherwise treat it as a lookup_key and query Stripe once, caching result.
    """
    if not raw:
        raise HTTPException(status_code=500, detail="Price not configured")
    if raw.startswith("price_"):
        return raw
    # cached lookup
    if raw in _PRICE_CACHE:
        return _PRICE_CACHE[raw]
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured for lookup key resolution")
    try:
        found = stripe.Price.list(limit=1, lookup_keys=[raw])
        data = getattr(found, 'data', []) if found else []
        if not data:
            raise HTTPException(status_code=500, detail=f"Stripe price lookup key '{raw}' not found")
        price_id = data[0]['id']
        _PRICE_CACHE[raw] = price_id
        return price_id
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stripe lookup failed: {e}")

class CheckoutRequest(BaseModel):
    plan_key: str
    billing_cycle: str = "monthly"  # monthly | annual
    # Base path (no query). We'll append ?checkout=success&session_id=... to avoid double '?'.
    success_path: str = "/billing"
    cancel_path: str = "/billing/cancel"

class CheckoutResponse(BaseModel):
    url: str

class PortalResponse(BaseModel):
    url: str

class SubscriptionStatus(BaseModel):
    plan_key: str
    status: str
    current_period_end: str | None = None
    cancel_at_period_end: bool | None = None
    max_episodes_month: int | None = None
    episodes_used_this_month: int | None = None
    episodes_remaining_this_month: int | None = None
    applied_upgrade_credit: float | None = None

def _ensure_customer(user: User, session: Session):
    if not getattr(user, 'stripe_customer_id', None):
        cust = stripe.Customer.create(email=user.email, metadata={"user_id": str(user.id)})
        user.stripe_customer_id = cust.id
        session.add(user)
        session.commit()
        return cust.id
    return user.stripe_customer_id

@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    request: Request,
    req: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    # Request must not be Optional; FastAPI special-cases Request only when non-optional.
    if req.plan_key not in PRICE_MAP:
        raise HTTPException(status_code=400, detail="Unknown plan")
    cycle_prices = PRICE_MAP[req.plan_key]
    if req.billing_cycle not in cycle_prices:
        raise HTTPException(status_code=400, detail="Invalid billing cycle")
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    # IMPORTANT: Use 127.0.0.1 (not localhost) so it matches Google OAuth / stored localStorage origin
    # Prefer caller origin so we preserve localhost vs 127.0.0.1 consistency with their existing localStorage
    origin = None
    try:
        origin = request.headers.get('origin')
    except Exception:
        origin = None
    if origin and origin.startswith("http"):
        base_url = origin.rstrip('/')
    else:
        base_url = os.getenv("APP_BASE_URL", "https://app.getpodcastplus.com")
    price_id = _resolve_price_id(cycle_prices[req.billing_cycle])
    try:
        customer_id = _ensure_customer(current_user, session)
        # Build success URL with proper query parameters (avoid legacy double '?')
        success_qs = f"?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"

        metadata = {"user_id": str(current_user.id), "plan_key": req.plan_key, "cycle": req.billing_cycle}
        subscription_data = {"metadata": metadata}
        discounts = []

        # --- Upgrade / Proration Logic ---
        prior_tier = getattr(current_user, 'tier', 'free') or 'free'
        prior_exp = getattr(current_user, 'subscription_expires_at', None)
        is_free_to_paid = (prior_tier == 'free' and req.plan_key != 'free')
        same_plan_cycle_change = (prior_tier == req.plan_key and req.billing_cycle == 'annual' and prior_exp is not None)
        is_plan_upgrade = (prior_tier != 'free' and prior_tier != req.plan_key)
        needs_proration = (same_plan_cycle_change or is_plan_upgrade) and (prior_exp is not None)
        if needs_proration:
            try:
                today = datetime.utcnow().date()
                remaining_days = (prior_exp.date() - today).days if prior_exp else 0
                if remaining_days < 0:
                    remaining_days = 0
                remaining_total_days = (prior_exp.date() - today).days if prior_exp else 0
                prior_cycle = 'annual' if remaining_total_days > 200 else 'monthly'
                daily_rate = Decimal('1.00') if prior_cycle == 'monthly' else Decimal('0.8333333')
                credit = (daily_rate * Decimal(remaining_days)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                # Resolve new price amount to cap credit
                try:
                    price_obj = stripe.Price.retrieve(price_id)
                    unit_amount = Decimal(price_obj['unit_amount']) / Decimal(100)
                except Exception:
                    unit_amount = Decimal('0')
                # Retrieve previous active subscription price for stronger cap (old price - 1)
                prev_sub = crud.get_active_subscription_for_user(session, current_user.id)
                if prev_sub:
                    try:
                        prev_price_obj = stripe.Price.retrieve(prev_sub.price_id)
                        prev_amount = Decimal(prev_price_obj['unit_amount']) / Decimal(100)
                        prev_cap = prev_amount - Decimal('1.00')
                        if prev_cap < 0:
                            prev_cap = Decimal('0')
                        if credit > prev_cap:
                            credit = prev_cap
                    except Exception:
                        pass  # non-fatal
                if credit > unit_amount:
                    credit = unit_amount
                if credit > 0:
                    coupon = stripe.Coupon.create(
                        name="Prorated credit for previous plan",
                        amount_off=int((credit * 100).to_integral_value(rounding=ROUND_HALF_UP)),
                        currency='usd',
                        duration='once',
                        metadata={"source": "upgrade_proration", "user_id": str(current_user.id), "prior_tier": prior_tier, "prorated":"1"}
                    )
                    discounts = [{"coupon": coupon.id}]
                    metadata['upgrade_prorated'] = '1'
            except Exception as e:  # pragma: no cover
                metadata['proration_error'] = str(e)[:150]
        if same_plan_cycle_change:
            metadata['cycle_change'] = '1'
        if is_plan_upgrade:
            metadata['plan_upgrade'] = '1'
        if is_free_to_paid:
            metadata['first_paid'] = '1'

        params = dict(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{base_url}{req.success_path}{success_qs}" if '?' not in req.success_path else f"{base_url}{req.success_path}&checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}{req.cancel_path}",
            customer=customer_id if customer_id else None,
            subscription_data=subscription_data,
            metadata=metadata,
        )
        if discounts:
            params['discounts'] = discounts
        else:
            # Only allow promotion codes if we are not already applying a discount coupon
            params['allow_promotion_codes'] = True  # type: ignore[assignment]
        checkout = stripe.checkout.Session.create(**params)  # type: ignore
        chk_url = getattr(checkout, 'url', None)
        if not chk_url:
            raise HTTPException(status_code=502, detail="Stripe did not return a checkout URL")
        return CheckoutResponse(url=str(chk_url))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stripe error: {e}")

class PortalRequest(BaseModel):
    return_path: str = "/billing"

@router.post("/portal", response_model=PortalResponse)
async def create_billing_portal(req: PortalRequest, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    base_url = os.getenv("APP_BASE_URL", "https://app.getpodcastplus.com")
    customer_id = getattr(current_user, 'stripe_customer_id', None)
    if not customer_id:
        customer_id = _ensure_customer(current_user, session)
    try:
        portal_session = stripe.billing_portal.Session.create(customer=str(customer_id), return_url=f"{base_url}{req.return_path}")  # type: ignore[arg-type]
        return PortalResponse(url=str(getattr(portal_session, 'url', '')))
    except Exception as e:
        msg = str(e)
        if "No configuration provided" in msg or "default configuration" in msg:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Stripe Customer Portal not initialized in test mode. Visit "
                    "https://dashboard.stripe.com/test/settings/billing/portal, select products/prices, and click 'Save changes' once to create the default configuration."
                ),
            )
        raise HTTPException(status_code=500, detail=f"Stripe error: {msg}")

def _episodes_created_this_month(session: Session, user_id) -> int:
    from datetime import datetime, timezone
    from calendar import monthrange  # noqa: F401 (future use for resetting logic)
    from ..models.podcast import Episode
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    # created_at may not exist on very old rows; filter defensively
    try:
        return session.exec(
            select(func.count(Episode.id))
            .where(Episode.user_id == user_id)
            .where(Episode.created_at >= start)
        ).one()
    except Exception:
        return session.exec(
            select(func.count(Episode.id))
            .where(Episode.user_id == user_id)
        ).one()


@router.get("/subscription", response_model=SubscriptionStatus)
async def get_subscription(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    tier = getattr(current_user, 'tier', 'free') or 'free'
    limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
    max_eps = limits.get('max_episodes_month')
    used = _episodes_created_this_month(session, current_user.id) if max_eps is not None else None
    remaining = (max_eps - used) if (max_eps is not None and used is not None) else None
    # Derive current_period_end from user.subscription_expires_at (renewal date) if present
    cpe = None
    try:
        exp = getattr(current_user, 'subscription_expires_at', None)
        if exp:
            cpe = exp.isoformat()
    except Exception:
        cpe = None
    return SubscriptionStatus(
        plan_key=tier,
        status="active" if tier != 'free' else 'free',
        current_period_end=cpe,
        max_episodes_month=max_eps,
        episodes_used_this_month=used,
        episodes_remaining_this_month=remaining,
    )

class CheckoutResult(BaseModel):
    plan_key: str
    billing_cycle: str | None = None
    renewal_date: str | None = None
    applied_credit: float | None = None
    flags: dict[str, bool] = {}

@router.get("/checkout_result", response_model=CheckoutResult)
async def get_checkout_result(session_id: str, current_user: User = Depends(get_current_user)):
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    try:
        cs = stripe.checkout.Session.retrieve(session_id, expand=['subscription'])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid session: {e}")
    md = cs.get('metadata') or {}
    plan_key = md.get('plan_key') or getattr(current_user, 'tier', 'free')
    cycle = md.get('cycle')
    flags = {k: (md.get(k)=='1') for k in ('plan_upgrade','cycle_change','first_paid','upgrade_prorated')}
    applied_credit = None
    try:
        disc = cs.get('total_details', {}).get('amount_discount')
        if disc:
            applied_credit = float(disc) / 100.0
        else:
            # Fallback: inspect discounts on subscription
            sub = cs.get('subscription') or {}
            if sub and isinstance(sub, dict):
                discounts = sub.get('discounts') or []
                for d in discounts:
                    coupon = d.get('coupon') or {}
                    amt = coupon.get('amount_off')
                    if amt:
                        applied_credit = float(amt) / 100.0
                        break
    except Exception:
        pass
    renewal = None
    try:
        exp = getattr(current_user, 'subscription_expires_at', None)
        if exp:
            renewal = exp.isoformat()
    except Exception:
        pass
    return CheckoutResult(plan_key=plan_key, billing_cycle=cycle, renewal_date=renewal, applied_credit=applied_credit, flags=flags)

class ForceSyncResponse(BaseModel):
    plan_key: str
    billing_cycle: str | None = None
    current_period_end: str | None = None
    updated: bool

def _compute_new_expiration(prior_exp: datetime | None, cycle: str, upgrading: bool) -> datetime | None:
    from datetime import datetime as _dt, date as _date, timedelta as _td
    import calendar
    if cycle not in ('monthly','annual'):
        return None
    today = _dt.utcnow().date()
    base = today
    if prior_exp and not upgrading:
        # renewal extend from current expiry (date part)
        base = prior_exp.date()
    def _add_month(d: _date) -> _date:
        year = d.year + (1 if d.month == 12 else 0)
        month = 1 if d.month == 12 else d.month + 1
        day = d.day
        try:
            return _date(year, month, day)
        except ValueError:
            last_day = calendar.monthrange(year, month)[1]
            year2 = year + (1 if month == 12 else 0)
            month2 = 1 if month == 12 else month + 1
            return _date(year2, month2, 1)
    def _add_year(d: _date) -> _date:
        try:
            return _date(d.year + 1, d.month, d.day)
        except ValueError:
            last_day = calendar.monthrange(d.year + 1, d.month)[1]
            if d.day > last_day:
                return _date(d.year + 1, d.month, last_day) + _td(days=1)
            raise
    if cycle == 'monthly':
        nxt = _add_month(base)
        if upgrading:
            nxt = nxt + _td(days=1)
    else:
        nxt = _add_year(base)
        if upgrading:
            nxt = nxt + _td(days=1)
    return _dt.combine(nxt, _dt.min.time())

@router.post("/force_sync_session", response_model=ForceSyncResponse)
async def force_sync_session(session_id: str, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Force immediate local user tier & expiration update using a Checkout Session (avoids waiting for webhook)."""
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    try:
        cs = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid session: {e}")
    sub_id = cs.get('subscription')
    if not sub_id:
        return ForceSyncResponse(plan_key=getattr(current_user,'tier','free'), billing_cycle=None, current_period_end=None, updated=False)
    try:
        sub = stripe.Subscription.retrieve(sub_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stripe subscription fetch failed: {e}")
    md = sub.get('metadata') or {}
    # Fallback to checkout session metadata if subscription metadata absent
    checkout_md = cs.get('metadata') or {}
    plan_key = md.get('plan_key') or checkout_md.get('plan_key') or getattr(current_user,'tier','free')
    cycle = md.get('cycle')
    if not cycle:
        cycle = checkout_md.get('cycle')
    prior_tier = getattr(current_user,'tier','free') or 'free'
    prior_exp = getattr(current_user,'subscription_expires_at', None)
    upgrading = (plan_key != prior_tier) or (md.get('cycle_change')=='1') or (md.get('plan_upgrade')=='1') or (prior_tier=='free' and plan_key!='free')
    # Only update if we have a legitimate plan change or tier mismatch
    updated = False
    cycle_str = cycle if isinstance(cycle, str) else 'monthly'
    if plan_key and plan_key != prior_tier and plan_key in PRICE_MAP:
        new_exp = _compute_new_expiration(prior_exp, cycle_str, upgrading=True)
        current_user.tier = plan_key
        if new_exp:
            current_user.subscription_expires_at = new_exp
        session.add(current_user)
        session.commit()
        updated = True
    elif plan_key == prior_tier and plan_key != 'free' and prior_exp is None and cycle_str in ('monthly','annual'):
        # first time setting expiration
        new_exp = _compute_new_expiration(prior_exp, cycle_str, upgrading=True)
        if new_exp:
            current_user.subscription_expires_at = new_exp
            session.add(current_user)
            session.commit()
            updated = True
    cpe = None
    try:
        if current_user.subscription_expires_at:
            cpe = current_user.subscription_expires_at.isoformat()
    except Exception:
        pass
    return ForceSyncResponse(plan_key=getattr(current_user,'tier','free'), billing_cycle=cycle_str, current_period_end=cpe, updated=updated)

@router.get("/usage")
async def get_usage(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    tier = getattr(current_user, 'tier', 'free') or 'free'
    limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
    max_eps = limits.get('max_episodes_month')
    used = _episodes_created_this_month(session, current_user.id) if max_eps is not None else None
    remaining = (max_eps - used) if (max_eps is not None and used is not None) else None
    # --- New minutes-based usage via ledger ---
    max_minutes = limits.get('max_processing_minutes_month')
    minutes_used = None
    minutes_remaining = None
    if max_minutes is not None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        minutes_used = usage_svc.month_minutes_used(session, current_user.id, start, now)
        minutes_remaining = max_minutes - minutes_used if minutes_used is not None else None
    return {
        "plan_key": tier,
        "max_episodes_month": max_eps,
        "episodes_used_this_month": used,
        "episodes_remaining_this_month": remaining,
        "max_processing_minutes_month": max_minutes,
        "processing_minutes_used_this_month": minutes_used,
        "processing_minutes_remaining_this_month": minutes_remaining,
    }


class LedgerList(BaseModel):
    items: list[dict]


@router.get("/ledger", response_model=LedgerList)
async def get_ledger(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    items = usage_svc.user_ledger(session, current_user.id, limit=200, offset=0)
    return {"items": items}


class RefundRequest(BaseModel):
    episode_id: UUID | None = None
    minutes: int
    note: str | None = None


@router.post("/refund")
async def post_refund(req: RefundRequest, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    # Simple admin-only check
    is_admin = (getattr(current_user, 'email', None) or '').lower() == (getattr(settings, 'ADMIN_EMAIL', '') or '').lower()
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    try:
        usage_svc.post_credit(
            session=session,
            user_id=current_user.id,
            minutes=int(req.minutes),
            episode_id=req.episode_id,
            reason="REFUND_ERROR",
            correlation_id=None,
            notes=(req.note or "admin refund"),
        )
        return {"ok": True}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
