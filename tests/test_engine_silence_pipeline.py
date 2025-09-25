# pyright: reportGeneralTypeIssues=false
import os, sys, json, types, importlib
import tempfile
import unittest

# --- Stub pydub.AudioSegment with minimal behavior used by engine ---
class _StubAudioSegment:
    def __init__(self, duration=0):
        self._duration = int(duration)
    def __len__(self):
        return self._duration
    def __getitem__(self, s):
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
        return cls(6000)
    def export(self, *_args, **_kwargs):
        return b""

pydub_stub = types.ModuleType('pydub')
setattr(pydub_stub, 'AudioSegment', _StubAudioSegment)
sys.modules['pydub'] = pydub_stub

ROOT = os.path.dirname(os.path.dirname(__file__))
PKG_ROOT = os.path.join(ROOT, 'backend')
if PKG_ROOT not in sys.path:
    sys.path.insert(0, PKG_ROOT)

api_pkg = types.ModuleType('api'); api_pkg.__path__ = [os.path.join(PKG_ROOT, 'api')]  # type: ignore[attr-defined]
services_pkg = types.ModuleType('api.services'); services_pkg.__path__ = [os.path.join(PKG_ROOT, 'api', 'services')]  # type: ignore[attr-defined]
clean_pkg = types.ModuleType('api.services.clean_engine'); clean_pkg.__path__ = [os.path.join(PKG_ROOT, 'api', 'services', 'clean_engine')]  # type: ignore[attr-defined]
sys.modules['api'] = api_pkg
sys.modules['api.services'] = services_pkg
sys.modules['api.services.clean_engine'] = clean_pkg

features_stub = types.ModuleType('api.services.clean_engine.features')

def _ensure_ffmpeg():
    return None

def _apply_flubber_cuts(audio, cuts):
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

def _apply_censor_beep(audio, *_args, **_kwargs):
    return audio, []

def _replace_keywords_with_sfx(audio, *_args, **_kwargs):
    return audio

def _remove_fillers(audio, *_args, **_kwargs):
    return audio, []

setattr(features_stub, 'ensure_ffmpeg', _ensure_ffmpeg)
setattr(features_stub, 'apply_flubber_cuts', _apply_flubber_cuts)
setattr(features_stub, 'insert_intern_responses', _insert_intern_responses)
setattr(features_stub, 'apply_censor_beep', _apply_censor_beep)
setattr(features_stub, 'replace_keywords_with_sfx', _replace_keywords_with_sfx)
setattr(features_stub, 'remove_fillers', _remove_fillers)
sys.modules['api.services.clean_engine.features'] = features_stub

models = importlib.import_module('api.services.clean_engine.models')
engine = importlib.import_module('api.services.clean_engine.engine')

UserSettings = models.UserSettings
SilenceSettings = models.SilenceSettings
InternSettings = models.InternSettings


class TestSilencePipeline(unittest.TestCase):
    def test_trim_long_pause_and_shift(self):
        # A[0-100ms], B[2000-2100ms] => gap 1900ms
        vendor_words = [
            {"word": "A", "start": 0.000, "end": 0.100},
            {"word": "B", "start": 2.000, "end": 2.100},
        ]
        with tempfile.TemporaryDirectory() as td:
            audio_path = os.path.join(td, 'in.wav')
            from tests.helpers.audio import make_tiny_wav
            make_tiny_wav(audio_path, ms=800)
            vendor_path = os.path.join(td, 'vendor.json')
            with open(vendor_path, 'w', encoding='utf-8') as f:
                json.dump(vendor_words, f)
            settings = UserSettings()
            setattr(settings, 'removeFillers', False)
            setattr(settings, 'removePauses', True)
            setattr(settings, 'maxPauseSeconds', 1.5)
            setattr(settings, 'targetPauseSeconds', 0.5)
            out = engine.run_all(
                audio_path=audio_path,
                words_json_path=vendor_path,
                work_dir=td,
                user_settings=settings,
                silence_cfg=SilenceSettings(),
                intern_cfg=InternSettings(),
                censor_cfg=None,
                sfx_map=None,
                synth=None,
                flubber_cuts_ms=None,
                output_name='siltest.mp3',
                disable_intern_insertion=True,
            )
            tr_dir = os.path.join(td, 'transcripts')
            out_json = os.path.join(tr_dir, 'siltest.json')
            with open(out_json, 'r', encoding='utf-8') as f:
                working = json.load(f)
            a = next(w for w in working if w['word'] == 'A')
            b = next(w for w in working if w['word'] == 'B')
            # B should shift earlier by ~1400ms: 2000->600ms start, 2100->700ms end
            self.assertAlmostEqual(b['start'], 0.600, places=3)
            self.assertAlmostEqual(b['end'], 0.700, places=3)
            # Final gap should be ~500ms between A.end (0.100) and B.start (0.600)
            self.assertAlmostEqual(b['start'] - a['end'], 0.500, places=3)


if __name__ == '__main__':
    unittest.main()
