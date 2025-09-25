import json
from pathlib import Path
from typing import Callable

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session as DBSession

from api.main import app
from api.core.database import engine
from api.core.paths import MEDIA_DIR
from api.core import crud
from api.models.user import UserCreate, User
from api.models.podcast import MediaItem
from api.routers.auth import get_current_user


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    # Ensure clean dependency overrides slate for each test
    original = dict(app.dependency_overrides)
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db() -> DBSession:
    with DBSession(engine) as s:
        yield s


@pytest.fixture
def user(db: DBSession) -> User:
    # Unique email per test run to avoid unique constraints
    import uuid
    uc = UserCreate(email=f"tts_{uuid.uuid4().hex[:8]}@example.com", password="Password123!")
    return crud.create_user(session=db, user_create=uc)


@pytest.fixture
def authed_client(client: TestClient, user: User):
    # Override auth dependency to return our test user
    app.dependency_overrides[get_current_user] = lambda: user
    return client


class FakeAudio:
    def __init__(self, content: bytes = b"FAKE_MP3"):
        self._content = content

    def export(self, out_path, format: str = "mp3"):
        p = Path(out_path)
        p.write_bytes(self._content)


def _cleanup_created_media(filename: str | None):
    if not filename:
        return
    try:
        p = MEDIA_DIR / filename
        if p.exists():
            p.unlink()
    except Exception:
        pass


def _delete_mediaitem(db: DBSession, filename: str | None):
    if not filename:
        return
    try:
        # Best-effort delete to keep the dev DB tidy
        mi = db.exec(
            MediaItem.select().where(MediaItem.filename == filename)  # type: ignore[attr-defined]
        ).first()
    except Exception:
        # Fallback query if select() isn't available on model (older SQLModel)
        from sqlmodel import select
        mi = db.exec(select(MediaItem).where(MediaItem.filename == filename)).first()
    if mi:
        try:
            db.delete(mi)
            db.commit()
        except Exception:
            db.rollback()


def test_tts_minimal_success_elevenlabs(monkeypatch: pytest.MonkeyPatch, authed_client: TestClient, db: DBSession):
    # Arrange: stub synthesis to avoid real TTS and ffmpeg
    import api.services.ai_enhancer as enh
    monkeypatch.setattr(enh, "generate_speech_from_text", lambda **kwargs: FakeAudio(b"ID3FAKE"))

    payload = {
        "text": "Hello world from tests",
        "category": "intro",
    }

    # Act
    resp = authed_client.post("/api/media/tts", json=payload)

    # Assert
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["filename"].endswith(".mp3")
    assert data["category"] == "intro"
    # Check file exists
    fp = MEDIA_DIR / data["filename"]
    assert fp.exists() and fp.stat().st_size > 0

    # Cleanup artifacts
    _cleanup_created_media(data.get("filename"))
    _delete_mediaitem(db, data.get("filename"))


def test_tts_missing_text_validation_422(authed_client: TestClient):
    # Missing required field -> 422
    resp = authed_client.post("/api/media/tts", json={"category": "intro"})
    assert resp.status_code == 422


def test_tts_whitespace_text_returns_400(monkeypatch: pytest.MonkeyPatch, authed_client: TestClient):
    # Arrange stub anyway (should not be called)
    import api.services.ai_enhancer as enh
    monkeypatch.setattr(enh, "generate_speech_from_text", lambda **kwargs: FakeAudio())

    resp = authed_client.post(
        "/api/media/tts",
        json={"text": "   ", "category": "music"},
    )
    assert resp.status_code == 400
    assert "Text is required" in resp.text


def test_tts_invalid_category_422(authed_client: TestClient):
    resp = authed_client.post(
        "/api/media/tts",
        json={"text": "Hi", "category": "not_a_real_category"},
    )
    assert resp.status_code == 422


def test_tts_google_provider_success(monkeypatch: pytest.MonkeyPatch, authed_client: TestClient, db: DBSession):
    # Arrange: verify our stub sees provider and google_voice
    captured: dict = {}

    def stub_generate_speech_from_text(**kwargs):
        captured.update(kwargs)
        assert kwargs.get("provider") == "google"
        assert kwargs.get("google_voice") == "en-US-Wavenet-D"
        return FakeAudio(b"ID3FAKE_GOOGLE")

    import api.services.ai_enhancer as enh
    monkeypatch.setattr(enh, "generate_speech_from_text", stub_generate_speech_from_text)

    payload = {
        "text": "Goodbye now",
        "category": "outro",
        "provider": "google",
        "google_voice": "en-US-Wavenet-D",
        "speaking_rate": 1.25,
    }
    resp = authed_client.post("/api/media/tts", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["category"] == "outro"

    # Cleanup
    _cleanup_created_media(data.get("filename"))
    _delete_mediaitem(db, data.get("filename"))


def test_tts_synthesis_failure_returns_500(monkeypatch: pytest.MonkeyPatch, authed_client: TestClient):
    # Arrange: raise a generic exception to trigger 500 path (not 502)
    import api.services.ai_enhancer as enh
    def boom(**kwargs):
        raise RuntimeError("boom")
    monkeypatch.setattr(enh, "generate_speech_from_text", boom)

    resp = authed_client.post(
        "/api/media/tts",
        json={"text": "Will fail", "category": "sfx"},
    )
    assert resp.status_code == 500
    body = resp.json()
    # Accept either default FastAPI detail or the app's error envelope
    if isinstance(body, dict) and "detail" in body:
        msg = str(body.get("detail"))
    elif isinstance(body, dict) and isinstance(body.get("error"), dict):
        msg = str(body["error"].get("message"))
    else:
        msg = str(body)
    assert "TTS failed" in msg
