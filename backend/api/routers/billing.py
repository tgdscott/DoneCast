from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel
from sqlmodel import Session
from ..core.database import get_session
from ..models.user import User
from api.routers.auth import get_current_user
from api.routers.admin.deps import get_current_admin_user
import os, stripe, logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from ..core.constants import TIER_LIMITS
from ..core import crud
from uuid import UUID
from sqlmodel import select
from sqlalchemy import func
from ..services.billing import usage as usage_svc
from ..core.config import settings
from typing import Optional
from ..models.promo_code import PromoCode

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter(prefix="/billing", tags=["Billing"])

# Internal router for scheduled jobs
internal_router = APIRouter(prefix="/internal/billing", tags=["internal:billing"])

_TASKS_AUTH = os.getenv("TASKS_AUTH", "")

PRICE_MAP = {
    "starter": {
        "monthly": os.getenv("PRICE_STARTER_MONTHLY", "price_starter_monthly_placeholder"),
        # Starter does not have an annual plan
    },
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
    "pro": {
        "monthly": os.getenv("PRICE_PRO_MONTHLY", "price_pro_monthly_placeholder"),
        "annual": os.getenv("PRICE_PRO_ANNUAL", "price_pro_annual_placeholder"),
    },
    "executive": {
        "monthly": os.getenv("PRICE_EXECUTIVE_MONTHLY", "price_executive_monthly_placeholder"),
        "annual": os.getenv("PRICE_EXECUTIVE_ANNUAL", "price_executive_annual_placeholder"),
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
    billing_cycle: str = "monthly"
    promo_code: Optional[str] = None

class AddonCreditsRequest(BaseModel):
    plan_key: str
    return_url: str = "/billing"

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
    """Ensure user has a Stripe customer ID, creating one if needed.
    
    Raises HTTPException if Stripe API call fails.
    """
    if not getattr(user, 'stripe_customer_id', None):
        try:
            cust = stripe.Customer.create(email=user.email, metadata={"user_id": str(user.id)})
            user.stripe_customer_id = cust.id
            session.add(user)
            session.commit()
            return cust.id
        except Exception as e:
            logger.error(
                "event=billing.customer_create_failed user_id=%s email=%s error=%s - "
                "Failed to create Stripe customer",
                user.id, user.email, str(e),
                exc_info=True
            )
            raise HTTPException(status_code=500, detail=f"Failed to create Stripe customer: {e}")
    return user.stripe_customer_id

class CheckoutSessionResponse(BaseModel):
    """Response for embedded checkout - returns client_secret instead of redirect URL"""
    client_secret: str
    session_id: str
    proration_error: str | None = None  # Set if proration was needed but failed

@router.post("/checkout/embedded", response_model=CheckoutSessionResponse)
async def create_embedded_checkout_session(
    request: Request,
    req: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Create a Stripe Checkout Session for embedded components (ui_mode='embedded').
    Returns client_secret for frontend to initialize embedded checkout.
    """
    if req.plan_key not in PRICE_MAP:
        raise HTTPException(status_code=400, detail="Unknown plan")
    cycle_prices = PRICE_MAP[req.plan_key]
    if req.billing_cycle not in cycle_prices:
        if req.plan_key == 'starter' and req.billing_cycle == 'annual':
            raise HTTPException(status_code=400, detail="Starter plan does not have an annual option")
        raise HTTPException(status_code=400, detail="Invalid billing cycle")
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    origin = None
    try:
        origin = request.headers.get('origin')
    except Exception:
        origin = None
    if origin and origin.startswith("http"):
        base_url = origin.rstrip('/')
    else:
        base_url = os.getenv("APP_BASE_URL", "https://app.podcastplusplus.com")
    
    price_id = _resolve_price_id(cycle_prices[req.billing_cycle])
    
    try:
        customer_id = _ensure_customer(current_user, session)
        
        metadata = {"user_id": str(current_user.id), "plan_key": req.plan_key, "cycle": req.billing_cycle}
        subscription_data = {"metadata": metadata}
        discounts = []

        # --- Promo Code Validation and Application ---
        promo_code_obj = None
        if req.promo_code:
            promo_code_upper = req.promo_code.strip().upper()
            promo_code_obj = session.exec(
                select(PromoCode).where(PromoCode.code == promo_code_upper)
            ).first()
            
            if promo_code_obj:
                # Validate promo code
                if not promo_code_obj.is_active:
                    raise HTTPException(status_code=400, detail="Promo code is not active")
                if promo_code_obj.expires_at and promo_code_obj.expires_at < datetime.utcnow():
                    raise HTTPException(status_code=400, detail="Promo code has expired")
                if promo_code_obj.max_uses is not None and promo_code_obj.usage_count >= promo_code_obj.max_uses:
                    raise HTTPException(status_code=400, detail="Promo code has reached maximum uses")
                
                # Check if user has already used this promo code
                from api.models.promo_code import PromoCodeUsage
                existing_usage = session.exec(
                    select(PromoCodeUsage).where(
                        PromoCodeUsage.user_id == current_user.id,
                        PromoCodeUsage.promo_code_id == promo_code_obj.id
                    )
                ).first()
                if existing_usage:
                    raise HTTPException(status_code=400, detail="You have already used this promo code")
                
                # Check if promo code applies to this billing cycle
                if req.billing_cycle == 'monthly' and not promo_code_obj.applies_to_monthly:
                    raise HTTPException(status_code=400, detail="Promo code does not apply to monthly subscriptions")
                if req.billing_cycle == 'annual' and not promo_code_obj.applies_to_yearly:
                    raise HTTPException(status_code=400, detail="Promo code does not apply to yearly subscriptions")
                
                # Apply percentage discount if set
                if promo_code_obj.discount_percentage and promo_code_obj.discount_percentage > 0:
                    try:
                        # Get the price to calculate discount
                        price_obj = stripe.Price.retrieve(price_id)
                        unit_amount = Decimal(price_obj['unit_amount']) / Decimal(100)
                        discount_amount = (unit_amount * Decimal(promo_code_obj.discount_percentage) / Decimal(100)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                        
                        if discount_amount > 0:
                            coupon = stripe.Coupon.create(
                                name=f"Promo: {promo_code_obj.code}",
                                percent_off=float(promo_code_obj.discount_percentage),
                                duration='once',
                                metadata={
                                    "promo_code": promo_code_obj.code,
                                    "user_id": str(current_user.id),
                                    "source": "promo_code"
                                }
                            )
                            discounts = [{"coupon": coupon.id}]
                            metadata['promo_code'] = promo_code_obj.code
                            metadata['promo_code_id'] = str(promo_code_obj.id)
                            logger.info(
                                f"[billing] Applied promo code {promo_code_obj.code} "
                                f"({promo_code_obj.discount_percentage}% discount) for user {current_user.id}"
                            )
                    except Exception as e:
                        logger.error(
                            f"[billing] Failed to create Stripe coupon for promo code {promo_code_obj.code}: {e}",
                            exc_info=True
                        )
                        # Don't fail checkout if coupon creation fails, just log it
                else:
                    # No discount but promo code is valid - store it for bonus credits
                    metadata['promo_code'] = promo_code_obj.code
                    metadata['promo_code_id'] = str(promo_code_obj.id)
            else:
                # Promo code not found - don't fail, just ignore it
                logger.warning(f"[billing] Promo code '{promo_code_upper}' not found for user {current_user.id}")

        # --- Upgrade / Proration Logic ---
        prior_tier = getattr(current_user, 'tier', 'free') or 'free'
        prior_exp = getattr(current_user, 'subscription_expires_at', None)
        is_free_to_paid = (prior_tier == 'free' and req.plan_key != 'free')
        same_plan_cycle_change = (prior_tier == req.plan_key and req.billing_cycle == 'annual' and prior_exp is not None)
        is_plan_upgrade = (prior_tier != 'free' and prior_tier != req.plan_key)
        needs_proration = (same_plan_cycle_change or is_plan_upgrade) and (prior_exp is not None)
        
        proration_error = None
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
                
                try:
                    price_obj = stripe.Price.retrieve(price_id)
                    unit_amount = Decimal(price_obj['unit_amount']) / Decimal(100)
                except Exception as e:
                    logger.warning(
                        "event=billing.proration.price_retrieve_failed user_id=%s price_id=%s error=%s - "
                        "Failed to retrieve price for proration calculation, defaulting to 0",
                        current_user.id, price_id, str(e),
                        exc_info=True
                    )
                    unit_amount = Decimal('0')
                
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
                    except Exception as e:
                        logger.warning(
                            "event=billing.proration.prev_price_retrieve_failed user_id=%s price_id=%s error=%s - "
                            "Failed to retrieve previous subscription price for proration cap, continuing without cap",
                            current_user.id, prev_sub.price_id, str(e),
                            exc_info=True
                        )
                        pass  # non-fatal: continue without price cap
                
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
            except Exception as e:
                error_msg = str(e)[:150]
                logger.error(
                    "event=billing.proration.failed user_id=%s plan_key=%s prior_tier=%s error=%s - "
                    "Proration calculation failed - failing checkout to prevent overcharging user",
                    current_user.id, req.plan_key, prior_tier, error_msg,
                    exc_info=True
                )
                proration_error = error_msg
                metadata['proration_error'] = error_msg
                # CRITICAL: Fail checkout if proration was needed but failed
                # This prevents users from being overcharged (charged full price instead of prorated)
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"Unable to calculate prorated credit for your subscription upgrade. "
                        f"Please try again in a moment or contact support if this persists. "
                        f"Error: {error_msg}"
                    )
                )
        
        if same_plan_cycle_change:
            metadata['cycle_change'] = '1'
        if is_plan_upgrade:
            metadata['plan_upgrade'] = '1'
        if is_free_to_paid:
            metadata['first_paid'] = '1'

        params = dict(
            mode="subscription",
            ui_mode="embedded",
            line_items=[{"price": price_id, "quantity": 1}],
            return_url=f"{base_url}{req.success_path}?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
            customer=customer_id if customer_id else None,
            subscription_data=subscription_data,
            metadata=metadata,
        )
        
        if discounts:
            params['discounts'] = discounts
        else:
            params['allow_promotion_codes'] = True  # type: ignore[assignment]
        
        checkout_session = stripe.checkout.Session.create(**params)  # type: ignore
        
        client_secret = getattr(checkout_session, 'client_secret', None)
        if not client_secret:
            raise HTTPException(status_code=502, detail="Stripe did not return a client secret")
        
        return CheckoutSessionResponse(
            client_secret=str(client_secret),
            session_id=str(checkout_session.id),
            proration_error=proration_error
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stripe error: {e}")

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
        if req.plan_key == 'starter' and req.billing_cycle == 'annual':
            raise HTTPException(status_code=400, detail="Starter plan does not have an annual option")
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
        base_url = os.getenv("APP_BASE_URL", "https://app.podcastplusplus.com")
    price_id = _resolve_price_id(cycle_prices[req.billing_cycle])
    try:
        customer_id = _ensure_customer(current_user, session)
        # Build success URL with proper query parameters (avoid legacy double '?')
        success_qs = f"?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"

        metadata = {"user_id": str(current_user.id), "plan_key": req.plan_key, "cycle": req.billing_cycle}
        subscription_data = {"metadata": metadata}
        discounts = []

        # --- Promo Code Validation and Application ---
        promo_code_obj = None
        if req.promo_code:
            promo_code_upper = req.promo_code.strip().upper()
            promo_code_obj = session.exec(
                select(PromoCode).where(PromoCode.code == promo_code_upper)
            ).first()
            
            if promo_code_obj:
                # Validate promo code
                if not promo_code_obj.is_active:
                    raise HTTPException(status_code=400, detail="Promo code is not active")
                if promo_code_obj.expires_at and promo_code_obj.expires_at < datetime.utcnow():
                    raise HTTPException(status_code=400, detail="Promo code has expired")
                if promo_code_obj.max_uses is not None and promo_code_obj.usage_count >= promo_code_obj.max_uses:
                    raise HTTPException(status_code=400, detail="Promo code has reached maximum uses")
                
                # Check if user has already used this promo code
                from api.models.promo_code import PromoCodeUsage
                existing_usage = session.exec(
                    select(PromoCodeUsage).where(
                        PromoCodeUsage.user_id == current_user.id,
                        PromoCodeUsage.promo_code_id == promo_code_obj.id
                    )
                ).first()
                if existing_usage:
                    raise HTTPException(status_code=400, detail="You have already used this promo code")
                
                # Check if promo code applies to this billing cycle
                if req.billing_cycle == 'monthly' and not promo_code_obj.applies_to_monthly:
                    raise HTTPException(status_code=400, detail="Promo code does not apply to monthly subscriptions")
                if req.billing_cycle == 'annual' and not promo_code_obj.applies_to_yearly:
                    raise HTTPException(status_code=400, detail="Promo code does not apply to yearly subscriptions")
                
                # Apply percentage discount if set
                if promo_code_obj.discount_percentage and promo_code_obj.discount_percentage > 0:
                    try:
                        # Get the price to calculate discount
                        price_obj = stripe.Price.retrieve(price_id)
                        unit_amount = Decimal(price_obj['unit_amount']) / Decimal(100)
                        discount_amount = (unit_amount * Decimal(promo_code_obj.discount_percentage) / Decimal(100)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                        
                        if discount_amount > 0:
                            coupon = stripe.Coupon.create(
                                name=f"Promo: {promo_code_obj.code}",
                                percent_off=float(promo_code_obj.discount_percentage),
                                duration='once',
                                metadata={
                                    "promo_code": promo_code_obj.code,
                                    "user_id": str(current_user.id),
                                    "source": "promo_code"
                                }
                            )
                            discounts = [{"coupon": coupon.id}]
                            metadata['promo_code'] = promo_code_obj.code
                            metadata['promo_code_id'] = str(promo_code_obj.id)
                            logger.info(
                                f"[billing] Applied promo code {promo_code_obj.code} "
                                f"({promo_code_obj.discount_percentage}% discount) for user {current_user.id}"
                            )
                    except Exception as e:
                        logger.error(
                            f"[billing] Failed to create Stripe coupon for promo code {promo_code_obj.code}: {e}",
                            exc_info=True
                        )
                        # Don't fail checkout if coupon creation fails, just log it
                else:
                    # No discount but promo code is valid - store it for bonus credits
                    metadata['promo_code'] = promo_code_obj.code
                    metadata['promo_code_id'] = str(promo_code_obj.id)
            else:
                # Promo code not found - don't fail, just ignore it
                logger.warning(f"[billing] Promo code '{promo_code_upper}' not found for user {current_user.id}")

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
                except Exception as e:
                    logger.warning(
                        "event=billing.proration.price_retrieve_failed user_id=%s price_id=%s error=%s - "
                        "Failed to retrieve price for proration calculation, defaulting to 0",
                        current_user.id, price_id, str(e),
                        exc_info=True
                    )
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
                    except Exception as e:
                        logger.warning(
                            "event=billing.proration.prev_price_retrieve_failed user_id=%s price_id=%s error=%s - "
                            "Failed to retrieve previous subscription price for proration cap, continuing without cap",
                            current_user.id, prev_sub.price_id, str(e),
                            exc_info=True
                        )
                        pass  # non-fatal: continue without price cap
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
                error_msg = str(e)[:150]
                logger.error(
                    "event=billing.proration.failed user_id=%s plan_key=%s prior_tier=%s error=%s - "
                    "Proration calculation failed - failing checkout to prevent overcharging user",
                    current_user.id, req.plan_key, prior_tier, error_msg,
                    exc_info=True
                )
                metadata['proration_error'] = error_msg
                # CRITICAL: Fail checkout if proration was needed but failed
                # This prevents users from being overcharged (charged full price instead of prorated)
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"Unable to calculate prorated credit for your subscription upgrade. "
                        f"Please try again in a moment or contact support if this persists. "
                        f"Error: {error_msg}"
                    )
                )
        if same_plan_cycle_change:
            metadata['cycle_change'] = '1'
        if is_plan_upgrade:
            metadata['plan_upgrade'] = '1'
        if is_free_to_paid:
            metadata['first_paid'] = '1'

        params = dict(
            mode="subscription",
            ui_mode="embedded",  # Enable embedded checkout
            line_items=[{"price": price_id, "quantity": 1}],
            return_url=f"{base_url}{req.success_path}?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
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
    base_url = os.getenv("APP_BASE_URL", "https://app.podcastplusplus.com")
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
    """Count episodes created this month for the given user.
    
    Returns the count of episodes created in the current month.
    
    Raises RuntimeError if the query with created_at filter fails (e.g., column missing on old rows).
    This prevents returning an inflated count (all episodes ever) which would incorrectly show
    the user has exhausted their monthly quota.
    """
    from datetime import datetime, timezone
    from calendar import monthrange  # noqa: F401 (future use for resetting logic)
    from ..models.podcast import Episode
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    try:
        return session.exec(
            select(func.count(Episode.id))
            .where(Episode.user_id == user_id)
            .where(Episode.created_at >= start)
        ).one()
    except Exception as e:
        # CRITICAL: Do not fall back to counting all episodes - that would inflate monthly usage
        # Instead, raise an error so the caller can handle it appropriately
        logger.error(
            "event=billing.episode_count_failed user_id=%s error=%s - "
            "Failed to count episodes created this month (created_at filter failed). "
            "Cannot compute accurate monthly usage. Caller should handle this error.",
            user_id, str(e),
            exc_info=True
        )
        raise RuntimeError(
            f"Unable to compute accurate monthly episode count for user {user_id}. "
            f"The created_at column may be missing or the query failed: {e}"
        ) from e


@router.get("/subscription", response_model=SubscriptionStatus)
async def get_subscription(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    # Use effective tier (trial users get "starter" tier limits)
    from api.services.trial_service import get_effective_tier
    tier = get_effective_tier(current_user) or 'free'
    limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
    max_eps = limits.get('max_episodes_month')
    used = None
    remaining = None
    if max_eps is not None:
        try:
            used = _episodes_created_this_month(session, current_user.id)
            remaining = (max_eps - used) if used is not None else None
        except RuntimeError as e:
            # Cannot compute accurate monthly usage - fail the endpoint to prevent misleading data
            logger.error(
                "event=billing.subscription.episode_count_unavailable user_id=%s error=%s - "
                "Cannot compute accurate monthly episode usage. Failing endpoint to prevent displaying incorrect quota information.",
                current_user.id, str(e),
                exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=(
                    "Unable to compute your monthly episode usage at this time. "
                    "Please try again in a moment or contact support if this persists."
                )
            )
    # Derive current_period_end from user.subscription_expires_at (renewal date) if present
    cpe = None
    try:
        exp = getattr(current_user, 'subscription_expires_at', None)
        if exp:
            cpe = exp.isoformat()
    except Exception as e:
        logger.warning(
            "event=billing.subscription_expires_at_read_failed user_id=%s error=%s - "
            "Failed to read subscription_expires_at, returning None for current_period_end",
            current_user.id, str(e),
            exc_info=True
        )
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
    except (ValueError, TypeError, KeyError) as e:
        # Narrow exception handling: only catch expected data structure issues
        logger.warning(
            "event=billing.checkout_result.discount_read_failed user_id=%s session_id=%s error=%s - "
            "Failed to parse discount data from checkout session (data structure issue). "
            "Returning None, which may incorrectly show 'no credit applied' in UI even if discount was applied.",
            current_user.id, session_id, str(e),
            exc_info=True
        )
        # Continue with applied_credit = None for data structure issues (non-critical)
    except Exception as e:
        # Unexpected errors (network, API issues) should fail the endpoint
        logger.error(
            "event=billing.checkout_result.discount_read_failed user_id=%s session_id=%s error=%s - "
            "Unexpected error reading discount information from checkout session. "
            "Failing endpoint to prevent incorrect 'no credit applied' display.",
            current_user.id, session_id, str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "Unable to retrieve applied credit information for this checkout session. "
                "Please refresh or contact support if this persists."
            )
        )
    renewal = None
    try:
        exp = getattr(current_user, 'subscription_expires_at', None)
        if exp:
            renewal = exp.isoformat()
    except Exception as e:
        logger.warning(
            "event=billing.checkout_result.renewal_date_read_failed user_id=%s session_id=%s error=%s - "
            "Failed to read subscription_expires_at for renewal date, returning None",
            current_user.id, session_id, str(e),
            exc_info=True
        )
        # Continue with renewal = None - non-critical field
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
    """
    Get usage information for the current user.
    
    Returns credit-based usage (new system) as primary, with legacy fields for backward compatibility.
    """
    from datetime import datetime, timezone
    from api.services.billing import credits
    from api.billing.plans import get_plan, is_unlimited_plan
    from api.services.billing.wallet import get_wallet_details
    
    tier = getattr(current_user, 'tier', 'free') or 'free'
    plan = get_plan(tier)
    
    # ========== CREDITS SYSTEM (PRIMARY) ==========
    # Get current credit balance and wallet details
    credits_balance = credits.get_user_credit_balance(session, current_user.id)
    wallet_details = get_wallet_details(session, current_user.id)
    
    # Get monthly credit allocation from plan
    if is_unlimited_plan(tier):
        max_credits = None  # Unlimited
    elif plan:
        max_credits = plan.get("monthly_credits")
    else:
        max_credits = 0.0
    
    # Get breakdown by action type for this month
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    breakdown = usage_svc.month_credits_breakdown(session, current_user.id, start_of_month, now)
    total_credits_used = breakdown.get('total', 0.0)
    
    # For quota display: use monthly allocation usage (not total credits which includes purchased)
    # The progress bar should show: used_monthly_rollover / monthly_credits
    monthly_credits_used = wallet_details.get("used_monthly_rollover", 0.0)
    monthly_credits_total = wallet_details.get("monthly_credits", 0.0)
    
    # Calculate credits remaining (total available credits)
    if max_credits is None:
        credits_remaining = None  # Unlimited
    else:
        credits_remaining = max(0.0, credits_balance)  # Use current balance, not max - used
    
    # ========== LEGACY FIELDS (for backward compatibility) ==========
    # Keep episode limits for now (may be removed in future)
    limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
    max_eps = limits.get('max_episodes_month')
    
    # Legacy minutes fields (deprecated, but kept for transition)
    max_minutes = limits.get('max_processing_minutes_month')
    minutes_used = None
    minutes_remaining = None
    if max_minutes is not None:
        minutes_used = usage_svc.month_minutes_used(session, current_user.id, start_of_month, now)
        minutes_remaining = max_minutes - minutes_used if minutes_used is not None else None
    
    # Legacy episode fields - handle failure explicitly
    used_episodes = None
    remaining_episodes = None
    if max_eps is not None:
        try:
            used_episodes = _episodes_created_this_month(session, current_user.id)
            remaining_episodes = (max_eps - used_episodes) if used_episodes is not None else None
        except RuntimeError as e:
            # Cannot compute accurate monthly usage - log but don't fail the entire usage endpoint
            # (usage endpoint has other important data like credits)
            logger.warning(
                "event=billing.usage.episode_count_unavailable user_id=%s error=%s - "
                "Cannot compute accurate monthly episode usage. Returning None for episode fields.",
                current_user.id, str(e),
                exc_info=True
            )
            used_episodes = None
            remaining_episodes = None
    
    return {
        "plan_key": tier,
        # Legacy episode fields
        "max_episodes_month": max_eps,
        "episodes_used_this_month": used_episodes,
        "episodes_remaining_this_month": remaining_episodes,
        # Legacy minutes fields (deprecated)
        "max_processing_minutes_month": max_minutes,
        "processing_minutes_used_this_month": minutes_used,
        "processing_minutes_remaining_this_month": minutes_remaining,
        # NEW: Credits fields (PRIMARY)
        "max_credits_month": max_credits,
        "credits_balance": credits_balance,
        "credits_used_this_month": total_credits_used,
        "credits_remaining_this_month": credits_remaining,
        # Monthly allocation usage (for progress bar display)
        "monthly_credits_used": monthly_credits_used,
        "monthly_credits_total": monthly_credits_total,
        "credits_breakdown": {
            "tts_generation": breakdown.get('tts_generation', 0),
            "transcription": breakdown.get('transcription', 0),
            "assembly": breakdown.get('assembly', 0),
            "storage": breakdown.get('storage', 0),
            "auphonic_processing": breakdown.get('auphonic_processing', 0),
            "ai_metadata": breakdown.get('ai_metadata', 0),
        },
        # Wallet details for detailed breakdown
        "wallet": {
            "monthly_credits": wallet_details.get("monthly_credits", 0.0),
            "rollover_credits": wallet_details.get("rollover_credits", 0.0),
            "purchased_credits": wallet_details.get("purchased_credits", 0.0),
            "monthly_allocation_available": wallet_details.get("monthly_allocation_available", 0.0),
            "purchased_credits_available": wallet_details.get("purchased_credits_available", 0.0),
        }
    }


class LedgerList(BaseModel):
    items: list[dict]


@router.get("/ledger", response_model=LedgerList)
async def get_ledger(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    items = usage_svc.user_ledger(session, current_user.id, limit=200, offset=0)
    return {"items": items}


@router.post("/checkout/addon_credits", response_model=CheckoutResponse)
async def create_addon_credits_checkout(
    request: Request,
    req: AddonCreditsRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Create a Stripe Checkout Session for purchasing addon credits.
    
    Uses lookup_key format: addon_credits_<plan>
    """
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    
    # Look up the addon credits price using lookup_key
    lookup_key = f"addon_credits_{req.plan_key.lower()}"
    
    try:
        # Query Stripe for price with this lookup_key
        prices = stripe.Price.list(lookup_keys=[lookup_key], limit=1)
        if not prices.data or len(prices.data) == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Addon credits price not found for plan '{req.plan_key}'. Lookup key: {lookup_key}"
            )
        price = prices.data[0]
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=500, detail=f"Stripe error looking up price: {e}")
    
    # Ensure customer exists
    customer_id = _ensure_customer(current_user, session)
    
    # Build return URLs
    base_url = os.getenv("APP_BASE_URL", "https://app.podcastplusplus.com")
    success_url = f"{base_url}{req.return_url}?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{base_url}{req.return_url}"
    
    try:
        checkout_session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[
                {
                    "price": price.id,
                    "quantity": 1,
                }
            ],
            mode="payment",  # One-time payment, not subscription
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "user_id": str(current_user.id),
                "type": "addon_credits",
                "plan_key": req.plan_key,
            },
            allow_promotion_codes=True,
        )
        
        chk_url = getattr(checkout_session, 'url', None)
        if not chk_url:
            raise HTTPException(status_code=502, detail="Stripe did not return a checkout URL")
        
        return CheckoutResponse(url=str(chk_url))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stripe error: {e}")


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


