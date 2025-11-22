"""Diagnostic script to check episode 213 cover issue"""
from api.core.database import get_session
from api.models.podcast import Podcast, Episode
from api.routers.episodes.common import compute_cover_info
from sqlmodel import select, col

sess = next(get_session())

# Find Cinema IRL podcast
podcast = sess.exec(select(Podcast).where(Podcast.name == "Cinema IRL")).first()
if not podcast:
    print("Cinema IRL podcast NOT FOUND")
    exit(1)

print(f"Podcast: {podcast.name} (ID: {podcast.id})\n")

# Find episode 213
episode_213 = sess.exec(
    select(Episode)
    .where(Episode.podcast_id == podcast.id)
    .where(Episode.episode_number == 213)
).first()

if not episode_213:
    print("Episode 213 NOT FOUND")
    exit(1)

print("=" * 80)
print("EPISODE 213 DETAILS")
print("=" * 80)
print(f"ID: {episode_213.id}")
print(f"Title: {episode_213.title}")
print(f"Status: {episode_213.status}")
print(f"Episode Number: {episode_213.episode_number}")
print(f"Publish At: {episode_213.publish_at}")
print()
print("COVER FIELDS:")
print(f"  gcs_cover_path: {episode_213.gcs_cover_path}")
print(f"  cover_path: {episode_213.cover_path}")
print(f"  remote_cover_url: {episode_213.remote_cover_url}")
print()

# Get cover info
cover_info = compute_cover_info(episode_213)
print("COMPUTED COVER INFO:")
print(f"  cover_url: {cover_info.get('cover_url')}")
print(f"  cover_source: {cover_info.get('cover_source')}")
print(f"  within_7day_window: {cover_info.get('within_7day_window')}")
print()

# Compare with other episodes (212, 214)
print("=" * 80)
print("COMPARISON WITH OTHER EPISODES")
print("=" * 80)

for ep_num in [212, 214]:
    ep = sess.exec(
        select(Episode)
        .where(Episode.podcast_id == podcast.id)
        .where(Episode.episode_number == ep_num)
    ).first()
    
    if ep:
        print(f"\nEpisode {ep_num}:")
        print(f"  Title: {ep.title}")
        print(f"  Status: {ep.status}")
        print(f"  gcs_cover_path: {ep.gcs_cover_path}")
        print(f"  cover_path: {ep.cover_path}")
        cover_info_other = compute_cover_info(ep)
        print(f"  Computed cover_url: {cover_info_other.get('cover_url')}")
        print(f"  cover_source: {cover_info_other.get('cover_source')}")
    else:
        print(f"\nEpisode {ep_num}: NOT FOUND")

print("\n" + "=" * 80)
print("ANALYSIS")
print("=" * 80)

# Check if gcs_cover_path is an R2 URL
if episode_213.gcs_cover_path:
    gcs_path_str = str(episode_213.gcs_cover_path)
    if gcs_path_str.startswith("https://") and ".r2.cloudflarestorage.com" in gcs_path_str:
        print("✓ Episode 213 has R2 URL in gcs_cover_path")
        print(f"  URL: {gcs_path_str[:100]}...")
    elif gcs_path_str.startswith("r2://"):
        print("✓ Episode 213 has R2 URI in gcs_cover_path")
        print(f"  URI: {gcs_path_str}")
    elif gcs_path_str.startswith("gs://"):
        print("⚠ Episode 213 has GCS URI (legacy) in gcs_cover_path")
        print(f"  URI: {gcs_path_str}")
    else:
        print(f"⚠ Episode 213 gcs_cover_path format unknown: {gcs_path_str[:100]}")
else:
    print("❌ Episode 213 has NO gcs_cover_path")

if not cover_info.get('cover_url'):
    print("\n❌ PROBLEM: Episode 213 has NO cover_url!")
    print("This means _cover_url_for() returned None")
    print("\nPossible causes:")
    print("  1. R2 signed URL generation failed")
    print("  2. R2 credentials missing or invalid")
    print("  3. R2 URL parsing failed")
    print("  4. File doesn't exist in R2")
else:
    print(f"\n✓ Episode 213 has cover_url: {cover_info.get('cover_url')[:100]}...")

