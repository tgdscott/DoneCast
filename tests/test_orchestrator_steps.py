import json
import types
from pathlib import Path

import pytest

from api.services.audio import orchestrator_steps as steps


class FakeAudio:
    pass


@pytest.fixture
def log():
    return []


def test_load_content_prefers_ws_root(monkeypatch, log):
    fname = 'cleaned_example.mp3'
    ws_media = steps.WS_ROOT / 'media_uploads'
    ws_media.mkdir(parents=True, exist_ok=True)
    target = ws_media / fname
    target.write_bytes(b'fake')

    monkeypatch.setattr(steps.AudioSegment, 'from_file', lambda path: FakeAudio())
    monkeypatch.setattr(steps.transcription, 'get_word_timestamps', lambda *_: [])

    content_path, audio, words, sanitized = steps.load_content_and_init_transcripts(fname, None, 'Episode Name', log)

    assert content_path == target
    assert isinstance(audio, FakeAudio)
    assert words == []
    assert sanitized == 'episode-name'


def test_load_content_scans_for_alternates(monkeypatch, log):
    requested = 'cleaned_missing_example.mp3'
    actual = 'missing_example.mp3'
    ws_media = steps.WS_ROOT / 'media_uploads'
    ws_media.mkdir(parents=True, exist_ok=True)
    alt_target = ws_media / actual
    alt_target.write_bytes(b'fake')

    monkeypatch.setattr(steps.AudioSegment, 'from_file', lambda path: FakeAudio())
    monkeypatch.setattr(steps.transcription, 'get_word_timestamps', lambda *_: [])

    content_path, audio, words, sanitized = steps.load_content_and_init_transcripts(
        requested, None, 'Episode Name 2', log
    )

    assert content_path == alt_target
    assert isinstance(audio, FakeAudio)
    assert words == []
    assert sanitized == 'episode-name-2'

def test_do_transcript_io_shape(monkeypatch, log):
    def fake_load(fname, words_json, out_name, log_, **kwargs):
        # No logs needed here; focus on shape
        return Path('media/foo.mp3'), FakeAudio(), [{'word': 'hello', 'start': 0.0, 'end': 0.1}], 'episode_sanitized'

    monkeypatch.setattr(steps, 'load_content_and_init_transcripts', fake_load)
    paths = {'audio_in': 'foo.mp3', 'output_name': 'episode', 'cover_art': None}
    out = steps.do_transcript_io(paths, {}, log)
    assert set(out.keys()) >= {'content_path', 'main_content_audio', 'words', 'sanitized_output_filename', 'output_filename', 'main_content_filename'}
    assert isinstance(out['content_path'], Path)
    assert isinstance(out['main_content_audio'], FakeAudio)
    assert out['sanitized_output_filename'] == 'episode_sanitized'
    assert out['output_filename'] == 'episode'


def test_do_intern_sfx_shape_and_logs(monkeypatch, log):
    def fake_detect(words, cleanup_options, words_json_path, mix_only, log_):
        log_.append('[AI_CFG] mix_only=False commands_keys=["intern"]')
        return [{'word': 'hello'}], {'intern': {}}, [{'cmd': 'insert'}], 1, 0

    monkeypatch.setattr(steps, 'detect_and_prepare_ai_commands', fake_detect)
    out = steps.do_intern_sfx({'words_json': None}, {'cleanup_options': {}}, log, words=[{'word': 'x'}])
    assert set(out.keys()) >= {'mutable_words', 'commands_cfg', 'ai_cmds', 'intern_count', 'flubber_count'}
    assert any('[AI_CFG]' in s for s in log)


def test_do_fillers_shape_and_logs(monkeypatch, log):
    def fake_primary(content_path, mutable_words, cleanup_options, mix_only, log_):
        log_.append('[FILLERS_CFG] remove_fillers=False filler_count=0 reasons=no_filler_words')
        return FakeAudio(), mutable_words, {'um': 3}, 2

    monkeypatch.setattr(steps, 'primary_cleanup_and_rebuild', fake_primary)
    out = steps.do_fillers({}, {'cleanup_options': {}}, log, content_path=Path('media/foo.mp3'), mutable_words=[{'word': 'x'}])
    assert set(out.keys()) >= {'cleaned_audio', 'mutable_words', 'filler_freq_map', 'filler_removed_count'}
    assert isinstance(out['cleaned_audio'], FakeAudio)
    assert any('[FILLERS_CFG]' in s for s in log)


