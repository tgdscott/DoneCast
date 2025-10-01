import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from api.services.episodes import assembler


def _make_template():
    return SimpleNamespace(
        segments_json=json.dumps(
            [
                {"segment_type": "intro", "source": {"source_type": "static", "filename": "intro.mp3"}},
                {"segment_type": "content", "source": {"source_type": "static", "filename": "content.mp3"}},
                {"segment_type": "outro", "source": {"source_type": "static", "filename": "outro.mp3"}},
            ]
        )
    )


def _duration_stub(name_map):
    def _inner(filename):
        key = str(filename).split("/")[-1]
        return name_map.get(key)

    return _inner


def test_minutes_precheck_allows(monkeypatch):
    user = SimpleNamespace(id=uuid4(), tier="creator", subscription_expires_at=None)
    template = _make_template()

    monkeypatch.setattr(assembler.repo, "get_template_by_id", lambda session, tid: template)
    monkeypatch.setattr(assembler.usage_svc, "month_minutes_used", lambda *args, **kwargs: 30)
    durations = {"content.mp3": 600.0, "intro.mp3": 45.0, "outro.mp3": 30.0}
    monkeypatch.setattr(assembler, "_estimate_audio_seconds", _duration_stub(durations))

    result = assembler.minutes_precheck(
        session=None,
        current_user=user,
        template_id=str(uuid4()),
        main_content_filename="content.mp3",
    )

    assert result["allowed"] is True
    assert result["minutes_required"] == 12
    assert pytest.approx(result["static_seconds"], rel=1e-6) == durations["intro.mp3"] + durations["outro.mp3"]
    remaining = assembler.TIER_LIMITS["creator"]["max_processing_minutes_month"] - 30
    assert result["minutes_remaining"] == remaining


def test_minutes_precheck_blocks_when_over(monkeypatch):
    user = SimpleNamespace(id=uuid4(), tier="free", subscription_expires_at=None)
    template = _make_template()

    monkeypatch.setattr(assembler.repo, "get_template_by_id", lambda session, tid: template)
    monkeypatch.setattr(assembler.usage_svc, "month_minutes_used", lambda *args, **kwargs: 55)
    durations = {"content.mp3": 900.0, "intro.mp3": 60.0, "outro.mp3": 45.0}
    monkeypatch.setattr(assembler, "_estimate_audio_seconds", _duration_stub(durations))

    result = assembler.minutes_precheck(
        session=None,
        current_user=user,
        template_id=str(uuid4()),
        main_content_filename="content.mp3",
    )

    assert result["allowed"] is False
    detail = result.get("detail") or {}
    assert detail.get("code") == "INSUFFICIENT_MINUTES"
    assert detail.get("source") == "precheck"
    assert detail.get("minutes_required") == result["minutes_required"]
    assert detail.get("minutes_remaining") == max(0, result["minutes_remaining"])
