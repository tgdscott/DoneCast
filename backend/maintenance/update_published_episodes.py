#!/usr/bin/env python3
"""
Maintenance job to update episode status from 'processed' to 'published'
when their publish_at time has passed.

This should be run periodically (e.g., every 5-15 minutes) via cron or scheduler.

Usage:
    python backend/maintenance/update_published_episodes.py
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select
from api.core.database import engine
from api.models.podcast import Episode, EpisodeStatus

def update_published_episodes():
    """Update episodes with past publish_at to published status."""
    now_utc = datetime.now(timezone.utc)
    
    with Session(engine) as session:
        # Find episodes that should be published but aren't
        # Criteria: publish_at is in past AND status is not 'published'
        episodes_to_update = session.exec(
            select(Episode)
            .where(
                Episode.publish_at.isnot(None),
                Episode.publish_at <= now_utc,
                Episode.status != EpisodeStatus.published
            )
        ).all()
        
        if not episodes_to_update:
            print(f"No episodes need status update (checked at {now_utc.isoformat()})")
            return 0
        
        print(f"Found {len(episodes_to_update)} episodes to update to 'published' status")
        
        updated = 0
        for ep in episodes_to_update:
            print(f"  Updating episode {ep.id}: {ep.status} -> published (publish_at was {ep.publish_at})")
            ep.status = EpisodeStatus.published
            # Also fix the flag if episode has spreaker_episode_id
            if ep.spreaker_episode_id and not ep.is_published_to_spreaker:
                ep.is_published_to_spreaker = True
            session.add(ep)
            updated += 1
        
        session.commit()
        print(f"\n✅ Updated {updated} episodes to 'published' status")
        return updated

if __name__ == "__main__":
    try:
        update_published_episodes()
    except Exception as e:
        print(f"Error updating episodes: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

