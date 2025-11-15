#!/usr/bin/env python3
"""
Diagnostic script to analyze episode database issues:
1. Compare episodes <200 vs >200 for publish status discrepancies
2. Check cover_path/gcs_cover_path issues
3. Identify data inconsistencies
"""
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlmodel import Session, select, func
from api.core.database import engine
from api.models.podcast import Episode, EpisodeStatus
from datetime import datetime, timezone

def analyze_episodes():
    with Session(engine) as session:
        # Get total count
        total = session.exec(select(func.count(Episode.id))).one()
        print(f"Total episodes: {total}\n")
        
        # Split at episode 200 (using created_at as proxy for ID ordering)
        # Get episodes ordered by created_at
        all_eps = session.exec(
            select(Episode)
            .order_by(Episode.created_at)
        ).all()
        
        if len(all_eps) < 200:
            print("Less than 200 episodes total, using all episodes for 'under 200' group")
            under_200 = all_eps
            over_200 = []
        else:
            under_200 = all_eps[:200]
            over_200 = all_eps[200:]
        
        print("=" * 80)
        print("EPISODES UNDER 200 (first 200 by created_at)")
        print("=" * 80)
        analyze_group(under_200, "Under 200")
        
        if over_200:
            print("\n" + "=" * 80)
            print("EPISODES OVER 200 (after first 200 by created_at)")
            print("=" * 80)
            analyze_group(over_200, "Over 200")
        
        # Check for specific issues
        print("\n" + "=" * 80)
        print("SPECIFIC ISSUES")
        print("=" * 80)
        
        # Episodes that should be published but aren't
        now_utc = datetime.utcnow()
        should_be_published = session.exec(
            select(Episode)
            .where(
                Episode.publish_at.isnot(None),
                Episode.publish_at <= now_utc,
                Episode.status != EpisodeStatus.published
            )
        ).all()
        
        print(f"\nEpisodes with publish_at in past but status != 'published': {len(should_be_published)}")
        if should_be_published:
            print("Sample (first 10):")
            for ep in should_be_published[:10]:
                print(f"  ID: {ep.id}, status: {ep.status}, publish_at: {ep.publish_at}, "
                      f"is_published_to_spreaker: {ep.is_published_to_spreaker}, "
                      f"spreaker_episode_id: {ep.spreaker_episode_id}")
        
        # Episodes with spreaker_episode_id but status != published
        has_spreaker_id = session.exec(
            select(Episode)
            .where(
                Episode.spreaker_episode_id.isnot(None),
                Episode.status != EpisodeStatus.published
            )
        ).all()
        
        print(f"\nEpisodes with spreaker_episode_id but status != 'published': {len(has_spreaker_id)}")
        if has_spreaker_id:
            print("Sample (first 10):")
            for ep in has_spreaker_id[:10]:
                print(f"  ID: {ep.id}, status: {ep.status}, publish_at: {ep.publish_at}, "
                      f"is_published_to_spreaker: {ep.is_published_to_spreaker}, "
                      f"spreaker_episode_id: {ep.spreaker_episode_id}")
        
        # Cover path issues
        no_cover = session.exec(
            select(Episode)
            .where(
                Episode.cover_path.is_(None),
                Episode.gcs_cover_path.is_(None),
                Episode.remote_cover_url.is_(None)
            )
        ).all()
        
        print(f"\nEpisodes with no cover (cover_path, gcs_cover_path, remote_cover_url all NULL): {len(no_cover)}")
        
        # Episodes with cover_path but no gcs_cover_path (R2 URL)
        cover_path_but_no_gcs = session.exec(
            select(Episode)
            .where(
                Episode.cover_path.isnot(None),
                Episode.cover_path.like("https://%"),
                Episode.gcs_cover_path.is_(None)
            )
        ).all()
        
        print(f"\nEpisodes with R2 URL in cover_path but gcs_cover_path is NULL: {len(cover_path_but_no_gcs)}")
        if cover_path_but_no_gcs:
            print("Sample (first 5):")
            for ep in cover_path_but_no_gcs[:5]:
                print(f"  ID: {ep.id}, cover_path: {ep.cover_path[:80]}...")

def analyze_group(episodes, label):
    if not episodes:
        print(f"No episodes in {label} group")
        return
    
    total = len(episodes)
    
    # Status breakdown
    status_counts = {}
    for ep in episodes:
        status = str(ep.status)
        status_counts[status] = status_counts.get(status, 0) + 1
    
    print(f"Total: {total}")
    print(f"Status breakdown:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")
    
    # Published status analysis
    published_count = sum(1 for ep in episodes if ep.status == EpisodeStatus.published)
    has_publish_at = sum(1 for ep in episodes if ep.publish_at is not None)
    has_spreaker_id = sum(1 for ep in episodes if ep.spreaker_episode_id is not None)
    is_published_to_spreaker = sum(1 for ep in episodes if ep.is_published_to_spreaker)
    
    print(f"\nPublished indicators:")
    print(f"  status == 'published': {published_count}")
    print(f"  has publish_at: {has_publish_at}")
    print(f"  has spreaker_episode_id: {has_spreaker_id}")
    print(f"  is_published_to_spreaker: {is_published_to_spreaker}")
    
    # Episodes that should appear published but don't
    now_utc = datetime.utcnow()
    should_be_published = [
        ep for ep in episodes
        if ep.publish_at and ep.publish_at <= now_utc and ep.status != EpisodeStatus.published
    ]
    print(f"  Should be published (publish_at in past, status != published): {len(should_be_published)}")
    
    # Cover analysis
    has_cover_path = sum(1 for ep in episodes if ep.cover_path is not None)
    has_gcs_cover_path = sum(1 for ep in episodes if ep.gcs_cover_path is not None)
    has_remote_cover = sum(1 for ep in episodes if ep.remote_cover_url is not None)
    has_any_cover = sum(1 for ep in episodes if ep.cover_path or ep.gcs_cover_path or ep.remote_cover_url)
    
    print(f"\nCover analysis:")
    print(f"  has cover_path: {has_cover_path}")
    print(f"  has gcs_cover_path: {has_gcs_cover_path}")
    print(f"  has remote_cover_url: {has_remote_cover}")
    print(f"  has any cover: {has_any_cover}")
    print(f"  no cover at all: {total - has_any_cover}")

if __name__ == "__main__":
    analyze_episodes()

