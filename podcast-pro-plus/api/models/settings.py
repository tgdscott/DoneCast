from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Session
from pydantic import BaseModel
import json


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
    """
    test_mode: bool = False
    default_user_active: bool = True
    # Maximum upload size for main content (in MB). Exposed publicly for client hints.
    max_upload_mb: int = 500


def load_admin_settings(session: Session) -> AdminSettings:
    """Load AdminSettings from AppSetting row 'admin_settings'. Returns defaults on error/missing."""
    try:
        rec = session.get(AppSetting, 'admin_settings')
        if not rec or not (rec.value_json or '').strip():
            return AdminSettings()
        data = json.loads(rec.value_json)
        if not isinstance(data, dict):
            return AdminSettings()
        return AdminSettings(**data)
    except Exception:
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
