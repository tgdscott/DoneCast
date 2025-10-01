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
    def fake_load(fname, words_json, out_name, log_):
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
