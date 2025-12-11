from sqlmodel import SQLModel, Field
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional

class AffiliateProgramSettings(SQLModel, table=True):
    """
    Configuration for the Affiliate/Referral Program.
    
    If user_id is NULL, this row represents the Global Default settings.
    If user_id is populated, this row is an Override for that specific user.
    """
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    
    # Null = Global Default. Value = Specific User Override.
    user_id: Optional[UUID] = Field(default=None, unique=True, index=True, description="User ID for override, or NULL for global default")
    
    # Reward for the REFERRER (The person who shared the link)
    referrer_reward_credits: float = Field(default=0.0, description="Credits given to the referrer when a friend subscribes")
    
    # Discount for the REFEREE (The person who clicked the link)
    referee_discount_percent: int = Field(default=0, ge=0, le=100, description="Percentage off for the new subscriber")
    referee_discount_duration: str = Field(default="once", description="Stripe coupon duration: 'once', 'repeating', 'forever'")
    
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
