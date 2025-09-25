import os
import sys
import json
import shutil
import tempfile
import types
import unittest
from pathlib import Path


# Ensure import path for app package
ROOT = Path(__file__).resolve().parents[1]
PKG_ROOT = ROOT / 'backend'
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


# Robust pydub stub to exercise processor without real audio
class _AS:
    def __init__(self, d=0):
        self._d = int(d)
    def __len__(self):
        return self._d
    def __getitem__(self, s):
        if isinstance(s, slice):
            start = 0 if s.start is None else int(max(0, s.start))
            stop = self._d if s.stop is None else int(min(self._d, s.stop))
            if stop < start:
                stop = start
            return _AS(stop - start)
        raise TypeError('slice only')
    @classmethod
    def silent(cls, duration=0):
        return cls(int(duration))
    @classmethod
    def empty(cls):
        return cls(0)
    @classmethod
    def from_file(cls, *a, **k):
        return cls(2000)
    def export(self, *a, **k):
        return b''
    def apply_gain(self, *a, **k):
        return self
    def fade_in(self, *a, **k):
        return self
    def fade_out(self, *a, **k):
        return self
    def overlay(self, other, position=0):
        end = max(self._d, int(position) + len(other))
        return _AS(end)
    def __add__(self, other):
        return _AS(self._d + len(other))
    def __iadd__(self, other):
        self._d += len(other)
        return self

pydub_mod = types.ModuleType('pydub')
setattr(pydub_mod, 'AudioSegment', _AS)
sys.modules['pydub'] = pydub_mod
# Provide pydub.silence stub used by cleanup module
pydub_silence = types.ModuleType('pydub.silence')
def _detect_silence(*args, **kwargs):
    return []
setattr(pydub_silence, 'detect_silence', _detect_silence)
sys.modules['pydub.silence'] = pydub_silence


from tests.helpers.audio import make_tiny_wav


def _ensure_media_uploads_sample():
    try:
        # Prefer the actual constant if exported
        try:
            from api.core.config import MEDIA_UPLOADS_DIR
            media_dir = Path(MEDIA_UPLOADS_DIR)
        except Exception:
            # Fallback: default project location used by the app
            media_dir = Path.cwd() / "media_uploads"
        media_dir.mkdir(parents=True, exist_ok=True)
        make_tiny_wav(media_dir / "in.wav", ms=800)
        return media_dir / "in.wav"
    except Exception as e:
        raise RuntimeError(f"Failed to create media_uploads/in.wav: {e}")


class TestProcessorTranscriptIntegration(unittest.TestCase):

    def test_processor_writes_transcripts_and_logs(self):
        from types import SimpleNamespace
        from api.services.audio.processor import process_and_assemble_episode, TRANSCRIPTS_DIR

        words = [
            {'word': 'Hello,', 'start': 0.0, 'end': 0.1, 'speaker': 'A'},
            {'word': 'World!', 'start': 0.11, 'end': 0.2, 'speaker': 'A'},
        ]

        tmp = Path(tempfile.mkdtemp())
        try:
            wjson = tmp / 'w.json'
            wjson.write_text(json.dumps(words), encoding='utf-8')
            logfile = tmp / 'log.txt'
            prev = os.environ.get('TRANSCRIPTS_DEBUG')
            os.environ['TRANSCRIPTS_DEBUG'] = '1'
            try:
                tpl = SimpleNamespace(segments_json='[]', background_music_rules_json='[]', timing_json='{}')
                # Ensure the main input exists under media_uploads as expected by the app
                _ensure_media_uploads_sample()
                _fp, log, _notes = process_and_assemble_episode(
                    tpl,
                    'in.wav',
                    'verify-ep',
                    {},
                    {},
                    mix_only=True,
                    words_json_path=str(wjson),
                    log_path=str(logfile),
                )
            finally:
                if prev is None:
                    os.environ.pop('TRANSCRIPTS_DEBUG', None)
                else:
                    os.environ['TRANSCRIPTS_DEBUG'] = prev

            wj = TRANSCRIPTS_DIR / 'verify-ep.json'
            nj = TRANSCRIPTS_DIR / 'verify-ep.nopunct.json'
            # Optional: quick debug listing if files are missing
            if not (wj.exists() and (TRANSCRIPTS_DIR / 'verify-ep.nopunct.json').exists()):
                print("TRANSCRIPTS_DIR contents:", sorted(p.name for p in TRANSCRIPTS_DIR.glob("*")))
            self.assertTrue(wj.exists(), 'working transcript json missing')
            self.assertTrue(nj.exists(), 'nopunct sidecar json missing')
            self.assertTrue(any('wrote working transcript JSON' in s for s in log))
            self.assertTrue(any('wrote punctuation-sanitized JSON' in s for s in log))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
