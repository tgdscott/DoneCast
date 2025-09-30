from __future__ import annotations

import io
import json
from pathlib import Path

from typing import Tuple

import pytest
from sqlmodel import select

from api.core.security import get_password_hash
from api.core.paths import MEDIA_DIR
from api.models.notification import Notification
from api.models.podcast import MediaCategory, MediaItem
from api.models.transcription import TranscriptionWatch
from api.models.user import User
from api.services.transcription import transcribe_media_file
from api.services.transcription.watchers import notify_watchers_processed



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


@pytest.mark.usefixtures("db_engine")
def test_transcribe_media_file_notifies_watchers_with_email(session, monkeypatch):
    user, _ = _create_user(session)

    filename = "notify-me.wav"
    friendly = "Notify Me"
    (MEDIA_DIR / filename).write_bytes(b"RIFF....WAVE")

    media_item = MediaItem(
        filename=filename,
        friendly_name=friendly,
        user_id=user.id,
        category=MediaCategory.main_content,
    )
    session.add(media_item)
    watch = TranscriptionWatch(
        user_id=user.id,
        filename=filename,
        friendly_name=friendly,
        notify_email="alerts@example.com",
        last_status="queued",
    )
    session.add(watch)
    session.commit()

    sent: list[tuple[str, str, str]] = []

    def fake_send(email: str, subject: str, body: str) -> bool:
        sent.append((email, subject, body))
        return True

    monkeypatch.setattr("api.services.transcription.watchers.mailer.send", fake_send)
    monkeypatch.setattr(
        "api.services.transcription.get_word_timestamps",
        lambda _: [{"word": "ok", "start": 0.0, "end": 0.5}],
    )

    transcribe_media_file(filename)

    updated_watch = session.exec(
        select(TranscriptionWatch).where(
            TranscriptionWatch.user_id == user.id,
            TranscriptionWatch.filename == filename,
        )
    ).first()
    assert updated_watch is not None
    assert updated_watch.notified_at is not None
    assert updated_watch.last_status == "sent"

    notes = session.exec(
        select(Notification).where(Notification.user_id == user.id)
    ).all()
    assert len(notes) == 1
    assert friendly in notes[0].body
    assert sent and sent[0][0] == "alerts@example.com"


@pytest.mark.usefixtures("db_engine")
def test_transcribe_media_file_notifies_without_email(session, monkeypatch):
    user, _ = _create_user(session)

    filename = "notify-none.wav"
    friendly = "Notify None"
    (MEDIA_DIR / filename).write_bytes(b"RIFF....WAVE")

    session.add(
        MediaItem(
            filename=filename,
            friendly_name=friendly,
            user_id=user.id,
            category=MediaCategory.main_content,
        )
    )
    session.add(
        TranscriptionWatch(
            user_id=user.id,
            filename=filename,
            friendly_name=friendly,
            notify_email=None,
            last_status="queued",
        )
    )
    session.commit()

    sent: list[tuple[str, str, str]] = []

    def fake_send(email: str, subject: str, body: str) -> bool:
        sent.append((email, subject, body))
        return True

    monkeypatch.setattr("api.services.transcription.watchers.mailer.send", fake_send)
    monkeypatch.setattr(
        "api.services.transcription.get_word_timestamps",
        lambda _: [{"word": "ok", "start": 0.0, "end": 0.5}],
    )

    transcribe_media_file(filename)

    updated_watch = session.exec(
        select(TranscriptionWatch).where(
            TranscriptionWatch.user_id == user.id,
            TranscriptionWatch.filename == filename,
        )
    ).first()
    assert updated_watch is not None
    assert updated_watch.notified_at is not None
    assert updated_watch.last_status == "no-email"

    notes = session.exec(
        select(Notification).where(Notification.user_id == user.id)
    ).all()
    assert len(notes) == 1
    assert friendly in notes[0].body
    assert sent == []
