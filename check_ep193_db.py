"""Quick check of Episode 193 gcs_audio_path in database"""
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlmodel import Session, create_engine, select
from api.models.podcast import Episode

# Use Cloud SQL Proxy connection
engine = create_engine(
    "postgresql://podcast_admin:uw4l8hE7vq8@127.0.0.1:5433/podcast612_db",
    echo=False
)

with Session(engine) as session:
    # Get episode 193
    episode = session.exec(
        select(Episode).where(Episode.episode_number == 193)
    ).first()
    
    if episode:
        print(f"Episode 193: {episode.title}")
        print(f"  ID: {episode.id}")
        print(f"  gcs_audio_path: {episode.gcs_audio_path}")
        print(f"  audio_file_size: {episode.audio_file_size}")
        print(f"  duration_ms: {episode.duration_ms}")
        print(f"  status: {episode.status}")
    else:
        print("Episode 193 not found in database")
