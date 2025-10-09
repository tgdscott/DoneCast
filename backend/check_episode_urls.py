#!/usr/bin/env python3
"""
Simple diagnostic script to check what URLs are in your RSS feed and database.
This will tell you if you need to migrate files from Spreaker.
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.resolve()
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlmodel import Session, select
from api.core.database import engine
from api.models.podcast import Episode, Podcast


def check_episode_urls(podcast_slug: str = "cinema-irl"):
    """Check what URLs are being used in episodes."""
    
    print("\n" + "="*80)
    print("Episode URL Diagnostic")
    print("="*80)
    print(f"Podcast: {podcast_slug}")
    print("="*80 + "\n")
    
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
        print("Checking first 5 episodes for URLs:")
        print("="*80 + "\n")
        
        # Stats
        has_gcs_audio = 0
        has_final_audio = 0
        has_remote_cover = 0
        has_gcs_cover = 0
        has_cover_path = 0
        spreaker_audio_count = 0
        spreaker_cover_count = 0
        
        # Check first 5 episodes in detail
        for i, episode in enumerate(episodes[:5]):
            print(f"\n📝 Episode {i+1}: {episode.title}")
            print("-" * 80)
            
            # Audio
            if episode.gcs_audio_path:
                print(f"  🎵 GCS Audio: {episode.gcs_audio_path}")
                has_gcs_audio += 1
            elif episode.final_audio_path:
                print(f"  🎵 Final Audio Path: {episode.final_audio_path}")
                has_final_audio += 1
                if "spreaker" in str(episode.final_audio_path).lower():
                    print("    ⚠️  This looks like a Spreaker URL!")
                    spreaker_audio_count += 1
            else:
                print("  🎵 Audio: None")
            
            # Cover Image
            if episode.remote_cover_url:
                print(f"  🖼️  Remote Cover: {episode.remote_cover_url[:80]}...")
                has_remote_cover += 1
                if "spreaker" in str(episode.remote_cover_url).lower():
                    print("    ⚠️  This is a Spreaker URL!")
                    spreaker_cover_count += 1
            elif episode.gcs_cover_path:
                print(f"  🖼️  GCS Cover: {episode.gcs_cover_path}")
                has_gcs_cover += 1
            elif episode.cover_path:
                print(f"  🖼️  Cover Path: {episode.cover_path[:80]}...")
                has_cover_path += 1
                if "spreaker" in str(episode.cover_path).lower():
                    print("    ⚠️  This is a Spreaker URL!")
                    spreaker_cover_count += 1
            else:
                print("  🖼️  Cover: None")
        
        # Count all episodes
        print("\n\n" + "="*80)
        print(f"Summary (all {len(episodes)} episodes):")
        print("="*80)
        
        for episode in episodes:
            if episode.gcs_audio_path:
                has_gcs_audio += 1
            elif episode.final_audio_path:
                has_final_audio += 1
                if "spreaker" in str(episode.final_audio_path).lower():
                    spreaker_audio_count += 1
            
            if episode.remote_cover_url:
                has_remote_cover += 1
                if "spreaker" in str(episode.remote_cover_url).lower():
                    spreaker_cover_count += 1
            elif episode.gcs_cover_path:
                has_gcs_cover += 1
            elif episode.cover_path:
                has_cover_path += 1
                if "spreaker" in str(episode.cover_path).lower():
                    spreaker_cover_count += 1
        
        print(f"\n📊 Audio Files:")
        print(f"  • Episodes with GCS audio: {has_gcs_audio}")
        print(f"  • Episodes with final_audio_path: {has_final_audio}")
        print(f"  • Episodes using Spreaker audio URLs: {spreaker_audio_count}")
        
        print(f"\n📊 Cover Images:")
        print(f"  • Episodes with remote_cover_url: {has_remote_cover}")
        print(f"  • Episodes with GCS covers: {has_gcs_cover}")
        print(f"  • Episodes with cover_path: {has_cover_path}")
        print(f"  • Episodes using Spreaker cover URLs: {spreaker_cover_count}")
        
        print("\n" + "="*80)
        print("🔍 What does this mean?")
        print("="*80)
        
        if spreaker_audio_count > 0 or spreaker_cover_count > 0:
            print("\n⚠️  WARNING: You have Spreaker URLs in your database!")
            print(f"   • {spreaker_audio_count} episodes have Spreaker audio URLs")
            print(f"   • {spreaker_cover_count} episodes have Spreaker cover URLs")
            print("\n❗ You NEED to migrate these files before canceling Spreaker!")
            print("   Otherwise your RSS feed will break when Spreaker deletes them.")
        elif has_gcs_audio == len(episodes):
            print("\n✅ GOOD NEWS: All audio files are already in GCS!")
            print("   You don't need to migrate audio files.")
        else:
            print("\n⚠️  MIXED: Some episodes have GCS paths, others don't.")
            print("   You should check the RSS feed to see what it's actually serving.")
        
        print("\n💡 Next Step:")
        print("   Check your RSS feed to see what URLs it's actually using:")
        print(f"   https://app.podcastplusplus.com/api/rss/{podcast_slug}/feed.xml")
        print("\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Check episode URLs")
    parser.add_argument("--podcast", default="cinema-irl", help="Podcast slug")
    
    args = parser.parse_args()
    
    check_episode_urls(args.podcast)
