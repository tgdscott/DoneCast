import uuid

import pytest
from fastapi.testclient import TestClient

import tests.conftest as _tests_conftest  # noqa: F401  # ensure env defaults applied

from api.main import app
import api.routers.ai_suggestions as ai_mod
from api.services.ai_content.schemas import SuggestNotesOut, SuggestTagsOut, SuggestTitleOut


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
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
def transcript_file(tmp_path):
    path = tmp_path / "dummy.txt"
    path.write_text("hello world", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "endpoint, stub_name, response_factory, expected_key, expected_value",
    [
        ("/api/ai/title", "suggest_title", lambda: SuggestTitleOut(title="Stub Title"), "title", "Stub Title"),
        (
            "/api/ai/notes",
            "suggest_notes",
            lambda: SuggestNotesOut(description="Stub Notes", bullets=["a"]),
            "description",
            "Stub Notes",
        ),
        (
            "/api/ai/tags",
            "suggest_tags",
            lambda: SuggestTagsOut(tags=["alpha", "beta"]),
            "tags",
            ["alpha", "beta"],
        ),
    ],
)
def test_ai_endpoints_accept_missing_podcast(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    transcript_file,
    endpoint,
    stub_name,
    response_factory,
    expected_key,
    expected_value,
):
    monkeypatch.setattr(ai_mod, "_discover_transcript_for_episode", lambda *args, **kwargs: str(transcript_file))
    monkeypatch.setattr(ai_mod, "_discover_or_materialize_transcript", lambda *args, **kwargs: str(transcript_file))
    result = response_factory()
    monkeypatch.setattr(ai_mod, stub_name, lambda inp, result=result: result)

    payload = {
        "episode_id": str(uuid.uuid4()),
        "transcript_path": None,
        "hint": None,
        "base_prompt": "",
        "extra_instructions": None,
    }
    if endpoint.endswith("/tags"):
        payload["tags_always_include"] = []

    resp = client.post(endpoint, json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body[expected_key] == expected_value
