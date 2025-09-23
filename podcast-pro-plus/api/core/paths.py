# api/core/paths.py
import os
from pathlib import Path

# The root of the project is one level up from the 'api' directory
# e.g., d:\PodWebDeploy\podcast-pro-plus\
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()

# Define the local media directory.
# It reads from the .env file (e.g., MEDIA_ROOT in .env.local).
# If not set, it defaults to a 'local_media' folder in the project root.
# This is much more robust for cross-platform (Windows/Linux) development.
_media_root_str = os.getenv("MEDIA_ROOT")
if _media_root_str:
    MEDIA_DIR = Path(_media_root_str).resolve()
else:
    MEDIA_DIR = PROJECT_ROOT / "local_media"

# Ensure the directory exists so the app doesn't crash on first upload
MEDIA_DIR.mkdir(parents=True, exist_ok=True)