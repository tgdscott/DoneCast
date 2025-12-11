from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy.orm import relationship
from pydantic import EmailStr
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional, List

# Forward reference to avoid circular import errors
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .podcast import PodcastTemplate

class UserBase(SQLModel):
    """Base model with shared fields."""
    email: EmailStr = Field(unique=True, index=True)
    is_active: bool = True
    google_id: Optional[str] = Field(default=None, unique=True)
    tier: str = Field(default="trial")
    spreaker_access_token: Optional[str] = Field(default=None)
    spreaker_refresh_token: Optional[str] = Field(default=None)
    stripe_customer_id: Optional[str] = Field(default=None, index=True)
    # Per-user ElevenLabs API key
    elevenlabs_api_key: Optional[str] = Field(default=None, description="User-provided ElevenLabs API key for TTS")
    # JSON-encoded user-level audio cleanup & command settings (serialized externally)
    audio_cleanup_settings_json: Optional[str] = Field(default=None, description="User-level settings for silence/filler removal and command keywords")
    # Preferred audio pipeline (advanced mastering vs standard)
    use_advanced_audio_processing: bool = Field(
        default=False,
        description="If True, route uploads through the advanced mastering pipeline instead of AssemblyAI-only flow",
    )
    audio_processing_threshold_label: Optional[str] = Field(
        default="very_bad",
        max_length=50,
        description="Quality threshold for triggering advanced audio processing. "
                    "Valid values: 'good', 'slightly_bad', 'fairly_bad', 'very_bad', 'incredibly_bad', 'abysmal'. "
                    "Default 'very_bad' routes top 3 quality levels to standard, bottom 3 to advanced processing.",
    )
    # Optional profile personalization fields
    first_name: Optional[str] = Field(default=None, max_length=80, description="User given name for personalization")
    last_name: Optional[str] = Field(default=None, max_length=120, description="User family name")
    timezone: Optional[str] = Field(default=None, description="IANA timezone string for scheduling display")
    # Role field for admin/superadmin access (distinct from tier which is for billing)
    role: Optional[str] = Field(default=None, max_length=50, description="User role: 'admin', 'superadmin', or None for regular users")
    # SMS notification preferences
    phone_number: Optional[str] = Field(default=None, max_length=20, description="User phone number for SMS notifications (E.164 format)")
    sms_notifications_enabled: bool = Field(default=False, description="Master toggle for SMS notifications")
    sms_notify_transcription_ready: bool = Field(default=False, description="Notify user when episode is ready to assemble (after transcription)")
    sms_notify_publish: bool = Field(default=False, description="Notify user when episode is published or scheduled")
    sms_notify_worker_down: bool = Field(default=False, description="Notify admin when worker server is down")
    # Promo code used at signup
    promo_code_used: Optional[str] = Field(default=None, max_length=50, index=True, description="Promo code used during registration")
    # Speed adjustment factors for length management (values like 1.05 for 5% speedup)
    speed_up_factor: float = Field(default=1.05, ge=1.0, le=1.25, description="Speed factor for lengthening episodes (1.0-1.25)")
    slow_down_factor: float = Field(default=0.95, ge=0.75, lt=1.0, description="Speed factor for shortening episodes (0.75-1.0)")

class User(UserBase, table=True):
    """The database model for a User."""
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    subscription_expires_at: Optional[datetime] = Field(default=None, description="When the paid subscription ends")
    # Nullable last_login; populated on successful auth events
    last_login: Optional[datetime] = Field(default=None, description="Timestamp of last successful login")
    terms_version_accepted: Optional[str] = Field(default=None, max_length=64, description="App terms version the user last accepted")
    terms_accepted_at: Optional[datetime] = Field(default=None, description="When the user accepted the current terms")
    terms_accepted_ip: Optional[str] = Field(default=None, max_length=64, description="IP address at latest acceptance")
    is_admin: bool = Field(default=False, description="Whether this user has admin privileges (legacy field, use role field instead)")
    
    # Soft deletion fields for user self-deletion with grace period
    deletion_requested_at: Optional[datetime] = Field(default=None, description="When deletion was requested (user or admin)")
    deletion_scheduled_for: Optional[datetime] = Field(default=None, description="When actual deletion will occur (after grace period)")
    deletion_requested_by: Optional[str] = Field(default=None, max_length=10, description="'user' or 'admin' - determines if admin notification sent")
    deletion_reason: Optional[str] = Field(default=None, description="Optional reason provided by user")
    is_deleted_view: bool = Field(default=False, description="User-facing deleted state - blocks login, appears deleted to user")
    # Referrer user ID (user who referred this user via affiliate code)
    referred_by_user_id: Optional[UUID] = Field(default=None, foreign_key="user.id", index=True, description="User who referred this user")
    # Free trial fields
    trial_started_at: Optional[datetime] = Field(default=None, description="When the free trial started (when user completed wizard)")
    trial_expires_at: Optional[datetime] = Field(default=None, index=True, description="When the free trial expires")

    # This creates the link back to the templates that belong to this user
    templates: List["PodcastTemplate"] = Relationship(back_populates="user")
    terms_acceptances: List["UserTermsAcceptance"] = Relationship(back_populates="user")
    # Affiliate code relationship (one-to-one: each user can have one affiliate code)
    affiliate_code: Optional["UserAffiliateCode"] = Relationship(
        back_populates="user", 
        sa_relationship=relationship("UserAffiliateCode", uselist=False, overlaps="user")
    )

class UserCreate(UserBase):
    """Schema for creating a new user (registration)."""
    password: str = Field(..., min_length=8)

class UserPublic(UserBase):
    """Schema for returning user data to the client (omits password)."""
    id: UUID
    created_at: datetime
    last_login: Optional[datetime] = None
    terms_version_accepted: Optional[str] = None
    terms_accepted_at: Optional[datetime] = None
    terms_version_required: Optional[str] = None
    # Admin flags exposed for frontend gating
    is_admin: bool = Field(default=False, description="Whether this user has admin privileges")
    # role field inherited from UserBase

class UserTermsAcceptance(SQLModel, table=True):
    """Audit log of terms of use acceptance events."""
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    version: str = Field(max_length=64, index=True)
    accepted_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    ip_address: Optional[str] = Field(default=None, max_length=64)
    user_agent: Optional[str] = Field(default=None, max_length=512)

    user: Optional[User] = Relationship(back_populates="terms_acceptances", sa_relationship=relationship("User"))
