"""
Billing configuration endpoint - provides Stripe publishable key to frontend
"""
from fastapi import APIRouter
from pydantic import BaseModel
from ..core.config import settings

router = APIRouter(prefix="/billing", tags=["Billing"])


class BillingConfigResponse(BaseModel):
    publishable_key: str
    mode: str  # "test" or "live"


@router.get("/config", response_model=BillingConfigResponse)
async def get_billing_config():
    """
    Return Stripe publishable key for frontend initialization.
    This is safe to expose publicly (it's a publishable key, not secret).
    """
    pub_key = settings.STRIPE_PUBLISHABLE_KEY
    mode = "live" if pub_key.startswith("pk_live_") else "test"
    
    return BillingConfigResponse(
        publishable_key=pub_key,
        mode=mode
    )
