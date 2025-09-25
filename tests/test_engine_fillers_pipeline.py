# pyright: reportGeneralTypeIssues=false
import os, sys, json, types, importlib
import tempfile
import unittest
from types import SimpleNamespace

# Ensure fresh imports so our pydub stub is honored across the full suite
for m in [
    'pydub',
    'pydub.silence',
    'api.services.clean_engine.engine',
]:
    sys.modules.pop(m, None)

# --- Stub pydub.AudioSegment with minimal behavior used by engine ---
class _StubAudioSegment:
    def __init__(self, duration=0):
        self._duration = int(duration)
    def __len__(self):
        return self._duration
    def __getitem__(self, s):
        # slice by ms
        if isinstance(s, slice):
            start = 0 if s.start is None else int(max(0, s.start))
            stop = self._duration if s.stop is None else int(min(self._duration, s.stop))
            if stop < start:
                stop = start
            return _StubAudioSegment(stop - start)
        raise TypeError("slice only")
    def __add__(self, other):
        if isinstance(other, _StubAudioSegment):
            return _StubAudioSegment(self._duration + len(other))
        return NotImplemented
    @classmethod
    def silent(cls, duration=0):
        return cls(int(duration))
    @classmethod
    def from_file(cls, *_args, **_kwargs):
        # pretend any input file is 2000ms long
        return cls(2000)
    def export(self, *_args, **_kwargs):
        # no-op
        return b""

pydub_stub = types.ModuleType('pydub')
setattr(pydub_stub, 'AudioSegment', _StubAudioSegment)
sys.modules['pydub'] = pydub_stub

# --- Point sys.path to the package root ---
ROOT = os.path.dirname(os.path.dirname(__file__))
PKG_ROOT = os.path.join(ROOT, 'backend')
if PKG_ROOT not in sys.path:
    sys.path.insert(0, PKG_ROOT)

# --- Create namespace-like packages to override features with stubs ---
api_pkg = types.ModuleType('api'); api_pkg.__path__ = [os.path.join(PKG_ROOT, 'api')]  # type: ignore[attr-defined]
services_pkg = types.ModuleType('api.services'); services_pkg.__path__ = [os.path.join(PKG_ROOT, 'api', 'services')]  # type: ignore[attr-defined]
clean_pkg = types.ModuleType('api.services.clean_engine'); clean_pkg.__path__ = [os.path.join(PKG_ROOT, 'api', 'services', 'clean_engine')]  # type: ignore[attr-defined]
sys.modules['api'] = api_pkg
sys.modules['api.services'] = services_pkg
sys.modules['api.services.clean_engine'] = clean_pkg

# Provide a stub features module consumed by engine
features_stub = types.ModuleType('api.services.clean_engine.features')

def _ensure_ffmpeg():
    return None

def _apply_flubber_cuts(audio, cuts):
    # Emulate cut splicing: concatenate segments outside cuts
    if not cuts:
        return audio
    cuts = sorted(cuts)
    out = _StubAudioSegment.silent(0)
    cursor = 0
    for s, e in cuts:
        out = out + audio[cursor:s]
        cursor = e
    out = out + audio[cursor:]
    return out

def _insert_intern_responses(audio, *_args, **_kwargs):
    return audio

def _compress_dead_air_middle(audio, _silence_cfg):
    return audio, []

def _apply_censor_beep(audio, *_args, **_kwargs):
    return audio, []

def _replace_keywords_with_sfx(audio, *_args, **_kwargs):
    return audio

# Unused in our flow but required symbol for import path compatibility
def _remove_fillers(audio, *args, **kwargs):
    return audio, []

setattr(features_stub, 'ensure_ffmpeg', _ensure_ffmpeg)
setattr(features_stub, 'apply_flubber_cuts', _apply_flubber_cuts)
setattr(features_stub, 'insert_intern_responses', _insert_intern_responses)
setattr(features_stub, 'compress_dead_air_middle', _compress_dead_air_middle)
setattr(features_stub, 'apply_censor_beep', _apply_censor_beep)
setattr(features_stub, 'replace_keywords_with_sfx', _replace_keywords_with_sfx)
setattr(features_stub, 'remove_fillers', _remove_fillers)
sys.modules['api.services.clean_engine.features'] = features_stub

# Now import real models/words/engine
models = importlib.import_module('api.services.clean_engine.models')
words_mod = importlib.import_module('api.services.clean_engine.words')
engine = importlib.import_module('api.services.clean_engine.engine')

Word = models.Word
UserSettings = models.UserSettings
SilenceSettings = models.SilenceSettings
InternSettings = models.InternSettings


class TestPipelineFillers(unittest.TestCase):
    def test_minimal_pipeline_shifts_world(self):
        # Prepare vendor transcript (seconds)
        vendor_words = [
            {"word": "Hello", "start": 0.00, "end": 0.10},
            {"word": "um",    "start": 0.10, "end": 0.20},
            {"word": "uh",    "start": 0.20, "end": 0.30},
            {"word": "world", "start": 0.30, "end": 0.50},
        ]
        with tempfile.TemporaryDirectory() as td:
            td_path = td
            audio_path = os.path.join(td_path, 'in.wav')
            from tests.helpers.audio import make_tiny_wav
            make_tiny_wav(audio_path, ms=800)
            vendor_path = os.path.join(td_path, 'vendor.json')
            with open(vendor_path, 'w', encoding='utf-8') as f:
                json.dump(vendor_words, f)
            work_dir = td_path

            settings = UserSettings()
            # ensure filler flags/words present
            setattr(settings, 'removeFillers', True)
            setattr(settings, 'fillerWords', ["um", "uh"])  # defaults merged with this
            silence_cfg = SilenceSettings()
            intern_cfg = InternSettings()

            out = engine.run_all(
                audio_path=audio_path,
                words_json_path=vendor_path,
                work_dir=work_dir,
                user_settings=settings,
                silence_cfg=silence_cfg,
                intern_cfg=intern_cfg,
                censor_cfg=None,
                sfx_map=None,
                synth=None,
                flubber_cuts_ms=None,
                output_name='test.mp3',
                disable_intern_insertion=True,
            )

            # Verify filler merged span and shifted world timing in output transcript
            edits = out['summary']['edits']
            spans = edits.get('filler_cuts') or []
            self.assertEqual(spans, [(100, 300)])

            tr_dir = os.path.join(work_dir, 'transcripts')
            out_json = os.path.join(tr_dir, 'test.json')
            with open(out_json, 'r', encoding='utf-8') as f:
                working = json.load(f)
            # find world
            world = next(w for w in working if w.get('word') == 'world')
            # shifted by 200ms earlier: start 0.30->0.10, end 0.50->0.30
            self.assertAlmostEqual(world['start'], 0.10, places=3)
            self.assertAlmostEqual(world['end'], 0.30, places=3)


if __name__ == '__main__':
    unittest.main()
