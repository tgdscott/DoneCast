# api/core/paths.py
import os
from pathlib import Path

# The root of the project is one level up from the 'api' directory
# e.g., d:\PodWebDeploy\podcast-pro-plus\
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
APP_ROOT = PROJECT_ROOT  # Alias for clarity

_ENV_VALUE = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").strip().lower()
_PPP_ENV = (os.getenv("PPP_ENV") or "").strip().lower()
IS_TEST_ENV = bool(os.getenv("PYTEST_CURRENT_TEST")) or _ENV_VALUE in {"test", "testing"} or _PPP_ENV in {"test", "testing"}
IS_DEV_ENV = _ENV_VALUE in {"dev", "development", "local"} or IS_TEST_ENV

# Define a base for temporary/generated files for local dev/test; otherwise fall back to /tmp
if IS_DEV_ENV or IS_TEST_ENV:
    # For local dev, keep generated files inside the project for easy access/cleanup.
    LOCAL_TMP_DIR = PROJECT_ROOT / "local_tmp"
else:
    # In production (containers), /tmp is a standard, ephemeral location.
    LOCAL_TMP_DIR = Path("/tmp")
 
# Define the local media directory.
# It reads from the .env file (e.g., MEDIA_ROOT in .env.local).
# If not set, it defaults to a 'local_media' folder in the project root.
# This is much more robust for cross-platform (Windows/Linux) development.
_media_root_str = os.getenv("MEDIA_ROOT")
if _media_root_str:
    MEDIA_DIR = Path(_media_root_str).resolve()
else:
    MEDIA_DIR = PROJECT_ROOT / "local_media"

# Define other necessary directories, using environment variables with local defaults
FINAL_DIR = Path(os.getenv("FINAL_DIR", str(LOCAL_TMP_DIR / "final_episodes")))
FLUBBER_CTX_DIR = Path(os.getenv("FLUBBER_CONTEXTS_DIR", str(LOCAL_TMP_DIR / "flubber_contexts")))
INTERN_CTX_DIR = Path(os.getenv("INTERN_CONTEXTS_DIR", str(LOCAL_TMP_DIR / "intern_contexts")))
CLEANED_DIR = Path(os.getenv("CLEANED_DIR", str(LOCAL_TMP_DIR / "cleaned_audio")))
if os.getenv("TRANSCRIPTS_DIR"):
    TRANSCRIPTS_DIR = Path(os.getenv("TRANSCRIPTS_DIR", ""))
elif IS_TEST_ENV:
    TRANSCRIPTS_DIR = PROJECT_ROOT.parent / "transcripts"
else:
    TRANSCRIPTS_DIR = Path(LOCAL_TMP_DIR / "transcripts")
WS_ROOT = Path(os.getenv("WS_ROOT", str(LOCAL_TMP_DIR / "ws_root")))
AI_SEGMENTS_DIR = Path(os.getenv("AI_SEGMENTS_DIR", str(LOCAL_TMP_DIR / "ai_segments")))


# Ensure all directories exist so the app doesn't crash on first use
for d in (MEDIA_DIR, FINAL_DIR, FLUBBER_CTX_DIR, INTERN_CTX_DIR, CLEANED_DIR, TRANSCRIPTS_DIR, WS_ROOT, AI_SEGMENTS_DIR):
    d.mkdir(parents=True, exist_ok=True)
