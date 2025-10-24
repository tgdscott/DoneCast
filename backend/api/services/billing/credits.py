"""
Credit charging service for usage-based billing.

Replaces hard-coded tier limits with flexible, per-action credit charges.
All features are available to all tiers - you just pay credits for what you use.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Optional
from datetime import datetime
from uuid import UUID

from sqlmodel import Session, select, func, col
from sqlalchemy import extract, case

from api.models.usage import ProcessingMinutesLedger, LedgerDirection, LedgerReason
from api.services import tier_service

if TYPE_CHECKING:
    from api.models.user import User

log = logging.getLogger(__name__)


# Credit cost rates (baseline, before multipliers)
BASE_CREDIT_RATE = 1.5  # 1 minute = 1.5 credits

# Feature-specific baseline rates
TRANSCRIPTION_RATE = 1.5  # Per minute of audio transcribed
TTS_GENERATION_RATE = 1.5  # Per minute of TTS generated
ASSEMBLY_BASE_COST = 5.0  # Flat cost per episode assembled
STORAGE_RATE_PER_GB_MONTH = 2.0  # Per GB per month


def get_user_credit_balance(session: Session, user_id: UUID) -> float:
    """
    Get user's current credit balance.
    
    Returns:
        Available credits (positive = have credits, negative = overdrawn)
    """
    # Get tier's monthly allocation
    from api.models.user import User
    user = session.get(User, user_id)
    if not user:
        return 0.0
    
    tier_credits = tier_service.get_tier_credits(session, getattr(user, 'tier', 'free') or 'free')
    
    # If unlimited tier, return large number
    if tier_credits is None:
        return 999999.0
    
    # Calculate used credits this month
    current_month = datetime.utcnow().month
    current_year = datetime.utcnow().year
    
    stmt = (
        select(func.sum(
            # DEBIT = subtract credits, CREDIT = add credits
            case(
                (ProcessingMinutesLedger.direction == LedgerDirection.DEBIT, -ProcessingMinutesLedger.credits),
                (ProcessingMinutesLedger.direction == LedgerDirection.CREDIT, ProcessingMinutesLedger.credits),
                else_=0
            )
        ))
        .where(ProcessingMinutesLedger.user_id == user_id)
        .where(extract('month', col(ProcessingMinutesLedger.created_at)) == current_month)
        .where(extract('year', col(ProcessingMinutesLedger.created_at)) == current_year)
    )
    
    used_credits = session.exec(stmt).one() or 0.0
    
    # Remaining = allocation - used (used is already negative for debits)
    return tier_credits + used_credits  # used is negative, so this subtracts


def check_sufficient_credits(
    session: Session,
    user: User,
    required_credits: float
) -> tuple[bool, float, str]:
    """
    Check if user has sufficient credits for an action.
    
    Returns:
        (has_sufficient, current_balance, message)
    """
    balance = get_user_credit_balance(session, user.id)
    
    if balance >= required_credits:
        return (True, balance, f"Sufficient credits: {balance:.1f} available, {required_credits:.1f} required")
    else:
        shortage = required_credits - balance
        return (False, balance, f"Insufficient credits: {balance:.1f} available, {required_credits:.1f} required (short {shortage:.1f})")


def charge_credits(
    session: Session,
    user_id: UUID,
    credits: float,
    reason: LedgerReason,
    episode_id: Optional[UUID] = None,
    notes: Optional[str] = None,
    cost_breakdown: Optional[dict] = None,
    correlation_id: Optional[str] = None
) -> ProcessingMinutesLedger:
    """
    Charge credits to a user's account.
    
    Args:
        session: Database session
        user_id: User to charge
        credits: Amount of credits to charge
        reason: Reason for the charge
        episode_id: Optional episode this relates to
        notes: Optional notes
        cost_breakdown: Optional dict with cost calculation details
        correlation_id: Optional idempotency key
    
    Returns:
        ProcessingMinutesLedger record
    """
    # Calculate equivalent minutes for legacy field (credits / 1.5)
    minutes = int(credits / BASE_CREDIT_RATE)
    
    # Create ledger entry
    entry = ProcessingMinutesLedger(
        user_id=user_id,
        episode_id=episode_id,
        minutes=minutes,
        credits=credits,
        direction=LedgerDirection.DEBIT,
        reason=reason,
        notes=notes,
        cost_breakdown_json=json.dumps(cost_breakdown) if cost_breakdown else None,
        correlation_id=correlation_id
    )
    
    session.add(entry)
    session.commit()
    session.refresh(entry)
    
    log.info(
        f"[credits] Charged {credits:.2f} credits to user {user_id} "
        f"(reason={reason.value}, episode={episode_id}, corr={correlation_id})"
    )
    
    return entry


def refund_credits(
    session: Session,
    user_id: UUID,
    credits: float,
    reason: LedgerReason,
    episode_id: Optional[UUID] = None,
    notes: Optional[str] = None
) -> ProcessingMinutesLedger:
    """
    Refund credits to a user's account.
    
    Returns:
        ProcessingMinutesLedger record
    """
    minutes = int(credits / BASE_CREDIT_RATE)
    
    entry = ProcessingMinutesLedger(
        user_id=user_id,
        episode_id=episode_id,
        minutes=minutes,
        credits=credits,
        direction=LedgerDirection.CREDIT,  # CREDIT = refund
        reason=reason,
        notes=notes
    )
    
    session.add(entry)
    session.commit()
    session.refresh(entry)
    
    log.info(
        f"[credits] Refunded {credits:.2f} credits to user {user_id} "
        f"(reason={reason.value}, episode={episode_id})"
    )
    
    return entry


def charge_for_tts_generation(
    session: Session,
    user: User,
    duration_seconds: float,
    use_elevenlabs: bool = False,
    episode_id: Optional[UUID] = None,
    notes: Optional[str] = None
) -> tuple[ProcessingMinutesLedger, dict]:
    """
    Charge credits for TTS generation (intros, outros, etc.).
    
    Args:
        session: Database session
        user: User to charge
        duration_seconds: Duration of generated TTS in seconds
        use_elevenlabs: Whether ElevenLabs was used (higher cost)
        episode_id: Optional episode this TTS is for
        notes: Optional notes
    
    Returns:
        (ledger_entry, cost_breakdown)
    """
    duration_minutes = duration_seconds / 60.0
    
    # Calculate cost with tier-specific multipliers
    cost_calc = tier_service.calculate_processing_cost(
        session=session,
        user=user,
        audio_duration_minutes=0,  # No main audio for TTS
        use_elevenlabs_tts=use_elevenlabs,
        tts_duration_minutes=duration_minutes
    )
    
    credits = cost_calc['tts_credits']
    
    breakdown = {
        'duration_seconds': duration_seconds,
        'duration_minutes': duration_minutes,
        'base_rate': TTS_GENERATION_RATE,
        'provider': 'elevenlabs' if use_elevenlabs else 'standard',
        'multiplier': cost_calc['multipliers']['elevenlabs'],
        'total_credits': credits
    }
    
    entry = charge_credits(
        session=session,
        user_id=user.id,
        credits=credits,
        reason=LedgerReason.TTS_GENERATION,
        episode_id=episode_id,
        notes=notes or f"TTS generation ({duration_seconds:.1f}s, {cost_calc['tts_provider']})",
        cost_breakdown=breakdown
    )
    
    return entry, breakdown


def charge_for_transcription(
    session: Session,
    user: User,
    duration_minutes: float,
    use_auphonic: bool = False,
    episode_id: Optional[UUID] = None,
    correlation_id: Optional[str] = None
) -> tuple[ProcessingMinutesLedger, dict]:
    """
    Charge credits for audio transcription.
    
    Args:
        session: Database session
        user: User to charge
        duration_minutes: Duration of audio transcribed in minutes
        use_auphonic: Whether Auphonic was used (higher cost than AssemblyAI)
        episode_id: Episode being transcribed
        correlation_id: Idempotency key (prevents double-charging on retries)
    
    Returns:
        (ledger_entry, cost_breakdown)
    """
    # Calculate cost with tier-specific multipliers
    cost_calc = tier_service.calculate_processing_cost(
        session=session,
        user=user,
        audio_duration_minutes=duration_minutes,
        use_auphonic=use_auphonic
    )
    
    credits = cost_calc['audio_credits']
    
    breakdown = {
        'duration_minutes': duration_minutes,
        'base_rate': TRANSCRIPTION_RATE,
        'pipeline': cost_calc['pipeline'],
        'multiplier': cost_calc['multipliers'].get('auphonic'),
        'total_credits': credits
    }
    
    entry = charge_credits(
        session=session,
        user_id=user.id,
        credits=credits,
        reason=LedgerReason.TRANSCRIPTION,
        episode_id=episode_id,
        notes=f"Transcription ({duration_minutes:.1f} min, {cost_calc['pipeline']})",
        cost_breakdown=breakdown,
        correlation_id=correlation_id
    )
    
    return entry, breakdown


def charge_for_assembly(
    session: Session,
    user: User,
    episode_id: UUID,
    total_duration_minutes: float,
    use_auphonic: bool = False,
    correlation_id: Optional[str] = None
) -> tuple[ProcessingMinutesLedger, dict]:
    """
    Charge credits for episode assembly (assembling all segments into final episode).
    
    Args:
        session: Database session
        user: User to charge
        episode_id: Episode being assembled
        total_duration_minutes: Total duration of final episode
        use_auphonic: Whether Auphonic processing was used
        correlation_id: Idempotency key
    
    Returns:
        (ledger_entry, cost_breakdown)
    """
    # Base assembly cost + per-minute cost
    base_cost = ASSEMBLY_BASE_COST
    duration_cost = total_duration_minutes * 0.5  # 0.5 credits per minute for assembly
    
    # Auphonic adds extra cost
    if use_auphonic:
        tier_config = tier_service.get_tier_config(session, getattr(user, 'tier', 'free') or 'free')
        multiplier = tier_config.get('auphonic_cost_multiplier', 2.0)
        total_credits = (base_cost + duration_cost) * multiplier
    else:
        multiplier = 1.0
        total_credits = base_cost + duration_cost
    
    breakdown = {
        'base_cost': base_cost,
        'duration_minutes': total_duration_minutes,
        'duration_cost': duration_cost,
        'pipeline': 'auphonic' if use_auphonic else 'assemblyai',
        'multiplier': multiplier,
        'total_credits': total_credits
    }
    
    entry = charge_credits(
        session=session,
        user_id=user.id,
        credits=total_credits,
        reason=LedgerReason.ASSEMBLY,
        episode_id=episode_id,
        notes=f"Episode assembly ({total_duration_minutes:.1f} min, {'Auphonic' if use_auphonic else 'Standard'})",
        cost_breakdown=breakdown,
        correlation_id=correlation_id
    )
    
    return entry, breakdown


def charge_for_storage(
    session: Session,
    user: User,
    storage_gb: float,
    notes: Optional[str] = None
) -> tuple[ProcessingMinutesLedger, dict]:
    """
    Charge credits for cloud storage usage (monthly).
    
    Args:
        session: Database session
        user: User to charge
        storage_gb: Storage used in gigabytes
        notes: Optional notes
    
    Returns:
        (ledger_entry, cost_breakdown)
    """
    credits = storage_gb * STORAGE_RATE_PER_GB_MONTH
    
    breakdown = {
        'storage_gb': storage_gb,
        'rate_per_gb': STORAGE_RATE_PER_GB_MONTH,
        'total_credits': credits
    }
    
    entry = charge_credits(
        session=session,
        user_id=user.id,
        credits=credits,
        reason=LedgerReason.STORAGE,
        notes=notes or f"Storage usage ({storage_gb:.2f} GB)",
        cost_breakdown=breakdown
    )
    
    return entry, breakdown


__all__ = [
    "get_user_credit_balance",
    "check_sufficient_credits",
    "charge_credits",
    "refund_credits",
    "charge_for_tts_generation",
    "charge_for_transcription",
    "charge_for_assembly",
    "charge_for_storage",
    "BASE_CREDIT_RATE",
    "TRANSCRIPTION_RATE",
    "TTS_GENERATION_RATE",
    "ASSEMBLY_BASE_COST",
    "STORAGE_RATE_PER_GB_MONTH",
]
