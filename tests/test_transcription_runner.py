from pathlib import Path
from typing import Any, Dict, List

import pytest

from api.services.transcription import assemblyai_client
from api.services.transcription.transcription_runner import run_assemblyai_job
from api.services.transcription.assemblyai_webhook import AssemblyAIWebhookManager


class FakeResponse:
    def __init__(self, status_code: int, payload: Dict[str, Any]):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> Dict[str, Any]:
        return dict(self._payload)


class FakeSession:
    def __init__(self, post, get):
        self._post = post
        self._get = get

    def post(self, url, headers=None, data=None, json=None):
        kwargs = {}
        if headers is not None:
            kwargs["headers"] = headers
        if data is not None:
            kwargs["data"] = data
        if json is not None:
            kwargs["json"] = json
        return self._post(url, **kwargs)

    def get(self, url, headers=None):
        return self._get(url, headers=headers)


def test_runner_happy_path(tmp_path, monkeypatch, caplog):
    caplog.set_level("INFO")
    # Create a fake audio file
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"RIFF....WAVE")

    calls: List[str] = []

    # Monkeypatch HTTP layer used by client so client logging runs
    def fake_post(url, headers=None, data=None, json=None):
        if url.endswith("/upload"):
            calls.append("post_upload")
            headers = headers or {}
            assert headers.get("authorization") == "k"
            return FakeResponse(200, {"upload_url": "https://mock/upload/123"})
        elif url.endswith("/transcript"):
            calls.append("post_transcript")
            headers = headers or {}
            json = json or {}
            assert headers.get("authorization") == "k"
            assert json.get("audio_url") == "https://mock/upload/123"
            return FakeResponse(200, {"id": "job_1", "status": "queued"})
        raise AssertionError(f"Unexpected POST url: {url}")

    seq = [
        {"status": "processing"},
        {"status": "completed", "text": "hi", "words": [{"text": "hi", "start": 0, "end": 1000}]},
    ]

    def fake_get(url, headers=None):
        headers = headers or {}
        assert headers.get("authorization") == "k"
        assert url.endswith("/transcript/job_1")
        calls.append("get_poll")
        return FakeResponse(200, seq.pop(0))

    session = FakeSession(fake_post, fake_get)
    monkeypatch.setattr(assemblyai_client, "_get_session", lambda: session)

    # Avoid delays
    monkeypatch.setattr("time.sleep", lambda s: None)

    cfg = {
        "api_key": "k",
        "base_url": "https://mock",
        "polling": {"interval_s": 0.01, "timeout_s": 5, "backoff": 1.0},
        "params": {"speaker_labels": False},
    }
    log: List[str] = []

    out = run_assemblyai_job(audio, cfg, log)

    # Order of HTTP calls (upload -> create -> poll*2)
    assert calls == ["post_upload", "post_transcript", "get_poll", "get_poll"]

    # Result normalized
    assert isinstance(out, dict)
    assert list(out.keys()) == ["words"]
    assert out["words"][0]["word"] == "hi"
    assert out["words"][0]["start"] == 0
    assert out["words"][0]["end"] == 1.0

    # Log lines present from client/runner
    msgs = "\n".join(r.getMessage() for r in caplog.records)
    assert "[assemblyai] payload=" in msgs
    assert "[assemblyai] created transcript id=" in msgs
    assert "[assemblyai] server flags" in msgs


def test_webhook_manager_handles_out_of_order_notifications():
    manager = AssemblyAIWebhookManager()

    # Webhook arrives before register()
    manager.notify({"id": "job123", "status": "completed", "text": "hi"})

    manager.register("job123", timeout_s=1.0)
    data = manager.wait_for_completion("job123", timeout_s=0.1)

    assert data is not None
    assert data["status"] == "completed"
