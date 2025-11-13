from fastapi import APIRouter, Request, HTTPException
import os, stripe, json, datetime, logging
from ..core.database import session_scope
from ..core import crud
from ..core.constants import ALLOWED_PLANS
from ..models.user import User
from ..models.notification import Notification
from ..core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY
WEBHOOK_SECRET = settings.STRIPE_WEBHOOK_SECRET

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

router = APIRouter(prefix="/billing", tags=["Billing Webhook"])

STATUS_MAP = {
    'active': 'active',
    'trialing': 'trialing',
    'past_due': 'past_due',
    'canceled': 'canceled',
    'incomplete': 'incomplete',
    'incomplete_expired': 'incomplete_expired'
}

@router.post("/webhook")
async def stripe_webhook(request: Request):
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    if not WEBHOOK_SECRET:
        # For security, refuse to process webhooks if secret not configured (prevents spoofing)
        raise HTTPException(status_code=500, detail="Stripe webhook secret not configured")
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    event = None
    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=sig_header, secret=WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {e}")

    with session_scope() as session:
        kind = event['type']
        data = event['data']['object']
        if kind.startswith('customer.subscription.'):
            sub_id = data['id']
            status = STATUS_MAP.get(data.get('status'), 'incomplete')
            metadata = data.get('metadata') or {}
            user_id = metadata.get('user_id')
            if not user_id:
                return {"received": True}
            items = data.get('items', {}).get('data', [])
            price_id = items[0]['price']['id'] if items else None
            raw_plan_key = metadata.get('plan_key', 'unknown')
            plan_key = raw_plan_key if raw_plan_key in ALLOWED_PLANS else 'unknown'
            if plan_key == 'unknown' and raw_plan_key not in (None, ''):
                logger.warning("Rejected unknown plan_key '%s' (sub %s)", raw_plan_key, sub_id)
            current_period_end = datetime.datetime.fromtimestamp(data.get('current_period_end')) if data.get('current_period_end') else None
            cancel_at_period_end = bool(data.get('cancel_at_period_end'))
            from uuid import UUID
            try:
                user_uuid = UUID(str(user_id))
            except Exception:
                logger.error("Webhook subscription event with invalid user_id '%s'", user_id)
                return {"received": True}
            crud.upsert_subscription(
                session,
                user_id=user_uuid,
                stripe_subscription_id=sub_id,
                plan_key=plan_key,
                price_id=price_id or 'unknown',
                status=status,
                current_period_end=current_period_end,
                cancel_at_period_end=cancel_at_period_end,
                billing_cycle=metadata.get('cycle'),
            )
            user = session.get(User, user_uuid)
            if user:
                cycle = (metadata.get('cycle') or '').lower()
                from datetime import datetime as _dt, date as _date, timedelta as _td
                def _add_month(d: _date) -> _date:
                    # attempt same day next month; if invalid, take last day of next month and add one day => first of following month
                    year = d.year + (1 if d.month == 12 else 0)
                    month = 1 if d.month == 12 else d.month + 1
                    day = d.day
                    try:
                        return _date(year, month, day)
                    except ValueError:
                        # last day of that month
                        import calendar
                        last_day = calendar.monthrange(year, month)[1]
                        # Add one day past last day -> first of following month
                        year2 = year + (1 if month == 12 else 0)
                        month2 = 1 if month == 12 else month + 1
                        return _date(year2, month2, 1)
                def _add_year(d: _date) -> _date:
                    try:
                        return _date(d.year + 1, d.month, d.day)
                    except ValueError:
                        # Feb 29 -> fallback to Feb 28 then +1 day -> Mar 1
                        import calendar
                        last_day = calendar.monthrange(d.year + 1, d.month)[1]
                        if d.day > last_day:
                            return _date(d.year + 1, d.month, last_day) + _td(days=1)
                        raise
                # Upgrade / activation
                if status in ('active','trialing') and plan_key in ALLOWED_PLANS:
                    # Treat plan upgrade or cycle change as a "new subscription" for +1 day rule.
                    upgrading = plan_key != user.tier or metadata.get('cycle_change') == '1' or metadata.get('plan_upgrade') == '1'
                    # Determine base date for calculation
                    now_date = _dt.utcnow().date()
                    base = now_date
                    renewing = (not upgrading) and bool(user.subscription_expires_at)
                    if renewing:
                        # Extend from current expiration date (date part)
                        base = user.subscription_expires_at.date()
                    new_exp = None
                    if cycle == 'monthly':
                        next_month = _add_month(base)
                        if upgrading:  # add extra day for initial upgrade (free->paid or upgrade/cycle change per spec)
                            next_month = next_month + _td(days=1)
                        new_exp = _dt.combine(next_month, _dt.min.time())
                    elif cycle == 'annual':
                        next_year = _add_year(base)
                        if upgrading:
                            next_year = next_year + _td(days=1)
                        new_exp = _dt.combine(next_year, _dt.min.time())
                    if upgrading:
                        user.tier = plan_key
                    if new_exp:
                        user.subscription_expires_at = new_exp
                    # Create notification for upgrade/activation
                    try:
                        title = f"Subscription updated to {plan_key.capitalize()} ({cycle or 'monthly'})"
                        body = None
                        if new_exp:
                            body = f"Renewal on {new_exp.date().isoformat()}"
                        note = Notification(user_id=user.id, type="billing", title=title, body=body)
                        session.add(note)
                    except Exception:
                        pass
                    # Initialize subscription_started_at for first activation of this plan+cycle
                    if upgrading or not getattr(user, 'subscription_expires_at', None):
                        # we treat 'start' as now when user first activates plan
                        pass
                    session.add(user)
                    session.commit()
                    
                    # Initialize credit wallet for active subscription
                    # This ensures users have their monthly credits allocated immediately
                    try:
                        from api.services.billing.wallet import get_or_create_wallet
                        wallet = get_or_create_wallet(session, user.id, plan_key)
                        logger.info(
                            f"[webhook] Initialized wallet for user {user.id} "
                            f"(plan={plan_key}, monthly_credits={wallet.monthly_credits})"
                        )
                    except Exception as e:
                        # Don't fail webhook if wallet initialization fails (wallet table might not exist)
                        logger.warning(
                            f"[webhook] Failed to initialize wallet for user {user.id}: {e}. "
                            f"Wallet will be created on first debit or balance check."
                        )
                # Downgrade / cancellation
                if status in ('canceled','incomplete_expired') and plan_key in ALLOWED_PLANS and plan_key == user.tier:
                    if status == 'incomplete_expired' or (status == 'canceled' and not data.get('cancel_at_period_end')):
                        user.tier = 'free'
                        session.add(user)
                        session.commit()
        elif kind == 'checkout.session.completed':
            cs = data
            customer_id = cs.get('customer')
            metadata = cs.get('metadata') or {}
            user_id = metadata.get('user_id')
            purchase_type = metadata.get('type')
            
            if user_id and customer_id:
                user = session.get(User, user_id)
                if user and not getattr(user, 'stripe_customer_id', None):
                    user.stripe_customer_id = customer_id
                    session.add(user)
                    session.commit()
            
            # Handle addon credits purchase
            if purchase_type == 'addon_credits' and user_id:
                try:
                    from uuid import UUID
                    user_uuid = UUID(str(user_id))
                    user = session.get(User, user_uuid)
                    if not user:
                        logger.error(f"[webhook] User {user_id} not found for addon credits purchase")
                        return {"received": True}
                    
                    # Get the line items to determine credit amount
                    line_items = stripe.checkout.Session.list_line_items(cs['id'], limit=1)
                    if line_items.data and len(line_items.data) > 0:
                        price = line_items.data[0].price
                        # Get credits amount from price metadata
                        credits_amount = 0.0
                        if hasattr(price, 'metadata') and price.metadata and 'credits' in price.metadata:
                            credits_amount = float(price.metadata['credits'])
                        elif price.get('metadata') and 'credits' in price.get('metadata', {}):
                            credits_amount = float(price['metadata']['credits'])
                        else:
                            # Default: 10,000 credits for addon_credits products
                            logger.warning(f"[webhook] No credits metadata found for price {price.id}, defaulting to 10,000")
                            credits_amount = 10000.0
                        
                        if credits_amount > 0:
                            from api.services.billing.wallet import add_purchased_credits
                            wallet = add_purchased_credits(session, user_uuid, credits_amount)
                            logger.info(
                                f"[webhook] Added {credits_amount} purchased credits to user {user_id} "
                                f"(total_purchased={wallet.purchased_credits})"
                            )
                            
                            # Create notification
                            try:
                                note = Notification(
                                    user_id=user_uuid,
                                    type="billing",
                                    title="Credits Purchased",
                                    body=f"You've purchased {int(credits_amount):,} credits. They've been added to your account."
                                )
                                session.add(note)
                                session.commit()
                            except Exception as e:
                                logger.warning(f"[webhook] Failed to create notification for addon credits: {e}")
                        else:
                            logger.warning(f"[webhook] Could not determine credits amount for addon purchase (price_id={price.id})")
                except Exception as e:
                    logger.error(f"[webhook] Error processing addon credits purchase: {e}", exc_info=True)
        else:
            logger.debug("Ignoring Stripe event type: %s", kind)
        return {"received": True}
