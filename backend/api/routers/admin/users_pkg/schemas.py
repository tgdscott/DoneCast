from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import UUID

from pydantic import BaseModel, Field

class RefundRequestResponse(BaseModel):
    """Refund request item for admin view"""
    notification_id: str
    user_id: str
    user_email: str
    episode_id: Optional[str] = None
    ledger_entry_ids: List[int] = []
    reason: str
    notes: Optional[str] = None
    created_at: datetime
    read_at: Optional[datetime] = None

class UserAdminOut(BaseModel):
    id: str
    email: str
    tier: Optional[str]
    is_active: bool
    created_at: str
    episode_count: int
    last_activity: Optional[str] = None
    subscription_expires_at: Optional[str] = None
    last_login: Optional[str] = None
    email_verified: bool = False  # NEW: Track email verification status

class UserAdminUpdate(BaseModel):
    tier: Optional[str] = None
    is_active: Optional[bool] = None
    subscription_expires_at: Optional[str] = None

class RefundCreditsRequest(BaseModel):
    ledger_entry_ids: List[int]
    notes: Optional[str] = None
    manual_credits: Optional[float] = Field(None, description="Optional manual refund amount. If provided, refunds this amount as a single adjustment instead of per-entry refunds.")

class AwardCreditsRequest(BaseModel):
    credits: float
    reason: str
    notes: Optional[str] = None

class DenyRefundRequest(BaseModel):
    """Request to deny a refund"""
    notification_id: str
    denial_reason: str = Field(..., min_length=10, description="Reason for denial (minimum 10 characters)")

class LedgerEntryDetail(BaseModel):
    """Detailed ledger entry for refund analysis"""
    id: int
    timestamp: datetime
    direction: str  # DEBIT or CREDIT
    reason: str
    credits: float
    minutes: int
    notes: Optional[str] = None
    cost_breakdown: Optional[Dict[str, Any]] = None
    correlation_id: Optional[str] = None
    credit_source: Optional[str] = None  # "monthly", "add-on", "rollover"
    episode_id: Optional[str] = None
    episode_title: Optional[str] = None
    can_refund: bool = True  # Whether this entry can be refunded (not already refunded)
    already_refunded: bool = False  # Whether this entry has already been refunded
    refund_status: Optional[str] = None  # "pending", "approved", "denied"
    service_delivered: Optional[bool] = None  # Whether the service was actually delivered (episode processed, TTS generated, etc.)
    service_details: Optional[Dict[str, Any]] = None  # Details about what was delivered

class EpisodeRefundDetail(BaseModel):
    """Comprehensive episode information for refund decision"""
    id: str
    title: str
    status: str
    created_at: datetime
    processed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    episode_number: Optional[int] = None
    season_number: Optional[int] = None
    podcast_title: Optional[str] = None
    has_final_audio: bool = False
    is_published: bool = False
    is_published_to_spreaker: bool = False
    spreaker_episode_id: Optional[str] = None
    error_message: Optional[str] = None
    spreaker_publish_error: Optional[str] = None
    spreaker_publish_error_detail: Optional[str] = None
    auphonic_processed: bool = False
    auphonic_error: Optional[str] = None
    gcs_audio_path: Optional[str] = None
    final_audio_path: Optional[str] = None
    audio_file_size: Optional[int] = None
    show_notes: Optional[str] = None
    brief_summary: Optional[str] = None
    episode_tags: Optional[List[str]] = None
    episode_chapters: Optional[List[Dict[str, Any]]] = None
    # Charges for this episode in the refund request
    ledger_entries: List[LedgerEntryDetail]
    total_credits_requested: float
    total_credits_already_refunded: float
    net_credits_to_refund: float
    # Service delivery status
    service_delivered: bool
    can_be_restored: bool
    refund_recommendation: Optional[str] = None  # "full_refund", "partial_refund", "no_refund", "conditional_refund"

class UserRefundContext(BaseModel):
    """User context for refund decision"""
    user_id: str
    email: str
    tier: Optional[str] = None
    account_created_at: datetime
    is_active: bool
    subscription_expires_at: Optional[datetime] = None
    total_credits_used_all_time: float = 0.0
    total_credits_used_this_month: float = 0.0
    current_credit_balance: float = 0.0
    monthly_credit_allocation: Optional[float] = None
    previous_refund_count: int = 0
    previous_refund_total_credits: float = 0.0
    last_refund_date: Optional[datetime] = None

class RefundRequestDetail(BaseModel):
    """Comprehensive refund request detail for admin decision-making"""
    # Request basics
    notification_id: str
    request_created_at: datetime
    request_read_at: Optional[datetime] = None
    user_reason: str
    user_notes: Optional[str] = None
    
    # User context
    user: UserRefundContext
    
    # Episodes with refund requests (grouped by episode)
    episodes: List[EpisodeRefundDetail] = []
    
    # Non-episode charges (TTS library, storage, etc. - not tied to an episode)
    non_episode_charges: List[LedgerEntryDetail] = []
    
    # Summary totals
    total_credits_requested: float
    total_credits_already_refunded: float
    net_credits_to_refund: float
    
    # Time analysis
    days_since_charges: float
    hours_since_request: float
    
    # Business context
    refund_eligibility_notes: List[str] = []
    credit_source_breakdown: Dict[str, float] = {}  # "monthly": 100.0, "add-on": 50.0

class RefundLogEntry(BaseModel):
    """Refund log entry for admin view"""
    id: int
    action_type: str
    admin_email: str
    target_user_email: str
    target_user_id: str
    refund_amount: Optional[float] = None
    refund_entry_ids: Optional[List[int]] = None
    denial_reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

class CreditAwardLogEntry(BaseModel):
    """Credit award log entry for admin view"""
    id: int
    action_type: str
    admin_email: str
    target_user_email: str
    target_user_id: str
    credit_amount: Optional[float] = None
    award_reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