# ============================================================================
# Internal endpoints (Cloud Scheduler / Admin)
# ============================================================================

def _require_internal_auth(request: Request, x_tasks_auth: str | None = None):
    """
    Require either Cloud Scheduler OIDC token OR admin token OR TASKS_AUTH header.
    
    Supports:
    - Cloud Scheduler OIDC: Bearer token in Authorization header
    - Admin token: Via get_current_admin_user dependency
    - Legacy: x-tasks-auth header matching TASKS_AUTH env var
    """
    # Check for OIDC token (Cloud Scheduler)
    auth_header = request.headers.get("Authorization", "")
    has_oidc = auth_header.startswith("Bearer ")
    
    # Check for legacy TASKS_AUTH header
    has_tasks_auth = x_tasks_auth and _TASKS_AUTH and x_tasks_auth == _TASKS_AUTH
    
    # If neither, require admin auth (will be checked via dependency)
    if not (has_oidc or has_tasks_auth):
        # This will be handled by the admin dependency if provided
        pass


class RolloverRequest(BaseModel):
    """Request body for rollover endpoint."""
    period: str | None = None  # Optional YYYY-MM period for idempotency


@internal_router.post("/rollover")
async def process_rollover_endpoint(
    request: Request,
    session: Session = Depends(get_session),
    payload: RolloverRequest | None = None,
    x_tasks_auth: str | None = Header(default=None),
):
    """
    Process monthly credit rollover for all active subscribers.
    
    Protected endpoint requiring:
    - Cloud Scheduler OIDC token (Bearer token), OR
    - Admin authentication (via Authorization header with JWT), OR
    - TASKS_AUTH header
    
    Args:
        payload: Optional request body with 'period' (YYYY-MM) for idempotency
    
    Returns:
        Summary of rollover processing
    """
    # Check authentication
    # Accept:
    # 1. Bearer token (OIDC from Cloud Scheduler OR admin JWT)
    # 2. TASKS_AUTH header (legacy)
    auth_header = request.headers.get("Authorization", "")
    has_bearer_token = auth_header.startswith("Bearer ")
    has_tasks_auth = x_tasks_auth and _TASKS_AUTH and x_tasks_auth == _TASKS_AUTH
    
    # Optionally verify admin JWT (for manual testing)
    # Note: Cloud Scheduler OIDC tokens also use "Bearer " prefix
    # We accept any Bearer token - actual verification happens at application level
    has_admin = False
    if has_bearer_token:
        try:
            # Try to verify as admin user (for manual testing)
            from api.routers.auth import get_current_user
            current_user = await get_current_user(request=request)
            # Check if user is admin
            from api.routers.auth.utils import is_admin
            has_admin = is_admin(current_user)
        except Exception:
            # Not an admin user or invalid token - that's ok, could be OIDC
            pass
    
    if not (has_bearer_token or has_tasks_auth or has_admin):
        raise HTTPException(status_code=401, detail="Unauthorized: requires Bearer token (OIDC or admin JWT), or TASKS_AUTH header")
    
    from api.services.billing.wallet import process_monthly_rollover
    from datetime import datetime as dt
    
    try:
        target_period = payload.period if payload else None
        result = process_monthly_rollover(
            session=session,
            now=dt.now(timezone.utc),
            target_period=target_period
        )
        
        return {
            "ok": True,
            **result
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        from api.core.logging import get_logger
        logger = get_logger("api.routers.billing")
        logger.error(f"Rollover processing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Rollover processing failed: {str(e)}")
