from sqlmodel import SQLModel, Field
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional

class Subscription(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    stripe_subscription_id: str = Field(index=True)
    plan_key: str
    price_id: str
    status: str = Field(default="incomplete")  # active, trialing, past_due, canceled, incomplete, incomplete_expired
    current_period_end: Optional[datetime] = Field(default=None)
    cancel_at_period_end: bool = Field(default=False)
    billing_cycle: Optional[str] = Field(default=None, description="monthly|annual")
    subscription_started_at: Optional[datetime] = Field(default=None, description="When this subscription (plan+cycle) was first started")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class SubscriptionPublic(SQLModel):
    id: UUID
    plan_key: str
    status: str
    current_period_end: Optional[datetime]
    cancel_at_period_end: bool
    price_id: str
