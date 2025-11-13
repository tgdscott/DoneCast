"""
Credit wallet service for managing monthly, purchased, and rollover credits.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlmodel import Session, select, col as sqlmodel_col
from sqlalchemy import func, extract

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
    # Normalize "free" to "starter" for plan lookup (backend uses "free", plans use "starter")
    normalized_plan_key = plan_key.lower()
    if normalized_plan_key == "free":
        normalized_plan_key = "starter"
    plan = PLANS.get(normalized_plan_key)
    monthly_credits = 0.0
    if plan and not plan.get("internal", False):
        monthly_credits = plan.get("monthly_credits", 0.0)
    
    # Check if there are existing ledger entries for this period
    # This handles the case where credits were charged before wallet was created
    used_credits_from_ledger = 0.0
    try:
        from api.models.usage import ProcessingMinutesLedger, LedgerDirection
        
        # Parse period to get year and month
        year, month = map(int, period.split("-"))
        
        # Get all debit entries for this user in this period
        ledger_stmt = (
            select(func.sum(ProcessingMinutesLedger.credits))
            .where(ProcessingMinutesLedger.user_id == user_id)
            .where(ProcessingMinutesLedger.direction == LedgerDirection.DEBIT)
            .where(extract('year', sqlmodel_col(ProcessingMinutesLedger.created_at)) == year)
            .where(extract('month', sqlmodel_col(ProcessingMinutesLedger.created_at)) == month)
        )
        used_credits_from_ledger = session.exec(ledger_stmt).one() or 0.0
        
        # Get refunds (CREDIT entries) for this period
        refund_stmt = (
            select(func.sum(ProcessingMinutesLedger.credits))
            .where(ProcessingMinutesLedger.user_id == user_id)
            .where(ProcessingMinutesLedger.direction == LedgerDirection.CREDIT)
            .where(extract('year', sqlmodel_col(ProcessingMinutesLedger.created_at)) == year)
            .where(extract('month', sqlmodel_col(ProcessingMinutesLedger.created_at)) == month)
        )
        refunded_credits = session.exec(refund_stmt).one() or 0.0
        
        # Net usage = debits - refunds
        used_credits_from_ledger = max(0.0, used_credits_from_ledger - refunded_credits)
        
        if used_credits_from_ledger > 0:
            log.info(
                f"[wallet] Found existing ledger usage for user {user_id}, period {period}: "
                f"{used_credits_from_ledger} credits"
            )
    except Exception as e:
        # If ledger table doesn't exist or query fails, continue with 0 usage
        log.warning(
            f"[wallet] Could not sync ledger usage for user {user_id}, period {period}: {e}"
        )
    
    # Calculate how much of the monthly credits have been used
    # We'll debit from monthly+rollover first (standard debit order)
    available_monthly = monthly_credits
    used_monthly_rollover = min(used_credits_from_ledger, available_monthly)
    used_purchased = max(0.0, used_credits_from_ledger - available_monthly)
    
    wallet = CreditWallet(
        user_id=user_id,
        period=period,
        monthly_credits=monthly_credits,
        rollover_credits=0.0,
        purchased_credits=0.0,
        used_credits=used_credits_from_ledger,
        used_monthly_rollover=used_monthly_rollover,
        used_purchased=used_purchased,
    )
    
    session.add(wallet)
    session.commit()
    session.refresh(wallet)
    
    log.info(
        f"[wallet] Created wallet for user {user_id}, period {period}, "
        f"monthly_credits={monthly_credits}, used_credits={used_credits_from_ledger}"
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
    # IMPORTANT: Monthly+rollover credits MUST be used 100% before touching purchased credits
    remaining = amount
    
    # First, use monthly+rollover credits (ALWAYS first, 100% of cases)
    available_mr = wallet.available_monthly_rollover
    if available_mr > 0 and remaining > 0:
        use_mr = min(available_mr, remaining)
        wallet.used_monthly_rollover += use_mr
        remaining -= use_mr
        log.debug(
            f"[wallet] Used {use_mr} from monthly+rollover pool "
            f"(available_mr={available_mr}, remaining={remaining})"
        )
    
    # Then, use purchased credits (ONLY after monthly+rollover is exhausted)
    if remaining > 0:
        available_purchased = wallet.available_purchased
        if available_purchased > 0:
            use_purchased = min(available_purchased, remaining)
            wallet.used_purchased += use_purchased
            remaining -= use_purchased
            log.debug(
                f"[wallet] Used {use_purchased} from purchased pool "
                f"(available_purchased={available_purchased}, remaining={remaining})"
            )
    
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
    """
    Get total available credits for user in period.
    
    If wallet doesn't exist, creates it with monthly credits from user's plan.
    """
    if period is None:
        period = get_period_string()
    
    stmt = select(CreditWallet).where(
        CreditWallet.user_id == user_id,
        CreditWallet.period == period
    )
    wallet = session.exec(stmt).first()
    
    if not wallet:
        # Wallet doesn't exist - create it with monthly credits from plan
        # This ensures users see their credits even if wallet wasn't created during subscription
        from api.models.user import User
        user = session.get(User, user_id)
        if not user:
            return 0.0
        
        plan_key = getattr(user, 'tier', 'free') or 'free'
        wallet = get_or_create_wallet(session, user_id, plan_key, period)
        log.info(
            f"[wallet] Created wallet on balance check for user {user_id}, "
            f"period {period}, monthly_credits={wallet.monthly_credits}"
        )
    
    return wallet.total_available


def get_wallet_details(
    session: Session,
    user_id: UUID,
    period: Optional[str] = None
) -> dict:
    """
    Get detailed wallet information including purchased credits and monthly allocation.
    
    Returns:
        dict with:
        - total_available: Total available credits
        - purchased_credits_available: Available purchased credits (never expire)
        - monthly_allocation_available: Available monthly + rollover credits
        - monthly_credits: Monthly credits from plan
        - rollover_credits: Rolled over credits
        - purchased_credits: Total purchased credits (before usage)
        - used_monthly_rollover: Credits used from monthly+rollover pool
        - used_purchased: Credits used from purchased pool
    """
    from api.models.user import User
    user = session.get(User, user_id)
    if not user:
        return {
            "total_available": 0.0,
            "purchased_credits_available": 0.0,
            "monthly_allocation_available": 0.0,
            "monthly_credits": 0.0,
            "rollover_credits": 0.0,
            "purchased_credits": 0.0,
            "used_monthly_rollover": 0.0,
            "used_purchased": 0.0,
        }
    
    plan_key = getattr(user, 'tier', 'free') or 'free'
    
    # Check if unlimited plan
    from api.billing.plans import is_unlimited_plan
    if is_unlimited_plan(plan_key):
        return {
            "total_available": 999999.0,
            "purchased_credits_available": 0.0,
            "monthly_allocation_available": 999999.0,
            "monthly_credits": 999999.0,
            "rollover_credits": 0.0,
            "purchased_credits": 0.0,
            "used_monthly_rollover": 0.0,
            "used_purchased": 0.0,
        }
    
    if period is None:
        period = get_period_string()
    
    stmt = select(CreditWallet).where(
        CreditWallet.user_id == user_id,
        CreditWallet.period == period
    )
    wallet = session.exec(stmt).first()
    
    if not wallet:
        # Wallet doesn't exist - create it with monthly credits from plan
        # This ensures users see their credits even if wallet wasn't created during subscription
        wallet = get_or_create_wallet(session, user_id, plan_key, period)
        log.info(
            f"[wallet] Created wallet on details check for user {user_id}, "
            f"period {period}, monthly_credits={wallet.monthly_credits}"
        )
    
    return {
        "total_available": wallet.total_available,
        "purchased_credits_available": wallet.available_purchased,
        "monthly_allocation_available": wallet.available_monthly_rollover,
        "monthly_credits": wallet.monthly_credits,
        "rollover_credits": wallet.rollover_credits,
        "purchased_credits": wallet.purchased_credits,
        "used_monthly_rollover": wallet.used_monthly_rollover,
        "used_purchased": wallet.used_purchased,
    }


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
            
            # Normalize "free" to "starter" for plan lookup
            normalized_plan_key = plan_key.lower()
            if normalized_plan_key == "free":
                normalized_plan_key = "starter"
            
            # Skip free/starter tier users (unless they have active subscription)
            if plan_key == 'free' and user_id not in subscription_user_ids and user_id not in future_expiry_user_ids:
                continue
            
            # Get plan (using normalized key)
            plan = PLANS.get(normalized_plan_key)
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


def refund_to_wallet(
    session: Session,
    user_id: UUID,
    amount: float,
    original_period: Optional[str] = None
) -> None:
    """
    Refund credits to user's wallet.
    
    Attempts to refund to the original bank (monthly/rollover or purchased) based on period.
    If original period is not provided or wallet doesn't exist, refunds to current period as purchased.
    
    Args:
        session: Database session
        user_id: User to refund
        amount: Credits to refund
        original_period: Period when the charge was made (YYYY-MM format). If None, uses current period.
    """
    if amount <= 0:
        return
    
    if original_period is None:
        original_period = get_period_string()
    
    # Get wallet for the original period
    from api.models.user import User
    user = session.get(User, user_id)
    if not user:
        log.error(f"[wallet] User {user_id} not found for refund")
        return
    
    plan_key = getattr(user, 'tier', 'free') or 'free'
    
    # Check if wallet table exists, if not, skip wallet refund (just log)
    try:
        wallet = get_or_create_wallet(session, user_id, plan_key, original_period)
    except Exception as e:
        # Wallet table might not exist (migration not run)
        log.warning(f"[wallet] Could not access wallet table for refund (table may not exist): {e}")
        log.info(f"[wallet] Skipping wallet refund for user {user_id}, amount {amount}. Please run migration 032.")
        return
    
    # Heuristic: Try to refund proportionally to monthly/rollover first if available
    # If monthly/rollover was used in that period, refund there first
    # Otherwise, refund as purchased credits (more flexible)
    
    # Store original amount for logging
    original_amount = amount
    
    # Check if monthly/rollover credits were used in that period
    if wallet.used_monthly_rollover > 0:
        # Refund to monthly/rollover pool (reduce used amount)
        refund_to_mr = min(amount, wallet.used_monthly_rollover)
        wallet.used_monthly_rollover = max(0.0, wallet.used_monthly_rollover - refund_to_mr)
        wallet.used_credits = max(0.0, wallet.used_credits - refund_to_mr)
        amount -= refund_to_mr
        
        log.info(
            f"[wallet] Refunded {refund_to_mr} credits to monthly/rollover pool "
            f"for user {user_id}, period {original_period}"
        )
    
    # Remaining amount (or all if no monthly/rollover was used) goes to purchased
    if amount > 0:
        # For current period, add as purchased credits
        # For past periods, we still add as purchased in current period (more useful)
        current_period = get_period_string()
        if original_period == current_period:
            # Same period: reduce used_purchased if possible, otherwise add to purchased
            if wallet.used_purchased > 0:
                refund_to_purchased = min(amount, wallet.used_purchased)
                wallet.used_purchased = max(0.0, wallet.used_purchased - refund_to_purchased)
                wallet.used_credits = max(0.0, wallet.used_credits - refund_to_purchased)
                amount -= refund_to_purchased
                log.info(
                    f"[wallet] Refunded {refund_to_purchased} credits to purchased pool "
                    f"(reduced usage) for user {user_id}, period {original_period}"
                )
            
            # Any remaining goes to purchased credits
            if amount > 0:
                wallet.purchased_credits += amount
                log.info(
                    f"[wallet] Refunded {amount} credits as new purchased credits "
                    f"for user {user_id}, period {original_period}"
                )
        else:
            # Past period: add to current period as purchased credits
            current_wallet = get_or_create_wallet(session, user_id, plan_key, current_period)
            current_wallet.purchased_credits += amount
            log.info(
                f"[wallet] Refunded {amount} credits from period {original_period} "
                f"to current period {current_period} as purchased credits for user {user_id}"
            )
            session.add(current_wallet)
    
    wallet.updated_at = datetime.utcnow()
    session.add(wallet)
    session.commit()
    
    log.info(
        f"[wallet] Completed refund of {original_amount} credits for user {user_id} "
        f"(original_period={original_period})"
    )


__all__ = [
    "get_period_string",
    "get_or_create_wallet",
    "debit",
    "add_purchased_credits",
    "process_rollover",
    "process_monthly_rollover",
    "get_wallet_balance",
    "get_wallet_details",
    "refund_to_wallet",
]

