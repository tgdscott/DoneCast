from __future__ import annotations

import io
import json
from typing import Tuple

import pytest
from sqlmodel import select

from api.core.security import get_password_hash
from api.models.transcription import TranscriptionWatch
from api.models.user import User


def _create_user(session) -> Tuple[User, str]:
    password = "notify-me!123"
    user = User(
        email="notify-tester@example.com",
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
def test_main_content_upload_records_watch_without_email(session, client, monkeypatch):
    user, password = _create_user(session)
    headers = _auth_headers(client, user.email, password)

    stub_task = lambda path, body: {"name": "stubbed"}
    monkeypatch.setattr(
        "infrastructure.tasks_client.enqueue_http_task",
        stub_task,
    )
    monkeypatch.setattr(
        "backend.api.routers.media.write.enqueue_http_task",
        stub_task,
    )

    resp = client.post(
        "/api/media/upload/main_content",
        data={
            "notify_when_ready": "false",
            "friendly_names": json.dumps(["My Upload"]),
        },
        files={
            "files": ("sample.wav", io.BytesIO(b"RIFF....WAVE"), "audio/wav"),
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    payload = resp.json()
    assert isinstance(payload, list) and payload

    filename = payload[0]["filename"]
    watch = session.exec(
        select(TranscriptionWatch).where(
            TranscriptionWatch.user_id == user.id,
            TranscriptionWatch.filename == filename,
        )
    ).first()

    assert watch is not None
    assert (watch.notify_email or "").strip() == ""
    assert watch.last_status == "queued"


@pytest.mark.usefixtures("db_engine")
def test_main_content_upload_records_email_target(session, client, monkeypatch):
    user, password = _create_user(session)
    headers = _auth_headers(client, user.email, password)

    stub_task = lambda path, body: {"name": "stubbed"}
    monkeypatch.setattr(
        "infrastructure.tasks_client.enqueue_http_task",
        stub_task,
    )
    monkeypatch.setattr(
        "backend.api.routers.media.write.enqueue_http_task",
        stub_task,
    )

    notify_email = "alerts@example.com"
    resp = client.post(
        "/api/media/upload/main_content",
        data={
            "notify_when_ready": "true",
            "notify_email": notify_email,
        },
        files={
            "files": ("another.wav", io.BytesIO(b"RIFF....WAVE"), "audio/wav"),
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    payload = resp.json()
    assert isinstance(payload, list) and payload

    filename = payload[0]["filename"]
    watch = session.exec(
        select(TranscriptionWatch).where(
            TranscriptionWatch.user_id == user.id,
            TranscriptionWatch.filename == filename,
        )
    ).first()

    assert watch is not None
    assert watch.notify_email == notify_email
    assert watch.last_status == "queued"
