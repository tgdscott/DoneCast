"""
Credit charging service for usage-based billing.

Replaces hard-coded tier limits with flexible, per-action credit charges.
All features are available to all tiers - you just pay credits for what you use.
"""
from __future__ import annotations

import json
import logging
import math
from typing import TYPE_CHECKING, Optional
from datetime import datetime
from uuid import UUID

from sqlmodel import Session, select, func, col
from sqlalchemy import extract, case

from api.models.usage import ProcessingMinutesLedger, LedgerDirection, LedgerReason
from api.services import tier_service
from api.billing.plans import RATES, RATES_ELEVENLABS, get_elevenlabs_rate, get_ai_metadata_rate
from api.services.billing.wallet import debit as wallet_debit, get_wallet_balance

if TYPE_CHECKING:
    from api.models.user import User

log = logging.getLogger(__name__)


# Credit cost rates (baseline, before multipliers)
BASE_CREDIT_RATE = 1.0  # 1 minute = 1 credit

# Feature-specific baseline rates (legacy, kept for backward compatibility)
TRANSCRIPTION_RATE = 1.0  # Per minute of audio transcribed
TTS_GENERATION_RATE = 1.0  # Per minute of TTS generated
ASSEMBLY_BASE_COST = 5.0  # Flat cost per episode assembled
STORAGE_RATE_PER_GB_MONTH = 2.0  # Per GB per month


