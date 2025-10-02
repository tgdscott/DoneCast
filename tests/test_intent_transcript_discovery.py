from __future__ import annotations
import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import api.routers.ai_suggestions as ai_suggestions


@pytest.fixture(autouse=True)
def _reset_download_helpers(monkeypatch):
    """Prevent network access during tests by stubbing download helpers."""

    monkeypatch.setattr(ai_suggestions, "_download_transcript_from_bucket", lambda *_, **__: None)
    monkeypatch.setattr(ai_suggestions, "_download_transcript_from_url", lambda *_, **__: None)


def test_discover_transcript_json_path_handles_sanitized_hint(monkeypatch, tmp_path):
    """Upper/lower-case differences in hints should still resolve transcripts."""

    monkeypatch.setattr(ai_suggestions, "TRANSCRIPTS_DIR", tmp_path)

    unique_prefix = uuid.uuid4().hex
    hint = f"gs://bucket/{unique_prefix}_Stereo_Mix.mp3"
    stem = f"{unique_prefix}_stereo_mix"
    transcript_path = tmp_path / f"{stem}.json"
    transcript_path.write_text("[]", encoding="utf-8")

    resolved = ai_suggestions._discover_transcript_json_path(MagicMock(), None, hint)
    assert resolved == transcript_path


def test_discover_transcript_json_path_downloads_from_bucket(monkeypatch, tmp_path):
    """Bucket download helper should be used when local files are missing."""

    monkeypatch.setattr(ai_suggestions, "TRANSCRIPTS_DIR", tmp_path)

    stem = uuid.uuid4().hex
    called: dict[str, str] = {}

    def fake_bucket_download(stem_value: str, user_id=None):  # type: ignore[unused-arg]
        called["stem"] = stem_value
        path = tmp_path / f"{stem_value}.json"
        path.write_text("[]", encoding="utf-8")
        return path

    monkeypatch.setattr(ai_suggestions, "_download_transcript_from_bucket", fake_bucket_download)

    hint = f"gs://bucket/{stem}.mp3"
    resolved = ai_suggestions._discover_transcript_json_path(MagicMock(), None, hint)

    assert resolved == tmp_path / f"{stem}.json"
    assert called["stem"] == stem


def test_discover_transcript_json_path_uses_remote_meta_url(monkeypatch, tmp_path):
    """Remote transcript URLs in episode meta should be downloaded when needed."""

    monkeypatch.setattr(ai_suggestions, "TRANSCRIPTS_DIR", tmp_path)

    stem = "remote-transcript"
    episode_id = uuid.uuid4()
    remote_url = f"https://example.com/{stem}.json"

    episode = MagicMock()
    episode.user_id = uuid.uuid4()
    episode.working_audio_name = None
    episode.final_audio_path = None
    episode.meta_json = json.dumps({"transcripts": {"gcs_json": remote_url}})

    monkeypatch.setattr(ai_suggestions._ep_repo, "get_episode_by_id", lambda *_: episode)

    def fake_url_download(url: str):
        if url.startswith("http"):
            path = tmp_path / f"{stem}.json"
            path.write_text("[]", encoding="utf-8")
            return path
        return None

    monkeypatch.setattr(ai_suggestions, "_download_transcript_from_url", fake_url_download)

    resolved = ai_suggestions._discover_transcript_json_path(MagicMock(), str(episode_id), None)

    assert isinstance(resolved, Path)
    assert resolved.name == f"{stem}.json"
    assert resolved.exists()
