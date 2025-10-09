"""
Script to match GCS audio files in imported/ folder to episodes in the database.
This script will:
1. List all audio files in GCS imported/ folder
2. Query all episodes from the database
3. Try to match files to episodes based on various identifiers
4. Update gcs_audio_path for matched episodes
"""
import os
import sys
from pathlib import Path
import subprocess
import json
from typing import Optional
import argparse

# Add backend directory to path
backend_dir = Path(__file__).parent.resolve()
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlmodel import Session, select
from api.core.database import engine
from api.models.podcast import Episode, Podcast

def get_gcs_audio_files(user_id: str, bucket: str = "ppp-media-us-west1") -> list[str]:
    """Get list of all audio files in the imported/ folder."""
    print(f"\nListing audio files in gs://{bucket}/{user_id}/imported/...")
    result = subprocess.run(
        f'gcloud storage ls "gs://{bucket}/{user_id}/imported/*.mp3"',
        capture_output=True,
        text=True,
        shell=True
    )
    
    if result.returncode != 0:
        print(f"Error listing GCS files: {result.stderr}")
        return []
    
    files = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
    print(f"Found {len(files)} audio files in GCS")
    return files

def get_file_metadata(gcs_path: str) -> dict:
    """Get metadata for a GCS file including size."""
    result = subprocess.run(
        f'gcloud storage ls -L "{gcs_path}"',
        capture_output=True,
        text=True,
        shell=True
    )
    
    metadata = {}
    for line in result.stdout.split('\n'):
        line = line.strip()
        if ':' in line:
            key, value = line.split(':', 1)
            metadata[key.strip()] = value.strip()
    
    return metadata

def main():
    parser = argparse.ArgumentParser(description='Match GCS audio files to episodes')
    parser.add_argument('--podcast', required=True, help='Podcast slug')
    parser.add_argument('--user-id', required=True, help='GCS user_id folder (e.g., b6d5f77e-699e-444b-a31a-e1b4cb15feb4)')
    parser.add_argument('--bucket', default='ppp-media-us-west1', help='GCS bucket name')
    parser.add_argument('--live', action='store_true', help='Actually update the database (default is dry run)')
    
    args = parser.parse_args()
    
    # Get all audio files from GCS
    gcs_files = get_gcs_audio_files(args.user_id, args.bucket)
    
    if not gcs_files:
        print("No audio files found in GCS!")
        return
    
    # Get all episodes from database
    with Session(engine) as session:
        # First get the podcast
        podcast = session.exec(
            select(Podcast).where(Podcast.slug == args.podcast)
        ).first()
        
        if not podcast:
            print(f"Podcast '{args.podcast}' not found!")
            return
        
        print(f"\nFound podcast: {podcast.name} (ID: {podcast.id})")
        podcast_id = podcast.id
        
        # Get all episodes for this podcast
        episodes = list(session.exec(
            select(Episode).where(Episode.podcast_id == podcast_id)
        ).all())
    
    print(f"Found {len(episodes)} episodes in database")
    
    # Display sample of what we have
    print("\n=== Sample GCS Files (first 5) ===")
    for i, file_path in enumerate(gcs_files[:5]):
        filename = file_path.split('/')[-1]
        print(f"{i+1}. {filename}")
    
    print("\n=== Sample Episodes (first 5) ===")
    for i, ep in enumerate(list(episodes)[:5]):
        print(f"{i+1}. Episode {ep.episode_number}: {ep.title}")
        print(f"   ID: {ep.id}")
        print(f"   final_audio_path: {ep.final_audio_path}")
        print(f"   spreaker_episode_id: {ep.spreaker_episode_id}")
        print(f"   gcs_audio_path: {ep.gcs_audio_path}")
    
    # Try to match files to episodes
    print("\n=== Attempting to Match ===")
    
    # Extract unique identifiers from filenames
    # Filenames look like: {hash}_{uuid_with_underscores}.mp3
    # Let's see if we can match by episode ID
    
    matched = 0
    unmatched_files = []
    unmatched_episodes = []
    
    for file_path in gcs_files:
        filename = file_path.split('/')[-1]
        # Try to extract UUID from filename (format: hash_uuid-with-underscores.mp3)
        # The UUID part appears to have underscores instead of hyphens
        parts = filename.replace('.mp3', '').split('_')
        
        if len(parts) >= 5:  # UUID has 5 parts when split by underscore
            # Try to reconstruct UUID
            potential_uuid = '_'.join(parts[1:])  # Skip the hash prefix
            
            # Search for episode with this ID (need to convert underscores to hyphens)
            uuid_with_hyphens = '-'.join([
                parts[1],
                parts[2],
                parts[3],
                parts[4],
                parts[5] if len(parts) > 5 else parts[4]
            ])
            
            # Try to find matching episode
            matched_ep = None
            for ep in episodes:
                if str(ep.id).replace('-', '_') == potential_uuid or str(ep.id) == uuid_with_hyphens:
                    matched_ep = ep
                    break
            
            if matched_ep:
                matched += 1
                print(f"✓ Matched: {filename}")
                print(f"  → Episode {matched_ep.episode_number}: {matched_ep.title}")
                print(f"  → GCS path: {file_path}")
            else:
                unmatched_files.append(filename)
        else:
            unmatched_files.append(filename)
    
    # Find episodes with no match
    for ep in episodes:
        if not ep.gcs_audio_path:
            unmatched_episodes.append(ep)
    
    print(f"\n=== Summary ===")
    print(f"Total GCS files: {len(gcs_files)}")
    print(f"Total episodes: {len(episodes)}")
    print(f"Matched: {matched}")
    print(f"Unmatched files: {len(unmatched_files)}")
    print(f"Episodes without audio: {len(unmatched_episodes)}")
    
    if unmatched_files:
        print(f"\nUnmatched files (first 10):")
        for f in unmatched_files[:10]:
            print(f"  - {f}")
    
    if unmatched_episodes:
        print(f"\nEpisodes without audio (first 10):")
        for ep in unmatched_episodes[:10]:
            print(f"  - Episode {ep.episode_number}: {ep.title} (ID: {ep.id})")
    
    if args.live:
        print(f"\n✅ Would update database, but live mode not yet implemented.")
        print(f"💡 This was a dry run. Manual update needed.")
    else:
        print(f"\n💡 This was a dry run. Use --live to see what would be updated.")

if __name__ == "__main__":
    main()