def get_user_credit_balance(session: Session, user_id: UUID) -> float:
    """
    Get user's current credit balance from wallet.
    
    Returns:
        Available credits (positive = have credits, negative = overdrawn)
    """
    from api.models.user import User
    user = session.get(User, user_id)
    if not user:
        return 0.0
    
    plan_key = getattr(user, 'tier', 'free') or 'free'
    
    # Check if unlimited plan
    from api.billing.plans import is_unlimited_plan
    if is_unlimited_plan(plan_key):
        return 999999.0
    
    # Get balance from wallet
    return get_wallet_balance(session, user_id)


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
    
    Uses wallet system for debit ordering (monthly+rollover first, then purchased).
    Also creates ledger entry for audit trail.
    
    Args:
        session: Database session
        user_id: User to charge
        credits: Amount of credits to charge
        reason: Reason for the charge
        episode_id: Optional episode this relates to
        notes: Optional notes
        cost_breakdown: Optional dict with cost calculation details
        correlation_id: Optional idempotency key - if provided and already exists, returns existing entry
    
    Returns:
        ProcessingMinutesLedger record
    """
    # Idempotency check: if correlation_id provided, check if already exists
    if correlation_id:
        stmt = select(ProcessingMinutesLedger).where(
            ProcessingMinutesLedger.correlation_id == correlation_id
        )
        existing = session.exec(stmt).first()
        if existing:
            log.info(
                f"[credits] Charge already exists for correlation_id={correlation_id}, "
                f"returning existing entry (idempotent retry)"
            )
            return existing
    
    # Debit from wallet (handles debit ordering: monthly+rollover first, then purchased)
    wallet_debit(
        session=session,
        user_id=user_id,
        amount=credits,
        reason=reason.value,
        metadata=cost_breakdown,
        request_id=correlation_id
    )
    
    # Calculate equivalent minutes for legacy field
    minutes = int(credits / BASE_CREDIT_RATE)
    
    # Create ledger entry for audit trail
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
    
    For ElevenLabs: rounds up to next whole second before charging.
    Example: 3.2s → 4s
    
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
    return charge_for_tts_batch(
        session=session,
        user=user,
        durations_seconds=[duration_seconds],
        use_elevenlabs=use_elevenlabs,
        episode_id=episode_id,
        notes=notes
    )


def charge_for_tts_batch(
    session: Session,
    user: User,
    durations_seconds: list[float],
    use_elevenlabs: bool = False,
    episode_id: Optional[UUID] = None,
    notes: Optional[str] = None
) -> tuple[ProcessingMinutesLedger, dict]:
    """
    Charge credits for multiple TTS clips generated in one job.
    
    For ElevenLabs: sums all durations first, then rounds up to next whole second.
    Example: [1.2s, 2.1s] → 3.3s total → 4s billed
    
    Args:
        session: Database session
        user: User to charge
        durations_seconds: List of durations for each TTS clip in seconds
        use_elevenlabs: Whether ElevenLabs was used (higher cost)
        episode_id: Optional episode this TTS is for
        notes: Optional notes
    
    Returns:
        (ledger_entry, cost_breakdown)
    """
    plan_key = getattr(user, 'tier', 'free') or 'free'
    
    # Sum all durations first
    raw_seconds = sum(durations_seconds)
    
    if use_elevenlabs:
        # Round up to next whole second for ElevenLabs (after summing)
        billed_seconds = math.ceil(raw_seconds)
        rate_per_sec = get_elevenlabs_rate(plan_key)
        credits = billed_seconds * rate_per_sec
        provider = 'elevenlabs'
    else:
        # Standard TTS: 1 credit per second (no rounding)
        billed_seconds = raw_seconds
        rate_per_sec = 1
        credits = billed_seconds * rate_per_sec
        provider = 'standard'
    
    # Build metadata with required fields
    breakdown = {
        'provider': provider,
        'raw_seconds': raw_seconds,
        'billed_seconds': billed_seconds,
        'rate_per_sec': rate_per_sec,
        'total_credits': credits,
        'clip_count': len(durations_seconds),
        'durations': durations_seconds if len(durations_seconds) <= 10 else None  # Only include if reasonable size
    }
    
    # Build notes
    if notes is None:
        if len(durations_seconds) == 1:
            notes = f"TTS generation ({raw_seconds:.1f}s → {billed_seconds}s billed, {provider})"
        else:
            notes = f"TTS batch: {len(durations_seconds)} clips ({raw_seconds:.1f}s → {billed_seconds}s billed, {provider})"
    
    entry = charge_credits(
        session=session,
        user_id=user.id,
        credits=credits,
        reason=LedgerReason.TTS_GENERATION,
        episode_id=episode_id,
        notes=notes,
        cost_breakdown=breakdown
    )
    
    return entry, breakdown


def charge_for_transcription(
    session: Session,
    user: User,
    duration_seconds: float,
    use_auphonic: bool = False,
    episode_id: Optional[UUID] = None,
    correlation_id: Optional[str] = None
) -> tuple[ProcessingMinutesLedger, dict]:
    """
    Charge credits for audio transcription/processing.
    
    Rate: 1 credit per second (processing_per_sec)
    Auphonic add-on: additional 1 credit per second (configurable via AUPHONIC_CREDITS_PER_SEC)
    
    Args:
        session: Database session
        user: User to charge
        duration_seconds: Duration of audio processed in seconds
        use_auphonic: Whether Auphonic add-on was used
        episode_id: Episode being transcribed
        correlation_id: Idempotency key (prevents double-charging on retries)
    
    Returns:
        (ledger_entry, cost_breakdown)
    """
    # Base processing rate: 1 credit per second
    processing_rate = RATES["processing_per_sec"]
    base_credits = duration_seconds * processing_rate
    
    # Auphonic add-on: additional credits per second
    auphonic_credits = 0.0
    if use_auphonic:
        auphonic_rate = RATES["auphonic_per_sec"]
        auphonic_credits = duration_seconds * auphonic_rate
    
    total_credits = base_credits + auphonic_credits
    
    breakdown = {
        'duration_seconds': duration_seconds,
        'processing_rate_per_sec': processing_rate,
        'base_credits': base_credits,
        'use_auphonic': use_auphonic,
        'auphonic_rate_per_sec': RATES["auphonic_per_sec"] if use_auphonic else 0,
        'auphonic_credits': auphonic_credits,
        'total_credits': total_credits
    }
    
    entry = charge_credits(
        session=session,
        user_id=user.id,
        credits=total_credits,
        reason=LedgerReason.TRANSCRIPTION,
        episode_id=episode_id,
        notes=f"Processing ({duration_seconds:.1f}s, {'with Auphonic' if use_auphonic else 'standard'})",
        cost_breakdown=breakdown,
        correlation_id=correlation_id
    )
    
    return entry, breakdown


def charge_for_assembly(
    session: Session,
    user: User,
    episode_id: UUID,
    total_duration_seconds: float,
    use_auphonic: bool = False,
    correlation_id: Optional[str] = None
) -> tuple[ProcessingMinutesLedger, dict]:
    """
    Charge credits for episode assembly (assembling all segments into final episode).
    
    Rate: 3 credits per second (assembly_per_sec)
    
    Args:
        session: Database session
        user: User to charge
        episode_id: Episode being assembled
        total_duration_seconds: Total duration of final episode in seconds
        use_auphonic: Whether Auphonic processing was used (doesn't affect assembly rate)
        correlation_id: Idempotency key
    
    Returns:
        (ledger_entry, cost_breakdown)
    """
    # Assembly rate: 3 credits per second
    assembly_rate = RATES["assembly_per_sec"]
    total_credits = total_duration_seconds * assembly_rate
    
    breakdown = {
        'duration_seconds': total_duration_seconds,
        'assembly_rate_per_sec': assembly_rate,
        'total_credits': total_credits
    }
    
    entry = charge_credits(
        session=session,
        user_id=user.id,
        credits=total_credits,
        reason=LedgerReason.ASSEMBLY,
        episode_id=episode_id,
        notes=f"Episode assembly ({total_duration_seconds:.1f}s)",
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


def charge_for_ai_metadata(
    session: Session,
    user: User,
    metadata_type: str,
    episode_id: Optional[UUID] = None,
    notes: Optional[str] = None,
    correlation_id: Optional[str] = None,
    provider: Optional[str] = None
) -> ProcessingMinutesLedger:
    """
    Charge credits for AI-generated metadata (title, description, tags).
    
    Args:
        session: Database session
        user: User to charge
        metadata_type: Type of metadata ("title", "description", "notes", "tags")
        episode_id: Optional episode this is for
        notes: Optional notes (will be auto-generated if not provided)
        correlation_id: Optional idempotency key (prevents double-charging)
        provider: Optional AI provider name (e.g., "gemini", "groq") for metadata
    
    Returns:
        Ledger entry
    
    Raises:
        ValueError: If insufficient credits (for non-unlimited plans)
    """
    from api.billing.plans import get_ai_metadata_rate
    
    # Get rate for this metadata type
    credits = get_ai_metadata_rate(metadata_type)
    
    # Generate default notes if not provided
    if notes is None:
        metadata_label = metadata_type.replace("_", " ").title()
        notes = f"AI {metadata_label} generation"
    
    # Build cost breakdown metadata
    cost_breakdown = {
        "type": "ai_metadata",
        "metadata_type": metadata_type.lower(),
        "provider": provider or "unknown",
        "credits_charged": credits
    }
    
    # Generate correlation ID if not provided (for idempotency)
    if correlation_id is None:
        import time
        timestamp = int(time.time() * 1000)  # milliseconds
        correlation_id = f"ai_{metadata_type}_{episode_id or 'none'}_{timestamp}"
    
    # Charge credits
    entry = charge_credits(
        session=session,
        user_id=user.id,
        credits=credits,
        reason=LedgerReason.AI_METADATA_GENERATION,
        episode_id=episode_id,
        notes=notes,
        cost_breakdown=cost_breakdown,
        correlation_id=correlation_id
    )
    
    return entry


__all__ = [
    "get_user_credit_balance",
    "check_sufficient_credits",
    "charge_credits",
    "refund_credits",
    "charge_for_tts_generation",
    "charge_for_transcription",
    "charge_for_assembly",
    "charge_for_storage",
    "charge_for_ai_metadata",
    "BASE_CREDIT_RATE",
    "TRANSCRIPTION_RATE",
    "TTS_GENERATION_RATE",
    "ASSEMBLY_BASE_COST",
    "STORAGE_RATE_PER_GB_MONTH",
]
