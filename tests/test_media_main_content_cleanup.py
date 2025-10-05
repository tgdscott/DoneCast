from __future__ import annotations

from typing import Tuple

import pytest
from sqlmodel import select

from api.core.security import get_password_hash
from api.models.podcast import MediaCategory, MediaItem
from api.models.user import User
from infrastructure import gcs


def _create_user(session) -> Tuple[User, str]:
    password = "super-secret!"
    user = User(
        email="cleanup-tester@example.com",
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
def test_list_main_content_prunes_missing_entries(session, client, monkeypatch):
    user, password = _create_user(session)

    missing_local = MediaItem(
        filename="does-not-exist.wav",
        user_id=user.id,
        category=MediaCategory.main_content,
    )
    missing_gcs = MediaItem(
        filename=f"gs://media-bucket/{user.id}/main_content/missing.wav",
        user_id=user.id,
        category=MediaCategory.main_content,
    )

    session.add(missing_local)
    session.add(missing_gcs)
    session.commit()

    probe_calls = []

    def _fake_blob_exists(bucket: str, key: str):
        probe_calls.append((bucket, key))
        return False

    monkeypatch.setattr(gcs, "blob_exists", _fake_blob_exists)

    headers = _auth_headers(client, user.email, password)
    response = client.get("/api/media/main-content", headers=headers)

    assert response.status_code == 200
    assert response.json() == []

    remaining = session.exec(select(MediaItem).where(MediaItem.user_id == user.id)).all()
    assert remaining == []
    assert probe_calls, "expected GCS existence check to run for gs:// uploads"
