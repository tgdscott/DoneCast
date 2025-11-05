import sys
from pathlib import Path

# Ensure backend package import path
ROOT = Path(__file__).resolve().parents[1]
PKG_ROOT = ROOT / "backend"
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from tests.helpers.audio import make_tiny_wav


def test_primary_cleanup_returns_real_audio_for_mix_only(tmp_path):
    from api.services.audio.orchestrator_steps_lib.cleanup import (
        primary_cleanup_and_rebuild,
    )

    audio_path = tmp_path / "sample.wav"
    make_tiny_wav(audio_path, ms=1200)

    words = [{"word": "hello", "start": 0.0, "end": 0.5}]
    log: list[str] = []

    cleaned_audio, new_words, filler_map, removed_count = primary_cleanup_and_rebuild(
        audio_path,
        words,
        cleanup_options={},
        mix_only=True,
        log=log,
    )

    # The mix_only path should load the real audio so we can insert intern clips later.
    assert len(cleaned_audio) >= 1200
    assert new_words is words  # words are passed through untouched
    assert filler_map == {}
    assert removed_count == 0
    assert any("mix_only=True" in entry for entry in log)
    assert any("Loaded original audio" in entry for entry in log)

