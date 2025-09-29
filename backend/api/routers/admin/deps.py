from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.exc import OperationalError
from sqlmodel import Session

from api.routers.auth import get_current_user
from api.core.config import settings
from api.models.user import User


log = logging.getLogger(__name__)


def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Ensure the requesting user has admin privileges."""
    try:
        email_ok = bool(current_user.email and current_user.email.lower() == settings.ADMIN_EMAIL.lower())
    except Exception:
        email_ok = False
    is_flag = bool(getattr(current_user, "is_admin", False))
    has_role = str(getattr(current_user, "role", "")).lower() == "admin"
    if not (email_ok or is_flag or has_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user does not have permissions to access this resource.",
        )
    return current_user


def commit_with_retry(session: Session, attempts: int = 3, base_sleep: float = 0.2) -> None:
    """Commit the session with retries for transient SQLite locking errors."""
    last_err: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            session.commit()
            return
        except OperationalError as exc:  # pragma: no cover - env specific
            msg = str(exc).lower()
            if "database is locked" in msg or "database is busy" in msg or "database table is locked" in msg:
                last_err = exc
                time.sleep(base_sleep * (attempt + 1))
                continue
            raise
        except Exception as exc:  # pragma: no cover
            last_err = exc
            break
    if last_err is not None:
        log.error("Admin commit_with_retry failed after %s attempts", attempts)
        raise last_err
