"""Check scheduled episodes 195-201 for Cinema IRL"""
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from sqlmodel import Session, create_engine, select
from api.models.podcast import Episode, Podcast

# Use production database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/podcastpro")
engine = create_engine(DATABASE_URL, echo=False)

with Session(engine) as session:
    # Find Cinema IRL podcast
    podcast = session.exec(
        select(Podcast).where(Podcast.slug == "cinema-irl")
    ).first()
    
    if not podcast:
        print("Cinema IRL podcast not found!")
        sys.exit(1)
    
    print(f"Found podcast: {podcast.name} (ID: {podcast.id})\n")
    
    # Get episodes 195-201
    episodes = session.exec(
        select(Episode).where(
            Episode.podcast_id == podcast.id,
            Episode.episode_number >= 195,
            Episode.episode_number <= 201
        ).order_by(Episode.episode_number)
    ).all()
    
    print(f"Found {len(episodes)} episodes:\n")
    
    for ep in episodes:
        print(f"Episode {ep.episode_number}: {ep.title}")
        print(f"  ID: {ep.id}")
        print(f"  Status: {ep.status}")
        print(f"  Publish At: {ep.publish_at}")
        print(f"  spreaker_episode_id: {ep.spreaker_episode_id}")
        print(f"  final_audio_path: {ep.final_audio_path}")
        print(f"  gcs_audio_path: {ep.gcs_audio_path}")
        print(f"  gcs_cover_path: {ep.gcs_cover_path}")
        
        # Check if final audio file exists
        if ep.final_audio_path:
            from config import settings
            FINAL_DIR = settings.FINAL_DIR
            MEDIA_DIR = settings.MEDIA_DIR
            
            base = Path(ep.final_audio_path).name
            final_path = FINAL_DIR / base
            media_path = MEDIA_DIR / base
            
            if final_path.exists():
                print(f"  ✅ Audio file exists at: {final_path}")
            elif media_path.exists():
                print(f"  ✅ Audio file exists at: {media_path}")
            else:
                print(f"  ❌ Audio file NOT found!")
        else:
            print(f"  ⚠️  No final_audio_path set")
        
        print()
