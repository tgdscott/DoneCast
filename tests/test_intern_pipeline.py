import sys
import types
import unittest

# Ensure app package import path
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PKG_ROOT = ROOT / 'backend'
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


class TestInternPipeline(unittest.TestCase):
    def test_sfx_markers_and_annotation(self):
        from api.services.audio.intern_pipeline import select_sfx_markers, annotate_words_with_sfx

        # Given: words containing a single-token trigger
        words = [
            {"word": "start", "start": 0.00, "end": 0.10, "speaker": "A"},
            {"word": "kaboom", "start": 0.12, "end": 0.22, "speaker": "A"},
            {"word": "after", "start": 0.25, "end": 0.35, "speaker": "A"},
        ]
        cfg = {
            "kaboom": {"action": "sfx", "file": "sfx_kaboom.mp3"}
        }
        log: list[str] = []

        markers = select_sfx_markers(words, cfg, log)
        # Should produce at least one marker at the trigger time
        self.assertTrue(markers, "no sfx markers detected")
        times = [round(float(m.get("time", 0.0)), 2) for m in markers]
        self.assertIn(0.12, times)
        # Annotation should add a visible placeholder at/after marker time
        words2 = annotate_words_with_sfx([dict(w) for w in words], markers, log=None)
        # Find first word at/after 0.12
        idx = next(i for i, w in enumerate(words2) if float(w.get("start", 0.0)) >= 0.12)
        self.assertIn("{", words2[idx]["word"])  # placeholder present
        # Other fields remain intact
        self.assertEqual(words2[0]["word"], "start")
        self.assertEqual(words2[-1]["word"], "after")


if __name__ == "__main__":
    unittest.main()
