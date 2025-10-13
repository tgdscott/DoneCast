"""
Fix scheduled Cinema IRL episodes 195-201 audio paths

This script:
1. Finds episodes 195-201 for Cinema IRL podcast
2. Checks if they have audio files in GCS
3. Populates gcs_audio_path if found
4. Reports what needs to be done

Run this on your production environment where database and GCS are accessible.
"""
import os
import sys
from pathlib import Path

# Try to import from current directory structure
try:
    from backend.api.models.podcast import Episode, Podcast
except ImportError:
    # If that fails, try adding to path
    sys.path.insert(0, str(Path(__file__).parent / "backend"))
    from api.models.podcast import Episode, Podcast

from sqlmodel import Session, create_engine, select

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL environment variable not set!")
    sys.exit(1)

engine = create_engine(DATABASE_URL, echo=False)

print("=" * 70)
print("CINEMA IRL SCHEDULED EPISODES - AUDIO PATH FIX")
print("=" * 70)

with Session(engine) as session:
    # Find Cinema IRL podcast
    podcast = session.exec(
        select(Podcast).where(Podcast.slug == "cinema-irl")
    ).first()
    
    if not podcast:
        print("\n❌ Cinema IRL podcast not found!")
        print("   Check if slug is different. Available podcasts:")
        podcasts = session.exec(select(Podcast)).all()
        for p in podcasts:
            print(f"   - {p.name} (slug: {p.slug})")
        sys.exit(1)
    
    print(f"\n✅ Found podcast: {podcast.name}")
    print(f"   ID: {podcast.id}")
    print(f"   Slug: {podcast.slug}")
    
    # Get episodes 195-201
    episodes = list(session.exec(
        select(Episode).where(
            Episode.podcast_id == podcast.id,
            Episode.episode_number >= 195,
            Episode.episode_number <= 201
        ).order_by(Episode.episode_number)
    ).all())
    
    if not episodes:
        print("\n❌ No episodes 195-201 found!")
        sys.exit(1)
    
    print(f"\n📊 Found {len(episodes)} episodes to check:")
    print()
    
    needs_fix = []
    
    for ep in episodes:
        print(f"Episode {ep.episode_number}: {ep.title}")
        print(f"   ID: {ep.id}")
        print(f"   Status: {ep.status}")
        print(f"   Publish: {ep.publish_at}")
        
        has_audio = False
        audio_location = None
        
        if ep.gcs_audio_path:
            print(f"   ✅ gcs_audio_path: {ep.gcs_audio_path}")
            has_audio = True
            audio_location = "GCS"
        else:
            print(f"   ❌ gcs_audio_path: None")
        
        if ep.final_audio_path:
            print(f"   ℹ️  final_audio_path: {ep.final_audio_path}")
            if not has_audio:
                has_audio = True
                audio_location = "Local"
        else:
            print(f"   ❌ final_audio_path: None")
        
        if ep.spreaker_episode_id:
            print(f"   ℹ️  spreaker_episode_id: {ep.spreaker_episode_id}")
            if not has_audio:
                has_audio = True
                audio_location = "Spreaker"
        
        if not has_audio:
            print(f"   🚨 NO AUDIO PATH FOUND!")
            needs_fix.append(ep)
        else:
            print(f"   ✓ Audio available via: {audio_location}")
        
        print()
    
    if needs_fix:
        print("\n" + "=" * 70)
        print(f"🚨 {len(needs_fix)} episodes NEED AUDIO PATHS:")
        print("=" * 70)
        for ep in needs_fix:
            print(f"   - Episode {ep.episode_number}: {ep.title}")
        
        print("\n💡 NEXT STEPS:")
        print("   1. Check if these episodes were assembled (have audio files)")
        print("   2. If files exist in GCS, run GCS migration for these specific episodes")
        print("   3. If files don't exist, you may need to:")
        print("      a) Reassemble them")
        print("      b) Or recover them from Spreaker if they were published there")
        print()
        print("   To check GCS manually:")
        print("   gsutil ls -lh gs://podcastpro-media/episodes/ | grep -E '(195|196|197|198|199|200|201)'")
    else:
        print("=" * 70)
        print("✅ ALL EPISODES HAVE AUDIO PATHS!")
        print("=" * 70)
        print("\nIf playback still doesn't work, the issue might be:")
        print("  - GCS signed URL generation failing")
        print("  - CORS issues")
        print("  - Files don't actually exist at the paths specified")

print("\nDone!")
