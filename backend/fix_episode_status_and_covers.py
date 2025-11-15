#!/usr/bin/env python3
"""
Fix script to standardize episode database:
1. Fix published status for episodes that should be published
2. Fix cover_path/gcs_cover_path inconsistencies
3. Standardize data across all episodes
"""
import os
import sys
from pathlib import Path
import argparse

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlmodel import Session, select
from api.core.database import engine
from api.models.podcast import Episode, EpisodeStatus
from datetime import datetime, timezone

def fix_episode_status(session, dry_run=True):
    """Fix episodes that should be published but aren't."""
    now_utc = datetime.utcnow()
    
    # Find episodes that should be published
    # Criteria: 
    # 1. has publish_at in past (already published, regardless of spreaker_episode_id)
    # 2. OR has spreaker_episode_id AND (publish_at is null OR publish_at is in past)
    # 
    # NOTE: Episodes with future publish_at should remain scheduled/processed, not be marked published
    # Even if they have spreaker_episode_id, if publish_at is in future, they're scheduled, not published
    episodes_to_fix = session.exec(
        select(Episode)
        .where(
            (
                # Has publish_at in past (already published)
                (Episode.publish_at.isnot(None) & (Episode.publish_at <= now_utc)) |
                # OR has spreaker_episode_id AND no future publish_at (null or past)
                (
                    Episode.spreaker_episode_id.isnot(None) &
                    (
                        Episode.publish_at.is_(None) |
                        (Episode.publish_at <= now_utc)
                    )
                )
            ),
            Episode.status != EpisodeStatus.published
        )
    ).all()
    
    print(f"Found {len(episodes_to_fix)} episodes that should be published")
    print("(Excluding episodes with future publish_at dates - those should remain scheduled)")
    
    if not episodes_to_fix:
        return 0
    
    fixed = 0
    for ep in episodes_to_fix:
        reason = []
        has_past_publish_at = ep.publish_at and ep.publish_at <= now_utc
        has_future_publish_at = ep.publish_at and ep.publish_at > now_utc
        
        if has_future_publish_at:
            # Skip episodes scheduled for the future - they should NOT be marked as published
            print(f"  SKIPPING Episode {ep.id}: has future publish_at={ep.publish_at} (should remain {ep.status})")
            continue
            
        if has_past_publish_at:
            reason.append(f"publish_at={ep.publish_at} (in past)")
        if ep.spreaker_episode_id:
            reason.append(f"spreaker_episode_id={ep.spreaker_episode_id}")
            # Also fix the is_published_to_spreaker flag if it's wrong
            if not ep.is_published_to_spreaker:
                reason.append("(also fixing is_published_to_spreaker=True)")
        
        print(f"  Episode {ep.id}: status={ep.status} -> published (reason: {', '.join(reason)})")
        
        if not dry_run:
            ep.status = EpisodeStatus.published
            # Fix the flag if episode has spreaker_episode_id
            if ep.spreaker_episode_id and not ep.is_published_to_spreaker:
                ep.is_published_to_spreaker = True
            session.add(ep)
            fixed += 1
    
    if not dry_run:
        session.commit()
        print(f"\n✅ Fixed {fixed} episodes")
    else:
        print(f"\n[DRY RUN] Would fix {len(episodes_to_fix)} episodes")
    
    return fixed if not dry_run else 0

def fix_cover_paths(session, dry_run=True):
    """Fix cover_path/gcs_cover_path inconsistencies."""
    # Find episodes with R2 URL in cover_path but gcs_cover_path is NULL
    episodes_to_fix = session.exec(
        select(Episode)
        .where(
            Episode.cover_path.isnot(None),
            Episode.cover_path.like("https://%.r2.cloudflarestorage.com%"),
            Episode.gcs_cover_path.is_(None)
        )
    ).all()
    
    print(f"\nFound {len(episodes_to_fix)} episodes with R2 URL in cover_path but gcs_cover_path is NULL")
    
    if not episodes_to_fix:
        return 0
    
    fixed = 0
    for ep in episodes_to_fix:
        print(f"  Episode {ep.id}: setting gcs_cover_path = cover_path ({ep.cover_path[:60]}...)")
        
        if not dry_run:
            ep.gcs_cover_path = ep.cover_path
            session.add(ep)
            fixed += 1
    
    if not dry_run:
        session.commit()
        print(f"\n✅ Fixed {fixed} cover paths")
    else:
        print(f"\n[DRY RUN] Would fix {len(episodes_to_fix)} cover paths")
    
    return fixed if not dry_run else 0

def main():
    parser = argparse.ArgumentParser(
        description="Fix episode status and cover path issues",
        epilog="""
Note: This script fixes historical data. For ongoing maintenance, run:
  python backend/maintenance/update_published_episodes.py
  
This should be scheduled to run periodically (e.g., every 15 minutes) to automatically
update episodes when their publish_at time passes.
        """
    )
    parser.add_argument("--dry-run", action="store_true", help="Don't make changes, just show what would be fixed")
    parser.add_argument("--fix-status", action="store_true", help="Fix published status issues")
    parser.add_argument("--fix-covers", action="store_true", help="Fix cover path issues")
    parser.add_argument("--fix-all", action="store_true", help="Fix all issues")
    
    args = parser.parse_args()
    
    if not (args.fix_status or args.fix_covers or args.fix_all):
        print("No fixes specified. Use --fix-status, --fix-covers, or --fix-all")
        print("Use --dry-run to see what would be changed without making changes")
        return
    
    dry_run = args.dry_run
    if dry_run:
        print("=" * 80)
        print("DRY RUN MODE - No changes will be made")
        print("=" * 80)
    
    with Session(engine) as session:
        total_fixed = 0
        
        if args.fix_all or args.fix_status:
            print("\n" + "=" * 80)
            print("FIXING EPISODE STATUS")
            print("=" * 80)
            total_fixed += fix_episode_status(session, dry_run=dry_run)
        
        if args.fix_all or args.fix_covers:
            print("\n" + "=" * 80)
            print("FIXING COVER PATHS")
            print("=" * 80)
            total_fixed += fix_cover_paths(session, dry_run=dry_run)
        
        if not dry_run:
            print(f"\n✅ Total fixes applied: {total_fixed}")
        else:
            print(f"\n[DRY RUN] Total fixes that would be applied: {total_fixed}")

if __name__ == "__main__":
    main()

