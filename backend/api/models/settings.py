from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.exc import OperationalError, ProgrammingError
from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel


logger = logging.getLogger(__name__)


class AppSetting(SQLModel, table=True):
    """Simple key/value app-wide setting store (JSON string in value_json).

    Use a small set of well-known keys, e.g., 'admin_settings'.
    """

    key: str = Field(primary_key=True, index=True)
    value_json: str = Field(default='{}')
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AdminSettings(BaseModel):
    """App-wide admin-configurable settings.

    - test_mode: legacy toggle used by parts of the system/tests
    - default_user_active: whether newly created users start active (True) or inactive (False)
    - maintenance_mode: when True, non-admin API requests are rejected with HTTP 503
    - maintenance_message: optional string surfaced to clients when maintenance is active
    """

    test_mode: bool = False
    default_user_active: bool = True
    # Maximum upload size for main content (in MB). Exposed publicly for client hints.
    max_upload_mb: int = 500
    maintenance_mode: bool = False
    maintenance_message: Optional[str] = None


def load_admin_settings(session: Session) -> AdminSettings:
    """Load AdminSettings from the AppSetting row ``admin_settings``.

    The helper is intentionally defensive: if the settings table is missing or
    contains malformed JSON we log the error, roll back the current transaction
    (to keep the caller's session usable) and fall back to the default
    ``AdminSettings`` values.
    """

    try:
        rec = session.get(AppSetting, "admin_settings")
        if not rec or not (rec.value_json or "").strip():
            return AdminSettings()
        data = json.loads(rec.value_json)
        if not isinstance(data, dict):
            return AdminSettings()
        return AdminSettings(**data)
    except Exception as exc:  # pragma: no cover - defensive fallback
        try:
            session.rollback()
        except Exception:  # pragma: no cover - rollback may fail if session closed
            pass
        if _is_missing_table_error(exc):
            _ensure_appsetting_table(session)
        logger.warning("Failed loading admin settings, using defaults: %s", exc)
        return AdminSettings()


def _is_missing_table_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "no such table" in text
        or "does not exist" in text
        or "undefined table" in text
    )


def _ensure_appsetting_table(session: Session) -> None:
    try:
        bind = session.get_bind()
        if bind is None:
            return
        AppSetting.__table__.create(bind, checkfirst=True)  # type: ignore[arg-type]
    except Exception as exc:  # pragma: no cover - best effort safeguard
        logger.debug("Unable to ensure appsetting table: %s", exc)


def save_admin_settings(session: Session, settings: AdminSettings) -> AdminSettings:
    """Persist AdminSettings into AppSetting row 'admin_settings'. Returns the reloaded value."""

    def _load_or_create() -> AppSetting:
        rec = session.get(AppSetting, 'admin_settings')
        payload = json.dumps(settings.model_dump())
        if not rec:
            rec = AppSetting(key='admin_settings', value_json=payload)
        else:
            rec.value_json = payload
        try:
            rec.updated_at = datetime.utcnow()
        except Exception:  # pragma: no cover - timestamp best effort
            pass
        session.add(rec)
        return rec

    try:
        rec = _load_or_create()
        session.commit()
    except (ProgrammingError, OperationalError) as exc:
        if not _is_missing_table_error(exc):
            session.rollback()
            raise
        session.rollback()
        _ensure_appsetting_table(session)
        rec = _load_or_create()
        session.commit()
    except Exception:
        session.rollback()
        raise
    return load_admin_settings(session)
