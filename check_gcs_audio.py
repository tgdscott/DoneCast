import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from api.core.database import get_session
from sqlmodel import select
from api.models.podcast import Episode

session = next(get_session())

# Check the test episode that was failing
episodes = session.exec(
    select(Episode)
    .where(Episode.title.like("%long walk%"))  # type: ignore
    .order_by(Episode.created_at.desc())  # type: ignore
).all()

print(f"\nFound {len(episodes)} episodes matching 'long walk':\n")

for ep in episodes:
    print(f"ID: {ep.id}")
    print(f"Title: {ep.title}")
    print(f"Status: {ep.status}")
    print(f"final_audio_path: {ep.final_audio_path}")
    print(f"gcs_audio_path: {ep.gcs_audio_path}")
    print(f"Created: {ep.created_at}")
    print("-" * 80)
