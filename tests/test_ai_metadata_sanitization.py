import sys
from pathlib import Path

# Ensure backend is importable as 'api'
ROOT = Path(__file__).resolve().parents[1]
PKG_ROOT = ROOT / "backend"
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from api.routers.ai_metadata import AIMetadataRequest, generate_episode_metadata  # type: ignore
from api.models.user import User  # type: ignore
import asyncio


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_ai_metadata_removes_hashes_and_audio_boilerplate(monkeypatch):
    # Build a fake user for dependency
    user = User(id="00000000-0000-0000-0000-000000000000", email="test@example.com")  # type: ignore

    # filename with multiple hashes and audio boilerplate
    fname = "456779837bc544b099e40d696cf87e1b 5c3483534233349f7b27e9b16b5821ced stereo mix.wav"

    req = AIMetadataRequest(
        prompt=None,
        audio_filename=fname,
        current_title=None,
        current_description=None,
        max_tags=10,
    )

    # Call the function directly, bypassing FastAPI dependency injection
    res = run(generate_episode_metadata(req, current_user=user))

    # Title should not contain any of the hashes or the phrase 'stereo mix'
    assert "stereo" not in res.title.lower()
    assert "mix" not in res.title.lower()
    assert "456779837bc544b099e40d696cf87e1b" not in res.title.lower()
    assert "5c3483534233349f7b27e9b16b5821ced" not in res.title.lower()

    # Tags should not contain hex-like ids
    for tag in res.tags:
        assert not any(len(tok) >= 16 and all(c in "0123456789abcdef" for c in tok.lower()) for tok in tag.split()), tag

    assert res.source == "heuristic"
