import sys
from pathlib import Path
import unittest

# Ensure package import path
ROOT = Path(__file__).resolve().parents[1]
PKG_ROOT = ROOT / 'backend'
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from api.services.audio.filler_pipeline import (
    compute_filler_spans,
    apply_blank_spans,
    remove_fillers,
)


class TestFillerPipeline(unittest.TestCase):
    def test_compute_and_blank(self):
        words = [
            {'word': 'Uh,'},
            {'word': 'I'},
            {'word': 'mean—'},
            {'word': 'we'},
            {'word': 'should'},
        ]
        fillers = ["uh", "i mean"]
        spans = compute_filler_spans(words, fillers)
        self.assertEqual(spans, {0, 1, 2})
        log: list[str] = []
        blanked = apply_blank_spans(words, spans, log)
        self.assertEqual([w.get('word') for w in blanked], ["", "", "", "we", "should"])
        # ensure log prefix matches production
        self.assertTrue(any(s.startswith('[FILLERS_TRANSCRIPT_STATS]') for s in log))

    def test_remove_fillers_wrapper(self):
        words = [
            {'word': 'Uh,'},
            {'word': 'I'},
            {'word': 'mean—'},
            {'word': 'we'},
            {'word': 'should'},
        ]
        fillers = ["uh", "i mean"]
        log: list[str] = []
        cleaned, metrics = remove_fillers(words, fillers, log)
        self.assertEqual([w.get('word') for w in cleaned], ["", "", "", "we", "should"])
        self.assertIsInstance(metrics, dict)
        self.assertTrue(any('FILLERS_TRANSCRIPT_STATS' in s for s in log))


if __name__ == '__main__':
    unittest.main()
