#!/usr/bin/env python
"""
Migrate legacy episodes (with final_audio_path but no gcs_audio_path) to GCS.

This script handles episodes that were processed before the GCS-only architecture
was enforced (Oct 13, 2025). These episodes have local audio files that need to
be uploaded to GCS to be playable in the current system.

Usage:
    cd backend
    python ../migrate_legacy_episodes_to_gcs.py [--dry-run] [--episode-id UUID]

Options:
    --dry-run       Show what would be migrated without actually uploading
    --episode-id    Migrate specific episode by ID (otherwise migrates all legacy episodes)
"""

import os
import sys
from pathlib import Path
from uuid import UUID
from datetime import datetime, timezone

# Load environment from backend/.env.local
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent / "backend" / ".env.local"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✓ Loaded environment from {env_file}")
except ImportError:
    print("⚠ python-dotenv not installed, using existing environment")

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from api.core.database import get_session
from api.models.podcast import Episode
from api.core.paths import FINAL_DIR, MEDIA_DIR
from infrastructure import gcs
from sqlmodel import select


def find_local_audio_file(episode: Episode) -> Path | None:
    """Find local audio file for episode."""
    if not episode.final_audio_path:
        return None
    
    basename = os.path.basename(episode.final_audio_path)
    
    # Check candidate locations
    candidates = [
        FINAL_DIR / basename,
        MEDIA_DIR / basename,
        Path(episode.final_audio_path) if os.path.isabs(episode.final_audio_path) else None,
    ]
    
    for candidate in candidates:
        if candidate and candidate.exists() and candidate.is_file():
            return candidate
    
    return None


def migrate_episode_to_gcs(episode: Episode, dry_run: bool = False) -> bool:
    """Migrate single episode audio to GCS."""
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Migrating episode: {episode.title}")
    print(f"  ID: {episode.id}")
    print(f"  Status: {episode.status}")
    print(f"  Processed: {episode.processed_at}")
    print(f"  Published: {episode.publish_at}")
    
    # Find local audio file
    local_file = find_local_audio_file(episode)
    if not local_file:
        print(f"  ❌ ERROR: Local audio file not found: {episode.final_audio_path}")
        return False
    
    print(f"  ✓ Found local file: {local_file} ({local_file.stat().st_size / 1024 / 1024:.2f} MB)")
    
    if dry_run:
        print(f"  [DRY RUN] Would upload to GCS: gs://{{bucket}}/{episode.user_id.hex}/audio/final/{local_file.name}")
        return True
    
    # Upload to GCS
    try:
        gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
        gcs_key = f"{episode.user_id.hex}/audio/final/{local_file.name}"
        
        print(f"  📤 Uploading to GCS: gs://{gcs_bucket}/{gcs_key}")
        
        with open(local_file, "rb") as f:
            audio_data = f.read()
        
        gcs.upload_bytes(gcs_bucket, gcs_key, audio_data, content_type="audio/mpeg")
        
        gcs_path = f"gs://{gcs_bucket}/{gcs_key}"
        print(f"  ✅ Upload successful: {gcs_path}")
        
        # Update episode record
        episode.gcs_audio_path = gcs_path
        session = next(get_session())
        session.add(episode)
        session.commit()
        
        print(f"  ✅ Database updated with gcs_audio_path")
        return True
        
    except Exception as e:
        print(f"  ❌ ERROR: Failed to upload to GCS: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Migrate legacy episodes to GCS")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without uploading")
    parser.add_argument("--episode-id", type=str, help="Migrate specific episode by ID")
    args = parser.parse_args()
    
    print("=" * 80)
    print("Legacy Episode GCS Migration")
    print("=" * 80)
    
    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
    
    session = next(get_session())
    
    # Find episodes to migrate
    if args.episode_id:
        try:
            episode_uuid = UUID(args.episode_id)
            episode = session.get(Episode, episode_uuid)
            if not episode:
                print(f"❌ Episode not found: {args.episode_id}")
                return 1
            episodes = [episode]
        except ValueError:
            print(f"❌ Invalid UUID: {args.episode_id}")
            return 1
    else:
        # Find all episodes with final_audio_path but no gcs_audio_path
        episodes = session.exec(
            select(Episode)
            .where(Episode.final_audio_path.isnot(None))
            .where(Episode.gcs_audio_path.is_(None))
            .order_by(Episode.processed_at)
        ).all()
    
    if not episodes:
        print("\n✅ No legacy episodes found - all episodes have GCS audio!")
        return 0
    
    print(f"\nFound {len(episodes)} legacy episode(s) to migrate:")
    for ep in episodes:
        print(f"  - {ep.title} (ID: {ep.id}, Processed: {ep.processed_at})")
    
    if not args.dry_run:
        confirm = input(f"\nProceed with migration of {len(episodes)} episode(s)? [y/N]: ")
        if confirm.lower() != 'y':
            print("❌ Migration cancelled by user")
            return 0
    
    # Migrate episodes
    success_count = 0
    fail_count = 0
    
    for episode in episodes:
        try:
            if migrate_episode_to_gcs(episode, dry_run=args.dry_run):
                success_count += 1
            else:
                fail_count += 1
        except Exception as e:
            print(f"\n❌ CRITICAL ERROR migrating episode {episode.id}: {e}")
            import traceback
            traceback.print_exc()
            fail_count += 1
    
    # Summary
    print("\n" + "=" * 80)
    print("Migration Summary")
    print("=" * 80)
    print(f"✅ Success: {success_count}")
    print(f"❌ Failed: {fail_count}")
    print(f"📊 Total: {len(episodes)}")
    
    if args.dry_run:
        print("\n🔍 This was a DRY RUN - no changes were made")
        print("Run without --dry-run to perform the actual migration")
    elif success_count > 0:
        print(f"\n✅ Successfully migrated {success_count} episode(s) to GCS")
        print("Episodes are now playable in dashboard, manual editor, and RSS feed")
    
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
