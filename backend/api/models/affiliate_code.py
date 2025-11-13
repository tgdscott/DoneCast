from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy.orm import relationship
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional

# Forward reference to avoid circular import errors
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .user import User


class UserAffiliateCode(SQLModel, table=True):
    """User-generated affiliate/referral code."""
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="user.id", unique=True, index=True, description="User who owns this affiliate code")
    code: str = Field(unique=True, index=True, max_length=50, description="Affiliate code (case-insensitive, auto-generated)")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationship to user (one-to-one: each affiliate code belongs to one user)
    user: Optional["User"] = Relationship(
        back_populates="affiliate_code", 
        sa_relationship=relationship("User", overlaps="affiliate_code")
    )


class UserAffiliateCodePublic(SQLModel):
    """Schema for returning affiliate code data to the client."""
    id: UUID
    code: str
    created_at: datetime
    referral_count: int = Field(default=0, description="Number of users who signed up using this code")
    referral_link: str = Field(description="Full referral link for sharing")


