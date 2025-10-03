import json
import logging
from uuid import uuid4

import pytest


@pytest.fixture(autouse=True)
def _ensure_clean(tmp_path, monkeypatch):
    from backend.worker.tasks.assembly import media as media_module

    ws_root = tmp_path / "ws_root"
    ws_root.mkdir(parents=True, exist_ok=True)
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(media_module, "PROJECT_ROOT", ws_root)
    monkeypatch.setattr(media_module, "APP_ROOT_DIR", ws_root)
    monkeypatch.setattr(media_module, "MEDIA_DIR", media_dir)

    yield


def test_resolve_media_promotes_from_workspace(tmp_path):
    from backend.worker.tasks.assembly import media as media_module

    upload_dir = media_module.PROJECT_ROOT / "media_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    sample = upload_dir / "example.mp3"
    sample.write_bytes(b"demo-bytes")

    resolved = media_module._resolve_media_file(sample.name)

    assert resolved == media_module.MEDIA_DIR / sample.name
    assert resolved.exists()
    assert resolved.read_bytes() == b"demo-bytes"


def test_resolve_media_returns_existing_media(tmp_path):
    from backend.worker.tasks.assembly import media as media_module

    target = media_module.MEDIA_DIR / "existing.wav"
    target.write_bytes(b"audio")

    resolved = media_module._resolve_media_file(target.name)

    assert resolved == target
    assert resolved.read_bytes() == b"audio"


def test_resolve_media_handles_uploader_sanitization(tmp_path):
    """Filenames saved by the upload endpoint preserve casing and use underscores."""

    from backend.worker.tasks.assembly import media as media_module

    original_name = "Demo Episode: What's New?.mp3"
    sanitized = "Demo_Episode__What_s_New_.mp3"

    durable = media_module.MEDIA_DIR / sanitized
    durable.write_bytes(b"durable")

    resolved = media_module._resolve_media_file(original_name)

    assert resolved == durable
    assert resolved.read_bytes() == b"durable"


def test_resolve_media_downloads_sanitized_transcript(monkeypatch, caplog):
    """Ensure bucket_stem hints fetch sanitized transcripts without noisy failures."""

    from backend.worker.tasks.assembly import media as media_module

    caplog.set_level(logging.INFO)

    bucket_name = "demo-bucket"
    bucket_stem = "demo-episode"
    expected_key = f"transcripts/{bucket_stem}.json"
    requested: list[tuple[str, str]] = []

    def _fake_download(bucket: str, key: str) -> bytes:
        requested.append((bucket, key))
        assert bucket == bucket_name
        assert key == expected_key
        return b"{}"

    monkeypatch.setattr(
        "backend.infrastructure.gcs.download_gcs_bytes",
        _fake_download,
    )

    template_id = uuid4()
    user_id = uuid4()
    episode_id = uuid4()

    class _Template:
        pass

    template = _Template()

    class _Episode:
        def __init__(self) -> None:
            self.id = episode_id
            self.status = "pending"
            self.final_audio_path = None
            self.meta_json = json.dumps(
                {
                    "transcripts": {
                        "bucket_stem": bucket_stem,
                        "stem": "Demo Episode",
                        "gcs_bucket": bucket_name,
                    }
                }
            )
            self.working_audio_name = None

    episode = _Episode()

    class _User:
        elevenlabs_api_key = None

    def _get_template(session, template_uuid):
        assert str(template_uuid) == str(template_id)
        return template

    def _get_episode(session, episode_uuid):
        assert str(episode_uuid) == str(episode_id)
        return episode

    def _get_user(session, user_uuid):
        return _User()

    monkeypatch.setattr(media_module.crud, "get_template_by_id", _get_template)
    monkeypatch.setattr(media_module.crud, "get_episode_by_id", _get_episode)
    monkeypatch.setattr(media_module.crud, "get_user_by_id", _get_user)

    class _Session:
        def add(self, obj):  # pragma: no cover - no-op for stub
            return None

        def commit(self):  # pragma: no cover - no-op for stub
            return None

        def rollback(self):  # pragma: no cover - no-op for stub
            return None

        def exec(self, query):  # pragma: no cover - deterministic empty result
            class _Result:
                def all(self_inner):
                    return []

            return _Result()

    session = _Session()

    _, words_path, _ = media_module.resolve_media_context(
        session=session,
        episode_id=str(episode_id),
        template_id=str(template_id),
        main_content_filename="missing.mp3",
        output_filename="output.mp3",
        episode_details={},
        user_id=str(user_id),
    )

    assert words_path is not None
    assert words_path.exists()
    assert words_path.read_bytes() == b"{}"
    assert requested == [(bucket_name, expected_key)]
    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]
