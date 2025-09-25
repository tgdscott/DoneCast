import sys
from pathlib import Path
import unittest

# Ensure package import path
ROOT = Path(__file__).resolve().parents[1]
PKG_ROOT = ROOT / 'backend'
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from api.services.audio.silence_pipeline import detect_pauses, guard_and_pad, retime_words


class TestSilencePipeline(unittest.TestCase):
    def test_detect_and_pad_and_retime(self):
        # A[0-0.1], B[2.2-2.3] => gap 2.1s; with threshold 1.5s we detect (0.1, 2.2)
        words = [
            {"word": "A", "start": 0.0, "end": 0.1},
            {"word": "B", "start": 2.2, "end": 2.3},
        ]
        cfg = {
            'maxPauseSeconds': 1.5,
            'pausePadPreMs': 100.0,   # 0.1s
            'pausePadPostMs': 200.0,  # 0.2s
        }
        log: list[str] = []

        spans = detect_pauses(words, cfg, log)
        self.assertEqual(spans, [(0.1, 2.2)])

        padded = guard_and_pad(spans, cfg, log)
        # start padded back to 0.0, end padded to 2.4 (allow float precision)
        self.assertEqual(len(padded), 1)
        self.assertAlmostEqual(padded[0][0], 0.0, places=6)
        self.assertAlmostEqual(padded[0][1], 2.4, places=6)

        # retime_words currently preserves timings (no-op for parity)
        retimed = retime_words(words, padded, cfg, log)
        self.assertIsNot(retimed, words)
        self.assertEqual([(w['start'], w['end']) for w in retimed], [(0.0, 0.1), (2.2, 2.3)])


if __name__ == '__main__':
    unittest.main()
