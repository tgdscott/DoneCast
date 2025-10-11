"""
Build info endpoint for admin users
"""
import os
from fastapi import APIRouter, Depends
from api.models.user import User
from .deps import get_current_admin_user

router = APIRouter()


@router.get("/build-info")
async def get_build_info(current_user: User = Depends(get_current_admin_user)):
    """
    Get current build/revision information from Cloud Run environment variables.
    Only accessible to admin users.
    """
    revision = os.getenv("K_REVISION", "unknown")
    service = os.getenv("K_SERVICE", "unknown")
    force_restart = os.getenv("FORCE_RESTART", "")
    
    return {
        "service": service,
        "revision": revision,
        "force_restart_timestamp": force_restart,
        "environment": os.getenv("APP_ENV", "unknown"),
    }
