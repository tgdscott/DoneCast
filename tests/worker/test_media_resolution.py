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
