import json
from typing import Dict, Any

import pytest
import requests
from fastapi.testclient import TestClient

from api.main import app
from api.core.config import settings
import api.services.elevenlabs_service as svc_mod


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
def client():
    return TestClient(app)


def _fake_voices_payload() -> Dict[str, Any]:
    # Two voices: first has top-level preview_url, second falls back to samples[0].preview_url
    return {
        "voices": [
            {
                "voice_id": "v_top",
                "name": "Brit Accent Voice",
                "description": "British style voice",
                "preview_url": "https://cdn.example.com/preview_top.mp3",
                "labels": {"accent": "british"},
                "samples": [],
            },
            {
                "voice_id": "v_samples",
                "name": "US Narrator",
                "description": "American narrator voice",
                # No top-level preview_url on purpose to test fallback
                "labels": {"accent": "american"},
                "samples": [
                    {
                        "sample_id": "s1",
                        "preview_url": "https://cdn.example.com/preview_fallback.mp3",
                    }
                ],
            },
        ]
    }


def _force_requests_path(monkeypatch: pytest.MonkeyPatch):
    # Service prefers httpx if installed; force it to use requests so requests-mock can intercept
    monkeypatch.setattr(svc_mod, "_HTTPX_AVAILABLE", False, raising=False)
    # Ensure the module-level 'requests' symbol exists and is the real requests used by requests-mock
    monkeypatch.setattr(svc_mod, "requests", requests, raising=False)


def test_list_voices_success(requests_mock, client, monkeypatch):
    # Arrange: platform key present and HTTP path mocked
    monkeypatch.setattr(settings, "ELEVENLABS_API_KEY", "pk_test", raising=False)
    _force_requests_path(monkeypatch)
    requests_mock.get(
        "https://api.elevenlabs.io/v1/voices",
        json=_fake_voices_payload(),
        status_code=200,
    )

    # Act
    resp = client.get("/api/elevenlabs/voices", params={"search": "", "page": 1, "size": 2})

    # Assert
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert set(data.keys()) == {"items", "page", "size", "total"}
    assert data["page"] == 1
    assert data["size"] == 2
    assert data["total"] == 2
    assert isinstance(data["items"], list) and len(data["items"]) == 2

    # Preview URL normalization: first item uses top-level, second uses samples[0].preview_url
    v0, v1 = data["items"][0], data["items"][1]
    assert v0["voice_id"] == "v_top"
    assert v0["preview_url"] == "https://cdn.example.com/preview_top.mp3"
    assert v1["voice_id"] == "v_samples"
    assert v1["preview_url"] == "https://cdn.example.com/preview_fallback.mp3"


def test_list_voices_search_filter(requests_mock, client, monkeypatch):
    # Arrange
    monkeypatch.setattr(settings, "ELEVENLABS_API_KEY", "pk_test", raising=False)
    _force_requests_path(monkeypatch)
    requests_mock.get(
        "https://api.elevenlabs.io/v1/voices",
        json=_fake_voices_payload(),
        status_code=200,
    )

    # Act: search label-based term 'british' -> only the first voice should match
    resp = client.get("/api/elevenlabs/voices", params={"search": "british", "page": 1, "size": 10})

    # Assert
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["voice_id"] == "v_top"
    assert item["name"] == "Brit Accent Voice"
    # Ensure preview_url still normalized
    assert item["preview_url"] == "https://cdn.example.com/preview_top.mp3"


def test_list_voices_missing_key_returns_400(client, monkeypatch):
    # Arrange: unset/None platform key to trigger 400 without performing HTTP request
    monkeypatch.setattr(settings, "ELEVENLABS_API_KEY", None, raising=False)

    # Act
    resp = client.get("/api/elevenlabs/voices", params={"search": "", "page": 1, "size": 2})

    # Assert
    assert resp.status_code == 400
    data = resp.json()
    # Detail/message should mention missing config (support custom error envelope)
    detail = data.get("detail")
    message = None
    if isinstance(data.get("error"), dict):
        message = data["error"].get("message")
    combined = " ".join([str(x) for x in [detail, message] if x])
    assert "ELEVENLABS_API_KEY not configured" in combined
