from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy.orm import relationship
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional, List

# Forward reference to avoid circular import errors
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .user import User


class PromoCode(SQLModel, table=True):
    """Promo code model for tracking referral and promotional codes."""
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    code: str = Field(unique=True, index=True, max_length=50, description="Promo code string (case-insensitive)")
    description: Optional[str] = Field(default=None, description="Description of the promo code benefit")
    benefit_description: Optional[str] = Field(default=None, description="User-facing description of what benefit this code provides")
    is_active: bool = Field(default=True, description="Whether this promo code is currently active")
    usage_count: int = Field(default=0, description="Number of times this code has been used")
    max_uses: Optional[int] = Field(default=None, description="Maximum number of times this code can be used (None = unlimited)")
    expires_at: Optional[datetime] = Field(default=None, description="When this promo code expires (None = never expires)")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = Field(default=None, max_length=255, description="Email or identifier of who created this code")
    
    # Future: benefit_type could be used to specify what kind of benefit (discount, credits, tier_upgrade, etc.)
    benefit_type: Optional[str] = Field(default=None, max_length=50, description="Type of benefit (e.g., 'discount', 'credits', 'tier_upgrade')")
    benefit_value: Optional[str] = Field(default=None, max_length=255, description="Value of the benefit (e.g., '20%', '1000 credits', 'pro')")


class PromoCodeCreate(SQLModel):
    """Schema for creating a promo code."""
    code: str = Field(..., max_length=50)
    description: Optional[str] = None
    benefit_description: Optional[str] = None
    is_active: bool = True
    max_uses: Optional[int] = None
    expires_at: Optional[datetime] = None
    created_by: Optional[str] = None
    benefit_type: Optional[str] = None
    benefit_value: Optional[str] = None


class PromoCodeUpdate(SQLModel):
    """Schema for updating a promo code."""
    description: Optional[str] = None
    benefit_description: Optional[str] = None
    is_active: Optional[bool] = None
    max_uses: Optional[int] = None
    expires_at: Optional[datetime] = None
    benefit_type: Optional[str] = None
    benefit_value: Optional[str] = None


class PromoCodePublic(SQLModel):
    """Schema for returning promo code data to the client."""
    id: UUID
    code: str
    description: Optional[str] = None
    benefit_description: Optional[str] = None
    is_active: bool
    usage_count: int
    max_uses: Optional[int] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    benefit_type: Optional[str] = None
    benefit_value: Optional[str] = None

