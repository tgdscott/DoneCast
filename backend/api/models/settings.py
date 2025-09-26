from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional
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
        logger.warning("Failed loading admin settings, using defaults: %s", exc)
        return AdminSettings()


def save_admin_settings(session: Session, settings: AdminSettings) -> AdminSettings:
    """Persist AdminSettings into AppSetting row 'admin_settings'. Returns the reloaded value."""
    rec = session.get(AppSetting, 'admin_settings')
    payload = json.dumps(settings.model_dump())
    if not rec:
        rec = AppSetting(key='admin_settings', value_json=payload)
    else:
        rec.value_json = payload
    try:
        rec.updated_at = datetime.utcnow()
    except Exception:
        pass
    session.add(rec)
    session.commit()
    return load_admin_settings(session)