def test_do_silence_shape_and_logs(monkeypatch, log):
    def fake_compress(cleaned_audio, cleanup_options, mix_only, mutable_words, log_):
        log_.append('[SILENCE] compressed')
        return cleaned_audio, mutable_words

    monkeypatch.setattr(steps, 'compress_pauses_step', fake_compress)
    out = steps.do_silence({}, {'cleanup_options': {}}, log, cleaned_audio=FakeAudio(), mutable_words=[{'word': 'x'}])
    assert set(out.keys()) >= {'cleaned_audio', 'mutable_words'}
    assert any('[SILENCE]' in s for s in log)


def test_do_tts_shape_and_logs(monkeypatch, log):
    def fake_exec(ai_cmds, cleaned_audio, orig_audio, tts_provider, api_key, enhancer, log_, insane_verbose, mutable_words, fast_mode):
        log_.append('[INTERN_CMD] executed')
        return cleaned_audio

    monkeypatch.setattr(steps, 'execute_intern_commands', fake_exec)
    out = steps.do_tts({}, {'tts_provider': 'elevenlabs'}, log, ai_cmds=[{'cmd': 'insert'}], cleaned_audio=FakeAudio(), content_path=Path('media/foo.mp3'), mutable_words=[{'word': 'x'}])
    assert set(out.keys()) >= {'cleaned_audio', 'ai_note_additions'}
    assert any('[INTERN_CMD]' in s for s in log)


def test_do_export_shape_and_logs(monkeypatch, log):
    def fake_export_cleaned(main_content_filename, cleaned_audio, log_):
        log_.append('Saved cleaned content to cleaned_foo.mp3')
        return 'cleaned_foo.mp3', Path('cleaned/cleaned_foo.mp3')

    def fake_build_mix(template, cleaned_audio, cleaned_filename, cleaned_path, main_content_filename, tts_overrides, tts_provider, api_key, output_filename, cover_image_path, log_):
        log_.append('[FINAL_MIX] duration_ms=1234')
        return Path('finals/episode.mp3'), [({'segment_type': 'content'}, FakeAudio(), 0, 1000)]

    def fake_write_transcripts(sanitized_output_filename, mutable_words, placements, template, main_content_filename, log_):
        log_.append('[TRANSCRIPTS] wrote final (content) episode.final.txt phrases=10')

    monkeypatch.setattr(steps, 'export_cleaned_audio_step', fake_export_cleaned)
    monkeypatch.setattr(steps, 'build_template_and_final_mix_step', fake_build_mix)
    monkeypatch.setattr(steps, 'write_final_transcripts_and_cleanup', fake_write_transcripts)

    paths = {'cover_art': None}
    cfg = {'tts_overrides': {}, 'tts_provider': 'elevenlabs'}
    out = steps.do_export(paths, cfg, log, template=types.SimpleNamespace(), cleaned_audio=FakeAudio(), main_content_filename='foo.mp3', output_filename='episode', cover_image_path=None, mutable_words=[{'word': 'x'}], sanitized_output_filename='episode')
    assert set(out.keys()) >= {'final_path', 'placements', 'cleaned_filename', 'cleaned_path'}
    assert any('Saved cleaned content' in s for s in log)
    assert any('[FINAL_MIX]' in s for s in log)
    assert any('[TRANSCRIPTS]' in s for s in log)


def test_streaming_mix_buffer_lazy_allocation():
    buf = steps._StreamingMixBuffer(
        frame_rate=44100,
        channels=2,
        sample_width=2,
        initial_duration_ms=60000,
    )

    # Initial allocation is deferred until audio is mixed.
    assert len(buf._buffer) == 0

    seg = steps.AudioSegment.silent(duration=1000, frame_rate=44100)
    buf.overlay(seg, 0)

    # After overlaying one second of stereo 16-bit audio we expect
    # frame_rate * seconds * channels * sample_width bytes.
    expected = 44100 * 1 * 2 * 2
    assert len(buf._buffer) == expected

    out = buf.to_segment()
    assert isinstance(out, steps.AudioSegment)
    assert len(out) >= 1000


