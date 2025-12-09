from pathlib import Path
from typing import Any, Dict

import builtins
import types
import pytest

from api.services.transcription import assemblyai_client
from api.services.transcription.assemblyai_client import (
    upload_audio,
    start_transcription,
    get_transcription,
    AssemblyAITranscriptionError,
)


class FakeSession:
    def __init__(self, *, post=None, get=None, delete=None):
        self._post = post
        self._get = get
        self._delete = delete

    def post(self, url, headers=None, data=None, json=None):
        assert self._post is not None, "post handler not configured"
        kwargs = {}
        if headers is not None:
            kwargs["headers"] = headers
        if data is not None:
            kwargs["data"] = data
        if json is not None:
            kwargs["json"] = json
        return self._post(url, **kwargs)

    def get(self, url, headers=None):
        assert self._get is not None, "get handler not configured"
        return self._get(url, headers=headers)

    def delete(self, url, headers=None):
        assert self._delete is not None, "delete handler not configured"
        return self._delete(url, headers=headers)


class FakeResponse:
    def __init__(self, status_code: int, payload: Dict[str, Any]):
        self.status_code = status_code
        self._payload = payload
        # Simple text body for error messages
        self.text = str(payload)

    def json(self) -> Dict[str, Any]:
        return dict(self._payload)


def test_upload_audio_success(tmp_path, monkeypatch, caplog):
    caplog.set_level("INFO")
    # Arrange
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF....WAVE")

    captured = {}

    def fake_post(url, headers=None, data=None):
        captured["url"] = url
        captured["headers"] = dict(headers or {})
        # Ensure data is an iterable/generator of bytes
        chunks = list(data)
        assert all(isinstance(c, (bytes, bytearray)) for c in chunks)
        return FakeResponse(200, {"upload_url": "https://mock/upload/123"})

    monkeypatch.setattr(assemblyai_client, "_get_session", lambda: FakeSession(post=fake_post))

    # Act
    out = upload_audio(audio, api_key="KEY", base_url="https://mock", log=[])

    # Assert
    assert out == "https://mock/upload/123"
    assert captured["url"] == "https://mock/upload/123".replace("upload/123", "upload")
    assert captured["headers"].get("authorization") == "KEY"
    assert captured["headers"].get("content-type") == "application/octet-stream"
    # upload_audio does not log in production; verify no [assemblyai] logs were emitted here
    assert not any("[assemblyai]" in r.getMessage() for r in caplog.records)


def test_upload_audio_failure(tmp_path, monkeypatch):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF....WAVE")

    def fake_post(url, headers=None, data=None):
        return FakeResponse(500, {"error": "oops"})

    monkeypatch.setattr(assemblyai_client, "_get_session", lambda: FakeSession(post=fake_post))

    with pytest.raises(AssemblyAITranscriptionError) as ei:
        upload_audio(audio, api_key="K", base_url="https://mock", log=[])
    assert str(ei.value).startswith("Upload failed: 500 ")


def test_start_transcription_success(monkeypatch, caplog):
    caplog.set_level("INFO")
    captured = {}

    def fake_post(url, json=None, headers=None):
        captured["url"] = url
        captured["json"] = dict(json or {})
        captured["headers"] = dict(headers or {})
        return FakeResponse(200, {"id": "job_1", "status": "queued"})

    monkeypatch.setattr(assemblyai_client, "_get_session", lambda: FakeSession(post=fake_post))

    out = start_transcription(
        upload_url="https://mock/upload/123",
        api_key="KEY",
        params={"speaker_labels": False},
        base_url="https://mock",
        log=[],
    )

    assert out["id"] == "job_1"
    assert captured["url"] == "https://mock/transcript"
    # Payload defaults merged; our override respected
    assert captured["json"]["audio_url"] == "https://mock/upload/123"
    assert captured["json"]["speaker_labels"] is False
    assert captured["headers"].get("authorization") == "KEY"
    # Logs include payload and created transcript id
    msgs = "\n".join(r.getMessage() for r in caplog.records)
    assert "[assemblyai] payload=" in msgs
    assert "[assemblyai] created transcript id=job_1" in msgs


def test_start_transcription_failure(monkeypatch):
    def fake_post(url, json=None, headers=None):
        return FakeResponse(400, {"error": "bad"})

    monkeypatch.setattr(assemblyai_client, "_get_session", lambda: FakeSession(post=fake_post))

    with pytest.raises(AssemblyAITranscriptionError) as ei:
        start_transcription(
            upload_url="https://mock/upload/123",
            api_key="KEY",
            params=None,
            base_url="https://mock",
            log=[],
        )
    assert str(ei.value).startswith("Transcription request failed: 400 ")


def test_get_transcription_success(monkeypatch, caplog):
    caplog.set_level("INFO")
    captured = {}

    def fake_get(url, headers=None):
        captured["url"] = url
        captured["headers"] = dict(headers or {})
        return FakeResponse(200, {"id": "job_1", "status": "completed", "text": "hello"})

    monkeypatch.setattr(assemblyai_client, "_get_session", lambda: FakeSession(get=fake_get))

    out = get_transcription("job_1", api_key="KEY", base_url="https://mock", log=[])
    assert out["status"] == "completed"
    assert captured["url"] == "https://mock/transcript/job_1"
    assert captured["headers"].get("authorization") == "KEY"
    # get_transcription does not log in production; verify no [assemblyai] logs from this call
    assert not any("[assemblyai]" in r.getMessage() for r in caplog.records)


def test_get_transcription_failure(monkeypatch):
    def fake_get(url, headers=None):
        return FakeResponse(503, {"error": "down"})

    monkeypatch.setattr(assemblyai_client, "_get_session", lambda: FakeSession(get=fake_get))

    with pytest.raises(AssemblyAITranscriptionError) as ei:
        get_transcription("job_1", api_key="KEY", base_url="https://mock", log=[])
    assert str(ei.value).startswith("Polling failed: 503 ")
