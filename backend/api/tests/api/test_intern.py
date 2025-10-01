from pathlib import Path
import importlib

import pytest

_REQUIRED_ENV = {
    "DB_USER": "test",
    "DB_PASS": "test",
    "DB_NAME": "test",
    "INSTANCE_CONNECTION_NAME": "test",
    "GEMINI_API_KEY": "test",
    "ELEVENLABS_API_KEY": "test",
    "ASSEMBLYAI_API_KEY": "test",
    "SPREAKER_API_TOKEN": "test",
    "SPREAKER_CLIENT_ID": "test",
    "SPREAKER_CLIENT_SECRET": "test",
    "GOOGLE_CLIENT_ID": "test",
    "GOOGLE_CLIENT_SECRET": "test",
    "STRIPE_SECRET_KEY": "test",
    "STRIPE_WEBHOOK_SECRET": "test",
}


class _StubSegment:
    def __init__(self, should_fail_mp3: bool, tmp_path: Path):
        self.should_fail_mp3 = should_fail_mp3
        self.tmp_path = tmp_path
        self.export_calls = []

    def __getitem__(self, item):  # pragma: no cover - slicing interface passthrough
        return self

    def export(self, out_path, format="mp3"):
        self.export_calls.append((Path(out_path), format))
        path = Path(out_path)
        if format == "mp3" and self.should_fail_mp3:
            raise RuntimeError("ffmpeg not available")
        path.write_bytes(b"stub")
        return path


@pytest.mark.parametrize("fail_mp3", [False, True])
def test_export_snippet_handles_missing_ffmpeg(tmp_path, monkeypatch, fail_mp3):
    for key, value in _REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)

    intern = importlib.reload(importlib.import_module("api.routers.intern"))

    monkeypatch.setattr(intern, "INTERN_CTX_DIR", tmp_path)

    segment = _StubSegment(fail_mp3, tmp_path)

    name, path = intern._export_snippet(segment, "Interview.Episode.mp3", 0.0, 1.5, suffix="intern")

    if fail_mp3:
        assert path.suffix == ".wav"
        assert name.endswith(".wav")
    else:
        assert path.suffix == ".mp3"
        assert name.endswith(".mp3")

    assert path.exists()
    assert path.read_bytes() == b"stub"

    # Ensure we attempted mp3 first when it fails.
    if fail_mp3:
        assert (tmp_path / name).suffix == ".wav"
        assert segment.export_calls[0][1] == "mp3"
        assert segment.export_calls[1][1] == "wav"
    else:
        assert segment.export_calls == [(path, "mp3")]