def test_streaming_mix_buffer_limit(monkeypatch):
    monkeypatch.setattr(steps, "MAX_MIX_BUFFER_BYTES", 1024, raising=False)
    seg = steps.AudioSegment.silent(duration=1000, frame_rate=44100)
    buf = steps._StreamingMixBuffer(
        frame_rate=44100,
        channels=2,
        sample_width=2,
    )

    with pytest.raises(steps.TemplateTimelineTooLargeError):
        buf.overlay(seg, 0, label="content")


def test_build_mix_rejects_huge_timeline(monkeypatch, log):
    monkeypatch.setattr(steps, "MAX_MIX_BUFFER_BYTES", 1024, raising=False)
    monkeypatch.setattr(steps, "match_target_dbfs", lambda audio, *_, **__: audio)

    template = types.SimpleNamespace(
        segments_json=json.dumps(
            [
                {
                    "id": "content",
                    "segment_type": "content",
                }
            ]
        ),
        background_music_rules_json="[]",
        timing_json=json.dumps({"content_start_offset_s": 120.0}),
    )
    cleaned_audio = steps.AudioSegment.silent(duration=1000, frame_rate=44100)

    with pytest.raises(steps.TemplateTimelineTooLargeError):
        steps.build_template_and_final_mix_step(
            template,
            cleaned_audio,
            "cleaned_content.mp3",
            Path("cleaned/cleaned_content.mp3"),
            "episode.mp3",
            {},
            "elevenlabs",
            None,
            "episode",
            None,
            log,
    )

    assert any("[TEMPLATE_TIMELINE_TOO_LARGE]" in entry for entry in log)


def test_background_music_streams_in_chunks(monkeypatch, log, tmp_path):
    calls = []
    orig_overlay = steps._StreamingMixBuffer.overlay

    def spy_overlay(self, segment, position_ms, *, label="segment"):
        calls.append((len(segment), position_ms, label))
        return orig_overlay(self, segment, position_ms, label=label)

    monkeypatch.setattr(steps._StreamingMixBuffer, "overlay", spy_overlay)
    monkeypatch.setattr(steps, "BACKGROUND_LOOP_CHUNK_MS", 5000, raising=False)
    monkeypatch.setattr(steps, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(steps, "MEDIA_DIR", tmp_path)
    monkeypatch.setattr(steps, "match_target_dbfs", lambda audio, *_, **__: audio)
    monkeypatch.setattr(steps, "normalize_master", lambda *a, **k: None)
    monkeypatch.setattr(steps, "mux_tracks", lambda *a, **k: None)
    monkeypatch.setattr(steps, "write_derivatives", lambda *a, **k: {})
    monkeypatch.setattr(steps, "embed_metadata", lambda *a, **k: None)
    monkeypatch.setattr(steps.AudioSegment, "export", lambda self, *a, **k: None, raising=False)

    background_audio = steps.AudioSegment.silent(duration=1200, frame_rate=44100)

    def fake_from_file(path):
        return background_audio

    monkeypatch.setattr(steps.AudioSegment, "from_file", fake_from_file)

    music_path = steps.MEDIA_DIR / "bg.mp3"
    music_path.parent.mkdir(parents=True, exist_ok=True)
    music_path.write_bytes(b"stub")

    template = types.SimpleNamespace(
        segments_json=json.dumps([
            {
                "id": "content",
                "segment_type": "content",
            }
        ]),
        background_music_rules_json=json.dumps(
            [
                {
                    "music_filename": "bg.mp3",
                    "apply_to_segments": ["content"],
                    "start_offset_s": 0,
                    "end_offset_s": 0,
                    "fade_in_s": 0.5,
                    "fade_out_s": 0.5,
                    "volume_db": -3.0,
                }
            ]
        ),
        timing_json=json.dumps({}),
    )

    cleaned_audio = steps.AudioSegment.silent(duration=20_000, frame_rate=44100)

    final_path, placements = steps.build_template_and_final_mix_step(
        template,
        cleaned_audio,
        "cleaned_content.mp3",
        tmp_path / "cleaned_content.mp3",
        "episode.mp3",
        {},
        "elevenlabs",
        None,
        "episode",
        None,
        log,
    )

    assert final_path.name.endswith(".mp3")
    assert placements

    background_calls = [c for c in calls if c[2].startswith("background:")]
    assert background_calls, "expected background overlays to be invoked"
    max_chunk = max(length for length, _pos, _label in background_calls)
    assert max_chunk <= 5000

    positions = [pos for _length, pos, label in background_calls]
    assert min(positions) == 0
    assert max(positions) >= 15_000
