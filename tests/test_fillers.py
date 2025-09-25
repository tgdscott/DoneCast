# pyright: reportGeneralTypeIssues=false
import sys, os, types, importlib
import unittest

# Minimal pydub stub so imports (from models) don't fail
pydub_stub = types.ModuleType('pydub')
setattr(pydub_stub, 'AudioSegment', type('AudioSegment', (), {}))  # type: ignore[attr-defined]
sys.modules['pydub'] = pydub_stub

# Make 'api' package importable by adding backend to sys.path
ROOT = os.path.dirname(os.path.dirname(__file__))
PKG_ROOT = os.path.join(ROOT, 'backend')
if PKG_ROOT not in sys.path:
    sys.path.insert(0, PKG_ROOT)

# Create namespace-like packages to bypass on-disk __init__.py side effects
api_pkg = types.ModuleType('api'); api_pkg.__path__ = [os.path.join(PKG_ROOT, 'api')]  # type: ignore[attr-defined]
services_pkg = types.ModuleType('api.services'); services_pkg.__path__ = [os.path.join(PKG_ROOT, 'api', 'services')]  # type: ignore[attr-defined]
clean_pkg = types.ModuleType('api.services.clean_engine'); clean_pkg.__path__ = [os.path.join(PKG_ROOT, 'api', 'services', 'clean_engine')]  # type: ignore[attr-defined]
sys.modules['api'] = api_pkg
sys.modules['api.services'] = services_pkg
sys.modules['api.services.clean_engine'] = clean_pkg

# Import the real modules from files using standard import machinery
importlib.import_module('api.services.clean_engine.models')
clean_words = importlib.import_module('api.services.clean_engine.words')
build_filler_cuts = getattr(clean_words, 'build_filler_cuts')

class Word:
    def __init__(self, word: str, start: float, end: float) -> None:
        self.word = word
        self.start = start
        self.end = end


class TestBuildFillerCuts(unittest.TestCase):
    def test_adjacent_fillers_merge_and_ms_units(self):
        # two adjacent fillers: [100,200] and [200,300] -> merged [100,300]
        words = [
            Word(word='um', start=0.10, end=0.20),
            Word(word='uh', start=0.20, end=0.30),
            Word(word='hello', start=0.35, end=0.60),
            Word(word='like', start=1.00, end=1.10),
        ]
        spans = build_filler_cuts(words, {'um', 'uh', 'like'})
        self.assertEqual(spans, [(100, 300), (1000, 1100)])
        # ensure values are integers (ms)
        for s, e in spans:
            self.assertIsInstance(s, int)
            self.assertIsInstance(e, int)


if __name__ == '__main__':
    unittest.main()
