from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from api.core.paths import TRANSCRIPTS_DIR
from api.routers.ai_suggestions import _discover_transcript_json_path


def test_discover_transcript_json_path_handles_sanitized_hint() -> None:
    """Upper/lower-case differences in hints should still resolve transcripts."""

    unique_prefix = uuid.uuid4().hex
    hint = f"gs://bucket/{unique_prefix}_Stereo_Mix.mp3"
    stem = f"{unique_prefix}_stereo_mix"
    transcript_path = TRANSCRIPTS_DIR / f"{stem}.json"
    transcript_path.write_text("[]", encoding="utf-8")

    try:
        resolved = _discover_transcript_json_path(MagicMock(), None, hint)
        assert resolved == transcript_path
    finally:
        try:
            transcript_path.unlink()
        except FileNotFoundError:
            pass
