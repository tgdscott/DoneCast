import json
import requests
import requests_mock
import api.services.elevenlabs_service as svc_mod
from api.services.elevenlabs_service import ElevenLabsService

ELEVEN_BASE = "https://api.elevenlabs.io/v1"

FAKE_VOICES = {
    "voices": [
        {
            "voice_id": "v1",
            "name": "Ava",
            "description": "Warm narrator",
            "labels": {"accent": "british", "style": "narration"},
            "preview_url": "https://cdn.example/ava.mp3",
        },
        {
            "voice_id": "v2",
            "name": "Noah",
            "description": "Conversational",
            "labels": {"accent": "american"},
            # No top-level preview_url; will fall back to samples[0].preview_url
            "samples": [{"preview_url": "https://cdn.example/noah.mp3"}],
        },
        {
            "voice_id": "v3",
            "name": "Mia",
            "description": "Cheerful",
            "labels": {"accent": "australian"},
            "preview_url": "https://cdn.example/mia.mp3",
        },
    ]
}

def test_list_voices_normalization_and_pagination():
    # Force service to use requests (not httpx) so requests-mock can intercept
    svc_mod._HTTPX_AVAILABLE = False
    svc_mod.requests = requests
    svc = ElevenLabsService(platform_key="pk_test")
    with requests_mock.Mocker() as m:
        req_count = {"n": 0}

        def _count(request, context):
            req_count["n"] += 1
            context.status_code = 200
            return json.dumps(FAKE_VOICES)

        m.get(f"{ELEVEN_BASE}/voices", text=_count)

        # First page
        resp = svc.list_voices(search="", page=1, size=2)
        assert resp["total"] == 3
        assert resp["page"] == 1 and resp["size"] == 2
        assert len(resp["items"]) == 2

        # Normalize + preview_url fallback
        first = resp["items"][0]
        assert {"voice_id", "name", "description", "labels", "preview_url"} <= set(first.keys())
        # Second item should pick samples[0].preview_url
        second = resp["items"][1]
        if second["voice_id"] == "v2":
            assert second["preview_url"] == "https://cdn.example/noah.mp3"

        # Second page
        resp2 = svc.list_voices(search="", page=2, size=2)
        assert resp2["page"] == 2
        assert len(resp2["items"]) == 1

        # Cache behavior: only one HTTP call across both list_voices invocations
        assert req_count["n"] == 1


def test_list_voices_search_filter():
    svc_mod._HTTPX_AVAILABLE = False
    svc_mod.requests = requests
    svc = ElevenLabsService(platform_key="pk_test")
    with requests_mock.Mocker() as m:
        m.get(f"{ELEVEN_BASE}/voices", json=FAKE_VOICES, status_code=200)

        # Search matches name/labels (case-insensitive)
        resp = svc.list_voices(search="british", page=1, size=25)
        ids = [v["voice_id"] for v in resp["items"]]
        assert ids == ["v1"]  # only Ava has british label
