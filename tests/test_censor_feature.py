import os
import sys
import types
import importlib
import unittest
from types import SimpleNamespace

# Ensure we use lightweight stubs for pydub so the module under test imports cleanly.
for mod in [
    'pydub',
    'pydub.generators',
    'api.services.clean_engine.feature_modules.censor',
]:
    sys.modules.pop(mod, None)


class _StubAudioSegment:
    def __init__(self, duration=0):
        self._duration = int(duration)

    def __len__(self):
        return self._duration

    def __getitem__(self, key):
        if not isinstance(key, slice):
            raise TypeError('slice access only')
        start = 0 if key.start is None else int(max(0, key.start))
        stop = self._duration if key.stop is None else int(min(self._duration, key.stop))
        if stop < start:
            stop = start
        return _StubAudioSegment(stop - start)

    def __add__(self, other):
        if isinstance(other, _StubAudioSegment):
            return _StubAudioSegment(self._duration + len(other))
        if isinstance(other, (int, float)):
            return self  # gain adjustments are no-ops for the stub
        return NotImplemented

    def fade_in(self, _):
        return self

    def fade_out(self, _):
        return self

    def apply_gain(self, _):
        return self

    @classmethod
    def silent(cls, duration=0):
        return cls(int(duration))

    @classmethod
    def from_file(cls, *_args, **_kwargs):
        return cls(100)


class _StubSine:
    def __init__(self, freq):
        self.freq = freq

    def to_audio_segment(self, duration=0):
        return _StubAudioSegment(duration)


pydub_stub = types.ModuleType('pydub')
setattr(pydub_stub, 'AudioSegment', _StubAudioSegment)
sys.modules['pydub'] = pydub_stub

generators_stub = types.ModuleType('pydub.generators')
setattr(generators_stub, 'Sine', _StubSine)
sys.modules['pydub.generators'] = generators_stub

ROOT = os.path.dirname(os.path.dirname(__file__))
PKG_ROOT = os.path.join(ROOT, 'backend')
if PKG_ROOT not in sys.path:
    sys.path.insert(0, PKG_ROOT)

censor = importlib.import_module('api.services.clean_engine.feature_modules.censor')
_apply_censor_beep = censor.apply_censor_beep
_normalize_token = censor._normalize_token
_matches_token = censor._matches_token


class TestCensorNormalization(unittest.TestCase):
    def test_trailing_exclamation_normalizes(self):
        self.assertEqual(_normalize_token('shit!'), 'shit')
        self.assertTrue(
            _matches_token(_normalize_token('shit!'), _normalize_token('shit'), fuzzy=False, threshold=0.85)
        )

    def test_apply_censor_handles_trailing_exclamation_without_fuzzy(self):
        audio = _StubAudioSegment.silent(duration=1000)
        words = [
            {'word': 'hello', 'start': 0, 'end': 100},
            {'word': 'shit!', 'start': 100, 'end': 300},
            {'word': 'world', 'start': 300, 'end': 600},
        ]
        cfg = SimpleNamespace(
            enabled=True,
            words=['shit'],
            fuzzy=False,
            match_threshold=0.85,
            beep_ms=200,
            beep_freq_hz=1000,
            beep_gain_db=0.0,
            beep_file=None,
            censorWords=['shit'],
            censorFuzzy=False,
            censorMatchThreshold=0.85,
            censorBeepMs=200,
            censorBeepFreq=1000,
            censorBeepGainDb=0.0,
            censorBeepFile=None,
        )

        _, spans = _apply_censor_beep(audio, words, cfg, mutate_words=False)
        self.assertEqual(spans, [(100, 300)])


if __name__ == '__main__':
    unittest.main()
