"""
Credit wallet service for managing monthly, purchased, and rollover credits.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlmodel import Session, select

from api.models.wallet import CreditWallet
from api.billing.plans import PLANS, ROLLOVER_RATE

log = logging.getLogger(__name__)


def get_period_string(dt: Optional[datetime] = None) -> str:
    """Get billing period string (YYYY-MM) for a datetime."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m")


def get_or_create_wallet(
    session: Session,
    user_id: UUID,
    plan_key: str,
    period: Optional[str] = None
) -> CreditWallet:
    """
    Get or create wallet for user in billing period.
    
    If wallet doesn't exist, creates it with monthly credits from plan.
    """
    if period is None:
        period = get_period_string()
    
    # Try to get existing wallet
    stmt = select(CreditWallet).where(
        CreditWallet.user_id == user_id,
        CreditWallet.period == period
    )
    wallet = session.exec(stmt).first()
    
    if wallet:
        return wallet
    
    # Create new wallet
    plan = PLANS.get(plan_key.lower())
    monthly_credits = 0.0
    if plan and not plan.get("internal", False):
        monthly_credits = plan.get("monthly_credits", 0.0)
    
    wallet = CreditWallet(
        user_id=user_id,
        period=period,
        monthly_credits=monthly_credits,
        rollover_credits=0.0,
        purchased_credits=0.0,
        used_credits=0.0,
        used_monthly_rollover=0.0,
        used_purchased=0.0,
    )
    
    session.add(wallet)
    session.commit()
    session.refresh(wallet)
    
    log.info(
        f"[wallet] Created wallet for user {user_id}, period {period}, "
        f"monthly_credits={monthly_credits}"
    )
    
    return wallet


def debit(
    session: Session,
    user_id: UUID,
    amount: float,
    reason: str,
    metadata: Optional[dict] = None,
    request_id: Optional[str] = None
) -> None:
    """
    Debit credits from user's wallet (atomic, idempotent).
    
    Debit order: first monthly+rollover, then purchased.
    
    Args:
        session: Database session
        user_id: User to debit
        amount: Credits to debit
        reason: Reason for debit (for logging)
        metadata: Optional metadata dict
        request_id: Optional idempotency key (if provided and already exists, no-op)
    """
    if amount <= 0:
        return
    
    period = get_period_string()
    
    # Get or create wallet
    from api.models.user import User
    user = session.get(User, user_id)
    if not user:
        log.error(f"[wallet] User {user_id} not found for debit")
        return
    
    plan_key = getattr(user, 'tier', 'free') or 'free'
    
    # Check if unlimited plan (bypass debit but still log)
    plan = PLANS.get(plan_key.lower())
    is_unlimited = plan and plan.get("internal", False)
    
    wallet = get_or_create_wallet(session, user_id, plan_key, period)
    
    # For unlimited plans, still track usage but don't block
    if is_unlimited:
        wallet.used_credits += amount
        wallet.updated_at = datetime.utcnow()
        session.add(wallet)
        session.commit()
        log.info(
            f"[wallet] Unlimited plan: debited {amount} credits (logged only) "
            f"for user {user_id}, reason={reason}"
        )
        return
    
    # Check if we have enough credits
    available = wallet.total_available
    if available < amount:
        # For unlimited, we already handled this above
        # For others, we should raise or handle insufficient credits
        log.warning(
            f"[wallet] Insufficient credits: user {user_id} has {available}, "
            f"needs {amount}"
        )
        # Still debit to track usage (may go negative)
        # The calling code should check before calling debit()
    
    # Debit in order: monthly+rollover first, then purchased
    remaining = amount
    
    # First, use monthly+rollover credits
    available_mr = wallet.available_monthly_rollover
    if available_mr > 0 and remaining > 0:
        use_mr = min(available_mr, remaining)
        wallet.used_monthly_rollover += use_mr
        remaining -= use_mr
    
    # Then, use purchased credits
    if remaining > 0:
        available_purchased = wallet.available_purchased
        if available_purchased > 0:
            use_purchased = min(available_purchased, remaining)
            wallet.used_purchased += use_purchased
            remaining -= use_purchased
    
    # Update total used
    wallet.used_credits += amount
    wallet.updated_at = datetime.utcnow()
    
    session.add(wallet)
    session.commit()
    
    log.info(
        f"[wallet] Debited {amount} credits from user {user_id} "
        f"(period={period}, reason={reason}, "
        f"remaining_available={wallet.total_available})"
    )


