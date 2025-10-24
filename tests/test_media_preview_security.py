import sys
import types

import pytest

# Provide lightweight stand-ins for the recurring models package so importing
# api.models.* during tests does not try to construct dialect-specific SQLModel
# columns (legacy compatibility - tests should use PostgreSQL now).
if "api.models.recurring" not in sys.modules:
    stub = types.ModuleType("api.models.recurring")

    class _RecurringScheduleBase:  # pragma: no cover - placeholder
        pass

    class _RecurringSchedule(_RecurringScheduleBase):  # pragma: no cover
        pass

    class _RecurringScheduleRead(_RecurringScheduleBase):  # pragma: no cover
        pass

    class _RecurringScheduleCreate:  # pragma: no cover
        pass

    stub.RecurringScheduleBase = _RecurringScheduleBase
    stub.RecurringSchedule = _RecurringSchedule
    stub.RecurringScheduleRead = _RecurringScheduleRead
    stub.RecurringScheduleCreate = _RecurringScheduleCreate
    sys.modules["api.models.recurring"] = stub

from api.core.paths import MEDIA_DIR
from api.core.security import get_password_hash
from api.models.podcast import MediaCategory, MediaItem
from api.models.user import User


def _create_user(session) -> tuple[User, str]:
    password = "hunter2!!"
    user = User(
        email="preview-tester@example.com",
        hashed_password=get_password_hash(password),
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user, password


def _auth_headers(client, email: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/token",
        data={"username": email, "password": password},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.usefixtures("db_engine")
def test_preview_rejects_path_traversal(session, client):
    user, password = _create_user(session)

    media_root = MEDIA_DIR
    (media_root / "legit.wav").write_bytes(b"ok")

    session.add(
        MediaItem(
            filename="legit.wav",
            user_id=user.id,
            category=MediaCategory.music,
        )
    )
    session.commit()

    headers = _auth_headers(client, user.email, password)
    resp = client.get(
        "/api/media/preview",
        params={"path": "../api/app.py"},
        headers=headers,
    )
    assert resp.status_code == 400
    data = resp.json()
    if isinstance(data, dict):
        detail = data.get("detail")
        if detail is None and isinstance(data.get("error"), dict):
            detail = data["error"].get("message")
        assert detail == "Invalid path"
    else:
        assert "Invalid path" in str(data)


@pytest.mark.usefixtures("db_engine")
def test_preview_normalizes_relative_segments(session, client):
    user, password = _create_user(session)

    nested_dir = MEDIA_DIR / "covers"
    nested_dir.mkdir(parents=True, exist_ok=True)
    (nested_dir / "art.png").write_bytes(b"img")

    item = MediaItem(
        filename="covers/art.png",
        user_id=user.id,
        category=MediaCategory.podcast_cover,
    )
    session.add(item)
    session.commit()
    session.refresh(item)

    headers = _auth_headers(client, user.email, password)
    resp = client.get(
        "/api/media/preview",
        params={"id": str(item.id), "resolve": "true"},
        headers=headers,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["url"].endswith("/static/media/covers/art.png")
    assert ".." not in payload["url"]
    assert payload["path"] == "/static/media/covers/art.png"
