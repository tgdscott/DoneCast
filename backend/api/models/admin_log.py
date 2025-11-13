from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlmodel import SQLModel, Field
from sqlalchemy import Index


class AdminActionType(str, Enum):
    """Types of admin actions that can be logged"""
    REFUND_APPROVED = "REFUND_APPROVED"
    REFUND_DENIED = "REFUND_DENIED"
    CREDIT_AWARDED = "CREDIT_AWARDED"


class AdminActionLog(SQLModel, table=True):
    """
    Log of admin actions for refunds and credit awards.
    
    Tracks:
    - Refund requests (approved/denied) with amounts
    - Credit awards (credits given away) with amounts and reasons
    """
    
    id: Optional[int] = Field(default=None, primary_key=True)
    action_type: AdminActionType = Field(index=True)
    admin_user_id: UUID = Field(description="Admin user who performed the action", index=True)
    target_user_id: UUID = Field(description="User who received/was denied the action", index=True)
    
    # Refund-specific fields
    refund_notification_id: Optional[UUID] = Field(default=None, description="Refund request notification ID")
    refund_amount: Optional[float] = Field(default=None, description="Credits refunded")
    refund_entry_ids: Optional[str] = Field(default=None, description="JSON array of ledger entry IDs refunded")
    denial_reason: Optional[str] = Field(default=None, description="Reason for denial if refund was denied")
    
    # Credit award-specific fields
    credit_amount: Optional[float] = Field(default=None, description="Credits awarded")
    award_reason: Optional[str] = Field(default=None, description="Reason for credit award")
    
    # Common fields
    notes: Optional[str] = Field(default=None, description="Additional notes")
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    
    __table_args__ = (
        Index("idx_admin_action_log_type_created", "action_type", "created_at"),
        Index("idx_admin_action_log_admin_created", "admin_user_id", "created_at"),
        Index("idx_admin_action_log_target_created", "target_user_id", "created_at"),
    )


__all__ = [
    "AdminActionLog",
    "AdminActionType",
]



