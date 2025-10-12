"""Quick API endpoint to check verification status - deploy temporarily"""
from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from api.core.database import get_session
from api.models.verification import EmailVerification
from api.models.user import User
from datetime import datetime

router = APIRouter()

@router.get("/debug/check-test5-verification")
async def check_test5_verification(session: Session = Depends(get_session)):
    """Temporary debug endpoint - remove after investigation"""
    
    # Get user
    user = session.exec(select(User).where(User.email == "test5@scottgerhardt.com")).first()
    
    if not user:
        return {"error": "User not found"}
    
    # Get all verification codes
    codes = session.exec(
        select(EmailVerification)
        .where(EmailVerification.user_id == user.id)
        .order_by(EmailVerification.created_at.desc())  # type: ignore
    ).all()
    
    now = datetime.utcnow()
    
    result = {
        "user_id": str(user.id),
        "email": user.email,
        "is_active": user.is_active,
        "created_at": str(user.created_at),
        "verification_codes": []
    }
    
    for code in codes:
        expired = code.expires_at < now
        result["verification_codes"].append({
            "code": code.code,
            "created_at": str(code.created_at),
            "expires_at": str(code.expires_at),
            "expired": expired,
            "used": code.used,
            "verified_at": str(code.verified_at) if code.verified_at else None,
            "warning": "Used but never verified!" if (code.used and not code.verified_at) else None
        })
    
    return result
