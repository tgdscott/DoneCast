from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, EmailStr
from datetime import datetime, timezone
from typing import Optional
from api.core.paths import WS_ROOT
from api.core.auth import get_current_user
from api.models.user import User

router = APIRouter(prefix="/public", tags=["Public"])

WAITLIST_FILE = WS_ROOT / "waitlist_emails.txt"


class WaitlistIn(BaseModel):
    email: EmailStr
    note: Optional[str] = None


@router.post("/waitlist", status_code=200)
async def post_waitlist(
    payload: WaitlistIn,
    request: Request,
    current_user: Optional[User] = Depends(lambda: None),  # optional auth
):
    """Append an email to a simple waitlist text file.

    Format per line: ISO_TIMESTAMP<TAB>EMAIL<TAB>USER_ID(optional)<TAB>NOTE(optional)
    """
    ts = datetime.now(timezone.utc).isoformat()
    uid = None
    try:
        # If a valid auth token is present, current_user will be set by dependency injection elsewhere.
        # Here we accept None to allow unauthenticated submissions.
        uid = getattr(current_user, "id", None)
    except Exception:
        uid = None
    note = (payload.note or "").strip().replace("\n", " ")
    line = f"{ts}\t{payload.email}\t{str(uid) if uid else ''}\t{note}\n"
    try:
        WAITLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        with WAITLIST_FILE.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        # Surface a simple 500; the global exception handler will format consistently
        raise HTTPException(status_code=500, detail="Failed to save your request") from e
    # Minimal acknowledgement; avoid echoing email back
    return {"status": "ok"}
