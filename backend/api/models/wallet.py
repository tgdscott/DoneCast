"""
Credit wallet model for tracking monthly, purchased, and rollover credits.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import SQLModel, Field, UniqueConstraint


class CreditWallet(SQLModel, table=True):
    """
    Tracks user's credit wallet per billing period.
    
    Each user has one wallet per billing period (monthly).
    Credits are debited in order: monthly + rollover, then purchased.
    """
    
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(index=True, foreign_key="user.id")
    
    # Billing period (YYYY-MM format)
    period: str = Field(index=True, description="Billing period in YYYY-MM format")
    
    # Credit allocations
    monthly_credits: float = Field(default=0.0, description="Monthly credits from plan")
    rollover_credits: float = Field(default=0.0, description="Rolled over from previous period (up to 10%)")
    purchased_credits: float = Field(default=0.0, description="Purchased credits (never expire, transferable)")
    
    # Usage tracking
    used_credits: float = Field(default=0.0, description="Total credits used this period")
    used_monthly_rollover: float = Field(default=0.0, description="Credits used from monthly+rollover pool")
    used_purchased: float = Field(default=0.0, description="Credits used from purchased pool")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Unique constraint: one wallet per user per period
    __table_args__ = (
        UniqueConstraint("user_id", "period", name="uq_wallet_user_period"),
    )
    
    @property
    def available_monthly_rollover(self) -> float:
        """Available credits from monthly + rollover pool."""
        total = self.monthly_credits + self.rollover_credits
        return max(0.0, total - self.used_monthly_rollover)
    
    @property
    def available_purchased(self) -> float:
        """Available purchased credits."""
        return max(0.0, self.purchased_credits - self.used_purchased)
    
    @property
    def total_available(self) -> float:
        """Total available credits (monthly+rollover + purchased)."""
        return self.available_monthly_rollover + self.available_purchased
    
    @property
    def unused_monthly_rollover(self) -> float:
        """Unused monthly+rollover credits (for rollover calculation)."""
        total = self.monthly_credits + self.rollover_credits
        return max(0.0, total - self.used_monthly_rollover)


class WalletPeriodProcessed(SQLModel, table=True):
    """
    Tracks which billing periods have been processed for rollover.
    
    Used for idempotency - prevents double-processing the same period.
    """
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    period: str = Field(unique=True, index=True, description="Billing period in YYYY-MM format")
    processed_at: datetime = Field(default_factory=datetime.utcnow)
    processed_count: int = Field(default=0, description="Number of users processed")
    rollover_total: float = Field(default=0.0, description="Total credits rolled over")
    
    __table_args__ = (
        UniqueConstraint("period", name="uq_wallet_period_processed"),
    )


__all__ = ["CreditWallet", "WalletPeriodProcessed"]

