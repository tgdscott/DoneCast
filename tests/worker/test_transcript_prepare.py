from pathlib import Path

import json

import pytest


@pytest.fixture(autouse=True)
def _isolate_dirs(tmp_path, monkeypatch):
    from backend.worker.tasks.assembly import transcript as transcript_module

    media_dir = tmp_path / "media"
    ws_root = tmp_path / "workspace"
    media_dir.mkdir(parents=True, exist_ok=True)
    ws_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(transcript_module, "MEDIA_DIR", media_dir)
    monkeypatch.setattr(transcript_module, "PROJECT_ROOT", ws_root)

    yield transcript_module, media_dir, ws_root


def test_prepare_transcript_context_mirrors_cleaned_audio(tmp_path, _isolate_dirs, monkeypatch):
    transcript_module, media_dir, ws_root = _isolate_dirs

    from backend.worker.tasks.assembly.media import MediaContext

    words_json = tmp_path / "words.json"
    words_json.write_text("[]", encoding="utf-8")

    audio_src = tmp_path / "input.wav"
    audio_src.write_bytes(b"input-bytes")

    cleaned_dir = tmp_path / "cleaned"
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    engine_output = cleaned_dir / "cleaned_input.mp3"
    engine_output.write_bytes(b"cleaned-bytes")

    def _fake_run_all(**kwargs):
        return {"final_path": str(engine_output)}

    monkeypatch.setattr(transcript_module.clean_engine, "run_all", _fake_run_all)

    class _Episode:
        def __init__(self):
            self.user_id = "user-1"
            self.meta_json = "{}"
            self.working_audio_name = audio_src.name

    episode = _Episode()

    class _User:
        elevenlabs_api_key = None

    media_context = MediaContext(
        template=None,
        episode=episode,
        user=_User(),
        cover_image_path=None,
        cleanup_settings={},
        preferred_tts_provider="elevenlabs",
        base_audio_name=audio_src.name,
        source_audio_path=audio_src,
        base_stems=[Path(audio_src).stem],
        search_dirs=[tmp_path],
    )

    class _Result:
        @staticmethod
        def all():
            return []

    class _Session:
        def add(self, obj):
            return None

        def commit(self):
            return None

        def rollback(self):
            return None

        def exec(self, query):
            return _Result()

    session = _Session()

    ctx = transcript_module.prepare_transcript_context(
        session=session,
        media_context=media_context,
        words_json_path=words_json,
        main_content_filename=audio_src.name,
        output_filename="episode",
        tts_values={},
        user_id="user-1",
        intents={},
    )

    assert ctx.cleaned_path == engine_output
    assert (media_dir / engine_output.name).exists()
    assert (media_dir / "media_uploads" / engine_output.name).exists()
    assert (ws_root / "media_uploads" / engine_output.name).exists()
    assert episode.working_audio_name == engine_output.name
    assert json.loads(episode.meta_json)["cleaned_audio"] == engine_output.name


def test_prepare_transcript_context_uploads_cleaned_audio(monkeypatch, tmp_path, _isolate_dirs):
    transcript_module, media_dir, ws_root = _isolate_dirs

    from backend.worker.tasks.assembly.media import MediaContext

    words_json = tmp_path / "words.json"
    words_json.write_text("[]", encoding="utf-8")

    audio_src = tmp_path / "input.wav"
    audio_src.write_bytes(b"input-bytes")

    cleaned_dir = tmp_path / "cleaned"
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    engine_output = cleaned_dir / "cleaned_input.mp3"
    engine_output.write_bytes(b"cleaned-bytes")

    def _fake_run_all(**kwargs):
        return {"final_path": str(engine_output)}

    monkeypatch.setattr(transcript_module.clean_engine, "run_all", _fake_run_all)

    class _Episode:
        def __init__(self):
            self.user_id = "user-2"
            self.meta_json = "{}"
            self.working_audio_name = audio_src.name

    episode = _Episode()

    class _User:
        elevenlabs_api_key = None

    media_context = MediaContext(
        template=None,
        episode=episode,
        user=_User(),
        cover_image_path=None,
        cleanup_settings={},
        preferred_tts_provider="elevenlabs",
        base_audio_name=audio_src.name,
        source_audio_path=audio_src,
        base_stems=[Path(audio_src).stem],
        search_dirs=[tmp_path],
    )

    class _Result:
        @staticmethod
        def all():
            return []

    class _Session:
        def add(self, obj):
            return None

        def commit(self):
            return None

        def rollback(self):
            return None

        def exec(self, query):
            return _Result()

    session = _Session()

    uploads: list[tuple[str, str, bytes]] = []

    class _GCS:
        def upload_fileobj(self, bucket, key, fileobj, content_type=None):
            data = fileobj.read()
            uploads.append((bucket, key, data))
            fileobj.seek(0)
            return f"gs://{bucket}/{key}"

    monkeypatch.setattr(transcript_module, "gcs_utils", _GCS())
    monkeypatch.setenv("MEDIA_BUCKET", "test-bucket")

    transcript_module.prepare_transcript_context(
        session=session,
        media_context=media_context,
        words_json_path=words_json,
        main_content_filename=audio_src.name,
        output_filename="episode",
        tts_values={},
        user_id="user-2",
        intents={},
    )

    assert uploads == [("test-bucket", "user-2/cleaned_audio/cleaned_input.mp3", b"cleaned-bytes")]
    meta = json.loads(episode.meta_json)
    assert meta["cleaned_audio"] == engine_output.name
    assert meta["cleaned_audio_sources"]["primary"] == "gs://test-bucket/user-2/cleaned_audio/cleaned_input.mp3"
    assert meta["cleaned_audio_bucket_key"] == "user-2/cleaned_audio/cleaned_input.mp3"
    assert meta["cleaned_audio_bucket"] == "test-bucket"
