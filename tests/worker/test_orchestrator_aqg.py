import types
import uuid
import tempfile
import wave
from contextlib import contextmanager
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from api.models.enums import EpisodeStatus
from backend.worker.tasks.assembly import oldorchestrator as orch


class FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False
        self.rolled_back = False

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def refresh(self, obj):
        return obj


class FakeEpisode:
    def __init__(self, episode_id, user_id, podcast_id, status=EpisodeStatus.pending):
        self.id = episode_id
        self.user_id = user_id
        self.podcast_id = podcast_id
        # Use valid UUID strings so orchestrator UUID parsing does not fail in tests.
        self.status = status
        self.meta_json = "{}"


def _make_temp_audio():
    path = Path(tempfile.gettempdir()) / "aqg_dummy_main.wav"
    # Use an explicit file handle for Python 3.12 wave.open compatibility and write a valid PCM WAV.
    with open(path, "wb") as raw_fh:
        with wave.open(raw_fh, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(8000)
            wf.writeframes(b"\x00\x00" * 8000)  # 1 second of silence
    return path


def _patch_crud(monkeypatch, episode, user, podcast):
    monkeypatch.setattr(
        orch,
        "crud",
        types.SimpleNamespace(
            get_episode_by_id=lambda session, _id: episode,
            get_user_by_id=lambda session, _id: user,
            get_podcast_by_id=lambda session, _id: podcast,
        ),
    )


def _patch_session_scope(monkeypatch, session):
    @contextmanager
    def _scope():
        yield session

    monkeypatch.setattr(orch, "session_scope", _scope)


def test_aqg_pauses_and_short_circuits(monkeypatch):
    session = FakeSession()
    episode = FakeEpisode(str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()))
    user = types.SimpleNamespace(audio_gate_settings={})
    podcast = types.SimpleNamespace(id=str(uuid.uuid4()))
    temp_audio = _make_temp_audio()

    _patch_crud(monkeypatch, episode, user, podcast)
    _patch_session_scope(monkeypatch, session)

    async def _pause(**kwargs):
        sess = kwargs.get("session")
        episode.status = EpisodeStatus.awaiting_audio_decision
        if sess:
            sess.commit()
        return {"status": "paused", "episode_id": str(episode.id)}

    monkeypatch.setattr(orch, "_handle_audio_decision", _pause)

    result = orch.orchestrate_create_podcast_episode(
        episode_id=str(episode.id),
        template_id="tpl1",
        main_content_filename=str(temp_audio),
        output_filename="out.wav",
        tts_values={},
        episode_details={},
        user_id=str(episode.user_id),
        podcast_id=str(episode.podcast_id),
    )

    assert result["status"] == "paused"
    assert episode.status == EpisodeStatus.awaiting_audio_decision
    assert session.committed is True


def test_failure_sets_failed_status(monkeypatch):
    session = FakeSession()
    episode = FakeEpisode(str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()))
    user = types.SimpleNamespace(audio_gate_settings={})
    podcast = types.SimpleNamespace(id=str(uuid.uuid4()))
    temp_audio = _make_temp_audio()

    _patch_crud(monkeypatch, episode, user, podcast)
    _patch_session_scope(monkeypatch, session)

    async def _continue_decision(**kwargs):
        return {"status": "continue", "use_auphonic": False}

    monkeypatch.setattr(orch, "_handle_audio_decision", _continue_decision)
    monkeypatch.setattr(orch, "audio_process_and_assemble_episode", lambda **kwargs: Path("/tmp/placeholder.mp3"), raising=False)
    monkeypatch.setattr(orch, "media", types.SimpleNamespace(resolve_media_context=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))))

    with pytest.raises(RuntimeError):
        orch.orchestrate_create_podcast_episode(
            episode_id=str(episode.id),
            template_id="tpl2",
                main_content_filename=str(temp_audio),
            output_filename="out.wav",
            tts_values={},
            episode_details={},
            user_id=str(episode.user_id),
            podcast_id=str(episode.podcast_id),
        )

    assert episode.status == EpisodeStatus.failed
    assert session.committed is True


