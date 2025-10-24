"""Migrate episodes 199 and 200 to GCS."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from api.core.database import get_session
from api.models.podcast import Episode
from uuid import UUID
import json

episode_ids = [
    "1679183d-d2de-4b4b-ad25-be5e7eb6199f",  # E199
    "fa933980-ecf1-44e4-935a-5236db1ddccc",  # E200
]

print("Migrating episodes 199 and 200 to GCS...\n")

session = next(get_session())

for ep_id in episode_ids:
    ep = session.get(Episode, UUID(ep_id))
    if not ep:
        print(f"ERROR: Episode {ep_id} not found")
        continue
    
    print(f"\n{'='*60}")
    print(f"Episode: {ep.title}")
    print(f"ID: {ep.id}")
    print(f"Status: {ep.status}")
    print(f"Current gcs_audio_path: {ep.gcs_audio_path}")
    
    # Check metadata for GCS URI
    meta = json.loads(ep.meta_json or '{}')
    gcs_uri = meta.get('cleaned_audio_gcs_uri')
    
    if gcs_uri:
        print(f"Found GCS URI in metadata: {gcs_uri}")
        print(f"Setting gcs_audio_path...")
        ep.gcs_audio_path = gcs_uri
        session.add(ep)
        session.commit()
        print("SUCCESS: gcs_audio_path updated!")
    else:
        print("WARNING: No GCS URI found in metadata")
        print(f"Metadata keys: {list(meta.keys())}")

print(f"\n{'='*60}")
print("Migration complete!")
