# api/core/paths.py
import os
from pathlib import Path

# The root of the project is one level up from the 'api' directory
# e.g., d:\PodWebDeploy\podcast-pro-plus\
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
APP_ROOT = PROJECT_ROOT # Alias for clarity
 
IS_DEV_ENV = os.getenv("APP_ENV") == "dev"
 
# Define a base for temporary/generated files for local dev
if IS_DEV_ENV:
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
CLEANED_DIR = Path(os.getenv("CLEANED_DIR", str(LOCAL_TMP_DIR / "cleaned_audio")))
TRANSCRIPTS_DIR = Path(os.getenv("TRANSCRIPTS_DIR", str(LOCAL_TMP_DIR / "transcripts")))
WS_ROOT = Path(os.getenv("WS_ROOT", str(LOCAL_TMP_DIR / "ws_root")))
AI_SEGMENTS_DIR = Path(os.getenv("AI_SEGMENTS_DIR", str(LOCAL_TMP_DIR / "ai_segments")))


# Ensure all directories exist so the app doesn't crash on first use
for d in (MEDIA_DIR, FINAL_DIR, FLUBBER_CTX_DIR, CLEANED_DIR, TRANSCRIPTS_DIR, WS_ROOT, AI_SEGMENTS_DIR):
    d.mkdir(parents=True, exist_ok=True)