def test_happy_path_sets_processed(monkeypatch):
    session = FakeSession()
    episode = FakeEpisode(str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()))
    user = types.SimpleNamespace(audio_gate_settings={})
    podcast = types.SimpleNamespace(id=str(uuid.uuid4()))

    _patch_crud(monkeypatch, episode, user, podcast)
    _patch_session_scope(monkeypatch, session)

    async def _continue_decision(**kwargs):
        return {"status": "continue", "use_auphonic": False}

    monkeypatch.setattr(orch, "_handle_audio_decision", _continue_decision)
    monkeypatch.setattr(orch, "audio_process_and_assemble_episode", lambda **kwargs: Path("/tmp/final.mp3"), raising=False)
    monkeypatch.setattr(orch, "transcribe_episode", lambda **kwargs: {"words_json_path": "/tmp/words.json"})

    temp_audio = _make_temp_audio()
    dummy_media_ctx = types.SimpleNamespace(
        cover_image_path=None,
        preferred_tts_provider=None,
        elevenlabs_api_key=None,
        source_audio_path=temp_audio,
    )
    monkeypatch.setattr(orch, "media", types.SimpleNamespace(resolve_media_context=lambda **kwargs: (dummy_media_ctx, None, None)))
    monkeypatch.setattr(orch, "transcript", types.SimpleNamespace(prepare_transcript_context=lambda **kwargs: "ctx"))
    monkeypatch.setattr(orch, "_finalize_episode", lambda **kwargs: {"message": "ok"})

    result = orch.orchestrate_create_podcast_episode(
        episode_id=str(episode.id),
        template_id="tpl3",
        main_content_filename=str(temp_audio),
        output_filename="out.wav",
        tts_values={},
        episode_details={},
        user_id=str(episode.user_id),
        podcast_id=str(episode.podcast_id),
    )

    assert result == {"message": "ok"}
    assert episode.status in {EpisodeStatus.processed, EpisodeStatus.completed}
    assert session.committed is True


def test_asyncio_run_is_isolated_per_call(monkeypatch):
    ep_a_id, ep_b_id = uuid.uuid4(), uuid.uuid4()
    user_a_id, user_b_id = uuid.uuid4(), uuid.uuid4()
    pod_a_id, pod_b_id = uuid.uuid4(), uuid.uuid4()

    episodes = {
        ep_a_id: FakeEpisode(ep_a_id, user_a_id, pod_a_id),
        ep_b_id: FakeEpisode(ep_b_id, user_b_id, pod_b_id),
    }
    users = {
        user_a_id: types.SimpleNamespace(audio_gate_settings={}),
        user_b_id: types.SimpleNamespace(audio_gate_settings={}),
    }
    podcasts = {
        pod_a_id: types.SimpleNamespace(id=pod_a_id),
        pod_b_id: types.SimpleNamespace(id=pod_b_id),
    }
    sessions = {}

    @contextmanager
    def _scope():
        sess = FakeSession()
        sessions[id(sess)] = sess
        yield sess

    monkeypatch.setattr(orch, "session_scope", _scope)
    monkeypatch.setattr(
        orch,
        "crud",
        types.SimpleNamespace(
            get_episode_by_id=lambda _s, _id: episodes[_id],
            get_user_by_id=lambda _s, _id: users[_id],
            get_podcast_by_id=lambda _s, _id: podcasts[_id],
        ),
    )

    async def _continue_decision(**kwargs):
        return {"status": "continue", "use_auphonic": False}

    monkeypatch.setattr(orch, "_handle_audio_decision", _continue_decision)
    monkeypatch.setattr(orch, "audio_process_and_assemble_episode", lambda **kwargs: Path("/tmp/final.mp3"), raising=False)
    monkeypatch.setattr(orch, "transcribe_episode", lambda **kwargs: {"words_json_path": "/tmp/words.json"})

    temp_audio = _make_temp_audio()
    dummy_media_ctx = types.SimpleNamespace(
        cover_image_path=None,
        preferred_tts_provider=None,
        elevenlabs_api_key=None,
        source_audio_path=temp_audio,
    )
    monkeypatch.setattr(orch, "media", types.SimpleNamespace(resolve_media_context=lambda **kwargs: (dummy_media_ctx, None, None)))
    monkeypatch.setattr(orch, "transcript", types.SimpleNamespace(prepare_transcript_context=lambda **kwargs: "ctx"))
    monkeypatch.setattr(orch, "_finalize_episode", lambda **kwargs: {"message": "ok"})

    def _run(eid: uuid.UUID):
        return orch.orchestrate_create_podcast_episode(
            episode_id=str(eid),
            template_id="tpl",
                main_content_filename=str(temp_audio),
            output_filename="out.wav",
            tts_values={},
            episode_details={},
            user_id=str(episodes[eid].user_id),
            podcast_id=str(episodes[eid].podcast_id),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_run, episodes.keys()))

    assert results == [{"message": "ok"}, {"message": "ok"}]
    assert episodes[ep_a_id].status in {EpisodeStatus.processed, EpisodeStatus.completed}
    assert episodes[ep_b_id].status in {EpisodeStatus.processed, EpisodeStatus.completed}
    assert all(sess.committed for sess in sessions.values())
