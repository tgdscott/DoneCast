"""Quick migration script for single episode - simpler version without unicode."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from api.core.database import get_session
from api.models.podcast import Episode
from uuid import UUID
from api.core.paths import FINAL_DIR, MEDIA_DIR
from infrastructure import gcs

episode_id = "768605b6-18ad-4a52-ab85-a05b8c1d321f"

print(f"Migrating episode {episode_id} to GCS...")

session = next(get_session())
ep = session.get(Episode, UUID(episode_id))

if not ep:
    print(f"ERROR: Episode not found: {episode_id}")
    sys.exit(1)

print(f"Episode: {ep.title}")
print(f"Status: {ep.status}")
print(f"final_audio_path: {ep.final_audio_path}")
print(f"gcs_audio_path: {ep.gcs_audio_path}")

# Find local file
basename = os.path.basename(ep.final_audio_path)
candidates = [FINAL_DIR / basename, MEDIA_DIR / basename]
local_file = next((c for c in candidates if c.exists()), None)

if not local_file:
    print(f"ERROR: Local audio file not found: {ep.final_audio_path}")
    print(f"Checked: {candidates}")
    sys.exit(1)

print(f"Found local file: {local_file} ({local_file.stat().st_size / 1024 / 1024:.2f} MB)")

# Upload to GCS
gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
gcs_key = f"{ep.user_id.hex}/audio/final/{local_file.name}"
gcs_path = f"gs://{gcs_bucket}/{gcs_key}"

print(f"Uploading to: {gcs_path}")

try:
    with open(local_file, "rb") as f:
        audio_data = f.read()
    
    gcs.upload_bytes(gcs_bucket, gcs_key, audio_data, content_type="audio/mpeg")
    print("Upload successful!")
    
    # Update database
    ep.gcs_audio_path = gcs_path
    session.add(ep)
    session.commit()
    print("Database updated!")
    print(f"\nSUCCESS: Episode {episode_id} migrated to GCS")
    print(f"GCS path: {gcs_path}")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
