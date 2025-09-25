from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlmodel import SQLModel, Field
from sqlalchemy import UniqueConstraint, Index, text


class LedgerDirection(str, Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class LedgerReason(str, Enum):
    PROCESS_AUDIO = "PROCESS_AUDIO"
    REFUND_ERROR = "REFUND_ERROR"
    MANUAL_ADJUST = "MANUAL_ADJUST"
    # Minutes charged for TTS generated assets saved to the media library (outside episode assembly)
    TTS_LIBRARY = "TTS_LIBRARY"


class ProcessingMinutesLedger(SQLModel, table=True):
    """
    Immutable ledger of processing minutes. Positive minutes are recorded with a direction:
    - DEBIT: charge minutes (e.g., processing audio)
    - CREDIT: refund minutes (e.g., system error, manual adjust)

    A partial uniqueness constraint prevents duplicate DEBIT entries with the same non-null
    correlation_id, providing idempotency for retried jobs.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: UUID = Field(index=True)
    episode_id: Optional[UUID] = Field(default=None, index=True)

    minutes: int = Field(description="Positive number of minutes for this entry")
    direction: LedgerDirection = Field(default=LedgerDirection.DEBIT)
    reason: LedgerReason = Field(default=LedgerReason.PROCESS_AUDIO)

    correlation_id: Optional[str] = Field(
        default=None,
        description="Idempotency key; for DEBIT rows this should be unique when provided",
        index=False,
    )
    notes: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Partial unique index for DEBIT rows with non-null correlation_id
    __table_args__ = (
        # SQLite supports partial indexes; use sqlite_where for conditional uniqueness
        Index(
            "uq_pml_debit_corr",
            "correlation_id",
            unique=True,
            sqlite_where=text("direction = 'DEBIT' AND correlation_id IS NOT NULL"),
        ),
        UniqueConstraint(
            "id",
            name="pk_processingminutesledger_id",
        ),
    )


__all__ = [
    "ProcessingMinutesLedger",
    "LedgerDirection",
    "LedgerReason",
]

# --- TTS usage tracking (for daily free quota and anti-spam heuristics) ---
from .podcast import MediaCategory  # late import to avoid circulars at module import time


class TTSUsage(SQLModel, table=True):
    """
    Track individual TTS generations (outside episode creation) for quota and guardrails.
    Stores both an estimate at request time and the actual duration we saved.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: UUID = Field(index=True)
    category: MediaCategory = Field(index=True)
    characters: int = Field(default=0)
    seconds_estimated: float = Field(default=0.0)
    seconds_actual: Optional[float] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


__all__.extend(["TTSUsage"]) 
