#!/usr/bin/env python3
"""
Fix episodes: Populate gcs_audio_path from existing GCS files.

This script finds audio files in GCS and updates the database so the RSS feed works.
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.resolve()
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from google.cloud import storage
from sqlmodel import Session, select
from api.core.database import engine
from api.models.podcast import Episode, Podcast

# Correct bucket name
GCS_BUCKET_NAME = "ppp-media-us-west1"


def fix_episode_gcs_paths(podcast_slug: str = "cinema-irl", dry_run: bool = True):
    """Find audio files in GCS and update database."""
    
    print("\n" + "="*80)
    print("Fix Episode GCS Paths")
    print("="*80)
    print(f"Podcast: {podcast_slug}")
    print(f"Bucket: gs://{GCS_BUCKET_NAME}/")
    print(f"Mode: {'DRY RUN (no changes)' if dry_run else 'LIVE (will update database)'}")
    print("="*80 + "\n")
    
    # Initialize GCS client
    storage_client = storage.Client()
    bucket = storage_client.bucket(GCS_BUCKET_NAME)
    
    with Session(engine) as session:
        # Get podcast
        podcast = session.exec(
            select(Podcast).where(Podcast.slug == podcast_slug)
        ).first()
        
        if not podcast:
            print(f"❌ Podcast '{podcast_slug}' not found!")
            return
        
        print(f"✓ Found podcast: {podcast.name}\n")
        
        # Get all episodes
        episodes = session.exec(
            select(Episode).where(Episode.podcast_id == podcast.id)
        ).all()
        
        if not episodes:
            print("❌ No episodes found!")
            return
        
        print(f"✓ Found {len(episodes)} episodes\n")
        print("="*80)
        print("Checking GCS for audio files...")
        print("="*80 + "\n")
        
        fixed_count = 0
        missing_count = 0
        already_set_count = 0
        
        for i, episode in enumerate(episodes, 1):
            # Check if already has gcs_audio_path
            if episode.gcs_audio_path:
                already_set_count += 1
                continue
            
            # Look for audio file in GCS under user_id/episodes/episode_id/
            episode_folder = f"{episode.user_id}/episodes/{episode.id}/"
            
            try:
                # List blobs in this episode's folder
                blobs = list(bucket.list_blobs(prefix=episode_folder, max_results=20))
                
                # Find audio file (mp3, m4a, wav)
                audio_blob = None
                for blob in blobs:
                    if any(blob.name.endswith(ext) for ext in ['.mp3', '.m4a', '.wav', '.aac']):
                        audio_blob = blob
                        break
                
                if audio_blob:
                    gcs_path = f"gs://{GCS_BUCKET_NAME}/{audio_blob.name}"
                    
                    if i <= 5:  # Show first 5
                        print(f"✓ Episode {i}: {episode.title[:50]}")
                        print(f"  Found: {audio_blob.name}")
                        print(f"  Size: {audio_blob.size / 1024 / 1024:.1f} MB")
                    
                    if not dry_run:
                        episode.gcs_audio_path = gcs_path
                        episode.audio_file_size = audio_blob.size
                        session.add(episode)
                    
                    fixed_count += 1
                else:
                    if i <= 5:
                        print(f"❌ Episode {i}: {episode.title[:50]}")
                        print(f"  No audio file found in gs://{GCS_BUCKET_NAME}/{episode_folder}")
                    missing_count += 1
            
            except Exception as e:
                print(f"❌ Error checking episode {episode.id}: {e}")
                missing_count += 1
        
        if not dry_run and fixed_count > 0:
            session.commit()
            print(f"\n✓ Database updated!")
        
        print("\n" + "="*80)
        print("Summary")
        print("="*80)
        print(f"Total episodes: {len(episodes)}")
        print(f"Already had gcs_audio_path: {already_set_count}")
        print(f"Found audio files: {fixed_count}")
        print(f"Missing audio files: {missing_count}")
        
        if dry_run and fixed_count > 0:
            print(f"\n💡 Run with --live to update the database")
        elif fixed_count > 0:
            print(f"\n✅ Successfully updated {fixed_count} episodes!")
            print(f"   Your RSS feed should now have audio URLs!")
        
        print("\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Fix episode GCS paths")
    parser.add_argument("--podcast", default="cinema-irl", help="Podcast slug")
    parser.add_argument("--live", action="store_true", help="Actually update database")
    
    args = parser.parse_args()
    
    fix_episode_gcs_paths(
        podcast_slug=args.podcast,
        dry_run=not args.live
    )
