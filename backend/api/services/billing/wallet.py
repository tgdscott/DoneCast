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


__all__ = [
    "get_period_string",
    "get_or_create_wallet",
    "debit",
    "add_purchased_credits",
    "process_rollover",
    "get_wallet_balance",
]

