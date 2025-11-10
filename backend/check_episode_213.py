"""Check Cinema IRL Episode 213 (S2E213)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from api.core.database import get_session
from api.models.podcast import Podcast, Episode
from api.routers.episodes.common import compute_cover_info
from sqlmodel import select, col
import json

session = next(get_session())

# Find Cinema IRL podcast
podcast = session.exec(select(Podcast).where(Podcast.name == "Cinema IRL")).first()
if not podcast:
    print("ERROR: Cinema IRL podcast NOT FOUND")
    sys.exit(1)

print(f"Found podcast: {podcast.name} (ID: {podcast.id})\n")

# Find Episode 213 - try by season/episode number first
episode = session.exec(
    select(Episode)
    .where(Episode.podcast_id == podcast.id)
    .where(Episode.season_number == 2)
    .where(Episode.episode_number == 213)
).first()

# If not found by number, try by title
if not episode:
    episodes = session.exec(
        select(Episode)
        .where(Episode.podcast_id == podcast.id)
        .where(Episode.title.ilike("%213%"))
        .order_by(col(Episode.created_at).desc())
    ).all()
    
    if episodes:
        episode = episodes[0]
        print(f"WARNING: Found episode by title search (not by season/episode number)")
    else:
        # Try "After the Hunt" which was mentioned in the UI
        episodes = session.exec(
            select(Episode)
            .where(Episode.podcast_id == podcast.id)
            .where(Episode.title.ilike("%After the Hunt%"))
            .order_by(col(Episode.created_at).desc())
        ).all()
        if episodes:
            episode = episodes[0]
            print(f"WARNING: Found episode by title 'After the Hunt'")

if not episode:
    print("ERROR: Episode 213 NOT FOUND")
    print("\nTrying to list recent episodes...")
    episodes = session.exec(
        select(Episode)
        .where(Episode.podcast_id == podcast.id)
        .order_by(col(Episode.created_at).desc())
        .limit(10)
    ).all()
    print(f"\nFound {len(episodes)} recent episodes:")
    for ep in episodes:
        print(f"  - {ep.title} (S{ep.season_number}E{ep.episode_number}) - ID: {ep.id}")
    sys.exit(1)

print("=" * 80)
print(f"EPISODE 213 DETAILS")
print("=" * 80)
print(f"ID: {episode.id}")
print(f"Title: {episode.title}")
print(f"Season: {episode.season_number}")
print(f"Episode: {episode.episode_number}")
print(f"Status: {episode.status}")
print(f"User ID: {episode.user_id}")
print(f"Podcast ID: {episode.podcast_id}")
print()

print("COVER IMAGE FIELDS:")
print("-" * 80)
print(f"cover_path: {episode.cover_path}")
print(f"gcs_cover_path: {episode.gcs_cover_path}")
print(f"remote_cover_url: {episode.remote_cover_url}")
print()

# Check cover info
print("COVER INFO (from compute_cover_info):")
print("-" * 80)
try:
    cover_info = compute_cover_info(episode)
    print(f"cover_url: {cover_info.get('cover_url')}")
    print(f"cover_source: {cover_info.get('cover_source')}")
    print(f"gcs_path: {cover_info.get('gcs_path')}")
except Exception as e:
    print(f"ERROR: Error computing cover info: {e}")
    import traceback
    traceback.print_exc()
print()

# Check other fields that might affect updates
print("OTHER FIELDS:")
print("-" * 80)
print(f"is_explicit: {episode.is_explicit}")
print(f"image_crop: {episode.image_crop}")
print(f"tags_json: {episode.tags_json}")
print(f"show_notes length: {len(episode.show_notes or '')}")
print()

# Check if there are any constraints or issues
print("VALIDATION CHECKS:")
print("-" * 80)

# Check if cover_path is too long
if episode.cover_path:
    cover_path_len = len(episode.cover_path)
    print(f"cover_path length: {cover_path_len} characters")
    if cover_path_len > 1000:
        print(f"WARNING: cover_path is very long ({cover_path_len} chars)")
    if episode.cover_path and not isinstance(episode.cover_path, str):
        print(f"WARNING: cover_path is not a string: {type(episode.cover_path)}")

# Check gcs_cover_path
if episode.gcs_cover_path:
    gcs_path_len = len(episode.gcs_cover_path)
    print(f"gcs_cover_path length: {gcs_path_len} characters")
    if gcs_path_len > 1000:
        print(f"WARNING: gcs_cover_path is very long ({gcs_path_len} chars)")
    if episode.gcs_cover_path and not isinstance(episode.gcs_cover_path, str):
        print(f"WARNING: gcs_cover_path is not a string: {type(episode.gcs_cover_path)}")

# Check for special characters that might cause issues
if episode.cover_path:
    problematic_chars = ['\x00', '\n', '\r']
    for char in problematic_chars:
        if char in episode.cover_path:
            print(f"WARNING: cover_path contains problematic character: {repr(char)}")

print()
print("=" * 80)
print("RAW DATABASE VALUES (for debugging):")
print("=" * 80)

# Get raw values from database
from sqlalchemy import text
result = session.execute(
    text("SELECT cover_path, gcs_cover_path, remote_cover_url FROM episode WHERE id = :ep_id"),
    {"ep_id": str(episode.id)}
).fetchone()

if result:
    raw_cover_path, raw_gcs_cover_path, raw_remote_cover_url = result
    print(f"Raw cover_path: {repr(raw_cover_path)}")
    print(f"Raw gcs_cover_path: {repr(raw_gcs_cover_path)}")
    print(f"Raw remote_cover_url: {repr(raw_remote_cover_url)}")
    print(f"cover_path type: {type(raw_cover_path)}")
    print(f"gcs_cover_path type: {type(raw_gcs_cover_path)}")
    print(f"remote_cover_url type: {type(raw_remote_cover_url)}")

session.close()

