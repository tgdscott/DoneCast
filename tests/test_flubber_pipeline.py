import tempfile
import unittest
from pathlib import Path
from tests.helpers.audio import make_tiny_wav


class TestFlubberPipeline(unittest.TestCase):
    def setUp(self):
        # Ensure app import root is on sys.path
        import sys
    root = Path(__file__).resolve().parents[1] / 'backend'
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))

    def _stub_audiosegment(self, target_module):
        class _AS:
            def __init__(self, d=0):
                self._d = int(d)
            def __len__(self):
                return self._d
            @classmethod
            def from_file(cls, *a, **k):
                return cls(2000)
            def export(self, out_f, format=None):
                try:
                    p = Path(out_f)
                    p.parent.mkdir(parents=True, exist_ok=True)
                    with open(p, 'wb') as fh:
                        fh.write(b'')
                except Exception:
                    pass
                return b''
        target_module.AudioSegment = _AS

    def test_normalize_merge_and_apply_and_retime(self):
        from api.services.audio import flubber_pipeline as fp

        # Replace AudioSegment in module with stub so no audio libs are needed
        self._stub_audiosegment(fp)

        # 1) normalize_and_merge_spans merges overlaps
        raw = [(5, 10), (8, 12), (0, 3)]
        merged = fp.normalize_and_merge_spans(raw, {}, [])
        self.assertEqual(merged, [(0, 3), (5, 12)])

        # 2) apply_flubber_audio writes output and returns metrics
        td = Path(tempfile.mkdtemp())
        try:
            in_p = td / 'in.wav'
            out_p = td / 'out.mp3'
            make_tiny_wav(in_p, ms=200)  # create a real tiny WAV for robustness
            metrics = fp.apply_flubber_audio(in_p, out_p, merged, {}, [])
            self.assertTrue(out_p.exists(), 'output audio not written')
            self.assertIn('spans_applied', metrics)
            self.assertIn('removed_ms', metrics)
            self.assertIn('final_ms', metrics)
            self.assertEqual(metrics['spans_applied'], 0)  # parity: no audio flubber in current behavior
            self.assertEqual(metrics['removed_ms'], 0)
            self.assertEqual(metrics['final_ms'], 2000)
        finally:
            # Clean up temp dir
            for p in td.glob('*'):
                try:
                    p.unlink()
                except Exception:
                    pass
            try:
                td.rmdir()
            except Exception:
                pass

        # 3) retime_words_after_flubber is a no-op in current behavior
        words = [
            {"word": "a", "start": 0.0, "end": 0.1},
            {"word": "b", "start": 0.1, "end": 0.2},
        ]
        out_words = fp.retime_words_after_flubber(words, merged, {}, [])
        self.assertEqual(out_words, words)


if __name__ == '__main__':
    unittest.main()
