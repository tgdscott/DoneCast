from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest


def _stub_episode() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        final_audio_path="final.mp3",
        title="Inline Episode",
        show_notes="Inline show notes",
    )


def _stub_user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), spreaker_access_token="token")


class _StubTask:
    def __init__(self) -> None:
        self.apply_calls = 0
        self.apply_async_calls = 0

    def apply(self, args=(), kwargs=None):  # pragma: no cover - signature compatibility
        self.apply_calls += 1
        return SimpleNamespace(result={"status": "inline"})

    def apply_async(self, *_, **__):  # pragma: no cover - signature compatibility
        self.apply_async_calls += 1
        raise AssertionError("apply_async should not be called when workers are unavailable")


class _StubCeleryControl:
    def ping(self, timeout=None):  # pragma: no cover - signature compatibility
        return []


class _StubCeleryApp:
    def __init__(self) -> None:
        self.conf = SimpleNamespace(task_always_eager=False)
        self.control = _StubCeleryControl()


@pytest.mark.parametrize("auto_fallback_env", ["1", "true", "TRUE", "yes", "on"])
def test_inline_fallback_skips_async(monkeypatch, caplog, auto_fallback_env):
    from backend.api.services.episodes import publisher

    caplog.set_level("WARNING")

    task = _StubTask()
    celery = _StubCeleryApp()
    episode = _stub_episode()
    user = _stub_user()

    monkeypatch.setenv("CELERY_AUTO_FALLBACK", auto_fallback_env)
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setattr(publisher, "publish_episode_to_spreaker_task", task)
    monkeypatch.setattr(publisher, "celery_app", celery)
    monkeypatch.setattr(
        publisher,
        "repo",
        SimpleNamespace(get_episode_by_id=lambda *_args, **_kwargs: episode),
    )

    result = publisher.publish(
        session=None,
        current_user=user,
        episode_id=episode.id,
        derived_show_id="show",
        publish_state="draft",
        auto_publish_iso=None,
    )

    assert task.apply_calls == 1
    assert task.apply_async_calls == 0
    assert result["job_id"] == "inline"
    assert result.get("worker_status", {}).get("available") is False
    assert "No Celery workers detected" in caplog.text