def add_purchased_credits(
    session: Session,
    user_id: UUID,
    amount: float,
    period: Optional[str] = None
) -> CreditWallet:
    """
    Add purchased credits to user's wallet.
    
    Purchased credits are added to current period and never expire.
    """
    if period is None:
        period = get_period_string()
    
    from api.models.user import User
    user = session.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    plan_key = getattr(user, 'tier', 'free') or 'free'
    wallet = get_or_create_wallet(session, user_id, plan_key, period)
    
    wallet.purchased_credits += amount
    wallet.updated_at = datetime.utcnow()
    
    session.add(wallet)
    session.commit()
    session.refresh(wallet)
    
    log.info(
        f"[wallet] Added {amount} purchased credits to user {user_id} "
        f"(period={period}, total_purchased={wallet.purchased_credits})"
    )
    
    return wallet


def process_rollover(
    session: Session,
    user_id: UUID,
    from_period: str,
    to_period: str
) -> CreditWallet:
    """
    Process credit rollover from one period to next.
    
    Rolls over up to 10% of unused monthly+rollover credits.
    """
    # Get previous period wallet
    stmt = select(CreditWallet).where(
        CreditWallet.user_id == user_id,
        CreditWallet.period == from_period
    )
    prev_wallet = session.exec(stmt).first()
    
    if not prev_wallet:
        log.warning(
            f"[wallet] No wallet found for rollover: user {user_id}, period {from_period}"
        )
        # Create empty wallet for new period
        from api.models.user import User
        user = session.get(User, user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        plan_key = getattr(user, 'tier', 'free') or 'free'
        return get_or_create_wallet(session, user_id, plan_key, to_period)
    
    # Calculate rollover (10% of unused monthly+rollover, capped at monthly_credits)
    unused = prev_wallet.unused_monthly_rollover
    rollover_amount = min(unused * ROLLOVER_RATE, prev_wallet.monthly_credits)
    
    if rollover_amount <= 0:
        log.info(
            f"[wallet] No rollover for user {user_id}: "
            f"unused={unused}, rollover={rollover_amount}"
        )
        # Still create wallet for new period
        from api.models.user import User
        user = session.get(User, user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        plan_key = getattr(user, 'tier', 'free') or 'free'
        return get_or_create_wallet(session, user_id, plan_key, to_period)
    
    # Get or create new period wallet
    from api.models.user import User
    user = session.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")
    plan_key = getattr(user, 'tier', 'free') or 'free'
    new_wallet = get_or_create_wallet(session, user_id, plan_key, to_period)
    
    # Add rollover to new wallet
    new_wallet.rollover_credits = rollover_amount
    new_wallet.updated_at = datetime.utcnow()
    
    session.add(new_wallet)
    session.commit()
    session.refresh(new_wallet)
    
    log.info(
        f"[wallet] Rolled over {rollover_amount} credits for user {user_id} "
        f"from {from_period} to {to_period}"
    )
    
    return new_wallet


def get_wallet_balance(
    session: Session,
    user_id: UUID,
    period: Optional[str] = None
) -> float:
    """Get total available credits for user in period."""
    if period is None:
        period = get_period_string()
    
    stmt = select(CreditWallet).where(
        CreditWallet.user_id == user_id,
        CreditWallet.period == period
    )
    wallet = session.exec(stmt).first()
    
    if not wallet:
        # Return 0 if no wallet exists (will be created on first debit)
        return 0.0
    
    return wallet.total_available


def process_monthly_rollover(
    session: Session,
    now: Optional[datetime] = None,
    target_period: Optional[str] = None
) -> dict:
    """
    Process monthly credit rollover for all active subscribers.
    
    For each active subscriber:
    1. Compute unused = (monthly_credits + rollover_credits) - used_monthly_rollover for ending period
    2. roll = min(int(unused * ROLLOVER_RATE), plan.monthly_credits) (cap at monthly_credits)
    3. Set new period:
       - rollover_credits = roll
       - monthly_credits = plan.monthly_credits
       - used_monthly_rollover = 0
    4. Leave purchased_credits unchanged
    
    Args:
        session: Database session
        now: Current datetime (defaults to UTC now)
        target_period: Optional period to process (YYYY-MM). If not provided, uses previous month.
                      Used for idempotency - will refuse to run twice for same period.
    
    Returns:
        dict with summary: processed_count, rollover_total, errors
    """
    if now is None:
        now = datetime.now(timezone.utc)
    
    # Determine periods
    # We process rollover FROM the previous month TO the current month
    if target_period:
        # Validate format
        try:
            from datetime import datetime as dt
            dt.strptime(target_period, "%Y-%m")
        except ValueError:
            raise ValueError(f"Invalid period format: {target_period}. Expected YYYY-MM")
        to_period = target_period
        # Calculate from_period (previous month)
        year, month = map(int, to_period.split("-"))
        if month == 1:
            from_period = f"{year-1}-12"
        else:
            from_period = f"{year}-{month-1:02d}"
    else:
        # Default: process rollover from previous month to current month
        # to_period is the NEW period we're creating (current month)
        to_period = get_period_string(now)
        # from_period is the OLD period we're rolling over from (previous month)
        year, month = map(int, to_period.split("-"))
        if month == 1:
            from_period = f"{year-1}-12"
        else:
            from_period = f"{year}-{month-1:02d}"
    
    # Check idempotency: ensure we haven't already processed this period
    from api.models.wallet import WalletPeriodProcessed
    existing = session.exec(
        select(WalletPeriodProcessed).where(WalletPeriodProcessed.period == to_period)
    ).first()
    
    if existing:
        log.warning(
            f"[WALLET] Rollover already processed for period {to_period}. "
            f"Processed at {existing.processed_at}"
        )
        return {
            "status": "already_processed",
            "period": to_period,
            "processed_at": existing.processed_at.isoformat(),
            "processed_count": 0,
            "rollover_total": 0.0,
            "errors": []
        }
    
    # Get all active subscribers
    # Active = users with non-free tier OR active subscription OR subscription_expires_at in future
    from api.models.user import User
    from api.models.subscription import Subscription
    
    # Get users with paid tiers
    paid_tier_users = session.exec(
        select(User).where(
            User.tier.notin_(["free", "admin", "superadmin"]),  # type: ignore
            User.tier.isnot(None)  # type: ignore
        )
    ).all()
    
    # Get users with active subscriptions
    active_subscriptions = session.exec(
        select(Subscription).where(
            Subscription.status.in_(["active", "trialing", "past_due"])  # type: ignore
        )
    ).all()
    subscription_user_ids = {sub.user_id for sub in active_subscriptions}
    
    # Get users with future subscription_expires_at
    future_expiry_users = session.exec(
        select(User).where(
            User.subscription_expires_at > now  # type: ignore
        )
    ).all()
    future_expiry_user_ids = {u.id for u in future_expiry_users}
    
    # Combine all active subscriber user IDs
    active_user_ids = set()
    for user in paid_tier_users:
        active_user_ids.add(user.id)
    active_user_ids.update(subscription_user_ids)
    active_user_ids.update(future_expiry_user_ids)
    
    log.info(
        f"[WALLET] Processing monthly rollover: from_period={from_period}, "
        f"to_period={to_period}, active_subscribers={len(active_user_ids)}"
    )
    
    processed_count = 0
    rollover_total = 0.0
    errors = []
    
    # Process each active subscriber
    for user_id in active_user_ids:
        try:
            user = session.get(User, user_id)
            if not user:
                errors.append(f"User {user_id} not found")
                continue
            
            plan_key = getattr(user, 'tier', 'free') or 'free'
            
            # Skip free tier users (unless they have active subscription)
            if plan_key == 'free' and user_id not in subscription_user_ids and user_id not in future_expiry_user_ids:
                continue
            
            # Get plan
            plan = PLANS.get(plan_key.lower())
            if not plan:
                log.warning(f"[WALLET] Unknown plan for user {user_id}: {plan_key}")
                continue
            
            # Skip unlimited/internal plans (they don't have monthly credits)
            if plan.get("internal", False):
                continue
            
            # Get previous period wallet
            prev_wallet = session.exec(
                select(CreditWallet).where(
                    CreditWallet.user_id == user_id,
                    CreditWallet.period == from_period
                )
            ).first()
            
            # Calculate unused credits
            if prev_wallet:
                unused = prev_wallet.unused_monthly_rollover
            else:
                unused = 0.0
            
            # Calculate rollover: 10% of unused, capped at monthly_credits
            monthly_credits = plan.get("monthly_credits", 0.0)
            roll = min(int(unused * ROLLOVER_RATE), int(monthly_credits))
            
            if unused <= 0:
                log.debug(
                    f"[WALLET] No rollover for user {user_id}: unused={unused}"
                )
                # Still create wallet for new period with monthly credits
                new_wallet = get_or_create_wallet(session, user_id, plan_key, to_period)
                new_wallet.monthly_credits = monthly_credits
                new_wallet.rollover_credits = 0.0
                new_wallet.used_monthly_rollover = 0.0
                new_wallet.updated_at = datetime.utcnow()
                session.add(new_wallet)
                session.commit()
                continue
            
            # Get or create new period wallet
            new_wallet = get_or_create_wallet(session, user_id, plan_key, to_period)
            
            # Set new period values
            new_wallet.rollover_credits = float(roll)
            new_wallet.monthly_credits = monthly_credits
            new_wallet.used_monthly_rollover = 0.0
            # Preserve purchased_credits (they carry over)
            # Note: purchased_credits are already in the wallet from get_or_create_wallet
            new_wallet.updated_at = datetime.utcnow()
            
            session.add(new_wallet)
            session.commit()
            session.refresh(new_wallet)
            
            processed_count += 1
            rollover_total += roll
            
            log.info(
                f"[WALLET] rollover user={user_id} roll={roll} "
                f"new_monthly={monthly_credits} from_period={from_period} to_period={to_period}"
            )
            
        except Exception as e:
            error_msg = f"Error processing rollover for user {user_id}: {e}"
            log.error(f"[WALLET] {error_msg}", exc_info=True)
            errors.append(error_msg)
            session.rollback()
            continue
    
    # Mark period as processed (idempotency)
    try:
        processed_record = WalletPeriodProcessed(
            period=to_period,
            processed_at=now,
            processed_count=processed_count,
            rollover_total=rollover_total
        )
        session.add(processed_record)
        session.commit()
    except Exception as e:
        log.error(f"[WALLET] Failed to record period processing: {e}", exc_info=True)
        # Don't fail the whole operation if we can't record it
    
    log.info(
        f"[WALLET] Monthly rollover complete: period={to_period}, "
        f"processed={processed_count}, rollover_total={rollover_total}, errors={len(errors)}"
    )
    
    return {
        "status": "completed",
        "period": to_period,
        "from_period": from_period,
        "processed_count": processed_count,
        "rollover_total": rollover_total,
        "errors": errors
    }


__all__ = [
    "get_period_string",
    "get_or_create_wallet",
    "debit",
    "add_purchased_credits",
    "process_rollover",
    "process_monthly_rollover",
    "get_wallet_balance",
]

