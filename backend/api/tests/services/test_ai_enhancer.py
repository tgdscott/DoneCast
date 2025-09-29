import os
import types

import pytest

for _env_key in [
    "DB_USER",
    "DB_PASS",
    "DB_NAME",
    "INSTANCE_CONNECTION_NAME",
    "GEMINI_API_KEY",
    "ELEVENLABS_API_KEY",
    "ASSEMBLYAI_API_KEY",
    "SPREAKER_API_TOKEN",
    "SPREAKER_CLIENT_ID",
    "SPREAKER_CLIENT_SECRET",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
]:
    os.environ.setdefault(_env_key, "test-value")

from api.services import ai_enhancer


def test_google_provider_not_implemented():
    with pytest.raises(ai_enhancer.AIEnhancerError) as exc:
        ai_enhancer.generate_speech_from_text("hello", provider="google")
    assert "not yet implemented" in str(exc.value)


def test_unsupported_provider():
    with pytest.raises(ai_enhancer.AIEnhancerError) as exc:
        ai_enhancer.generate_speech_from_text("hello", provider="unknown")
    assert "Unsupported TTS provider" in str(exc.value)


def test_translate_error_voice_not_found(monkeypatch):
    fake_httpx = types.SimpleNamespace(HTTPStatusError=Exception)
    monkeypatch.setattr(ai_enhancer, "httpx", fake_httpx)

    class FakeResponse:
        status_code = 422

        @staticmethod
        def json():
            return {"detail": {"message": "voice_id not found"}}

        text = "voice_id not found"

    class FakeError(Exception):
        def __init__(self):
            self.response = FakeResponse()

    err = ai_enhancer._translate_elevenlabs_error(FakeError(), "abc123")
    assert "abc123" in str(err)
