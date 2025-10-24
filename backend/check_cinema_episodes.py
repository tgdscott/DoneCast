"""Check Cinema IRL episode data"""
from api.core.database import get_session
from api.models.podcast import Podcast, Episode, EpisodeStatus
from api.routers.episodes.common import compute_playback_info
from sqlmodel import select, col

sess = next(get_session())

# Find Cinema IRL podcast
podcast = sess.exec(select(Podcast).where(Podcast.name == "Cinema IRL")).first()
if not podcast:
    print("Cinema IRL podcast NOT FOUND")
    exit(1)

print(f"Podcast: {podcast.name} (ID: {podcast.id})")
print(f"Cover URL: {podcast.cover_path}\n")

# Get all episodes
episodes = sess.exec(
    select(Episode)
    .where(Episode.podcast_id == podcast.id)
    .order_by(col(Episode.created_at).desc())
    .limit(5)
).all()

print(f"Found {len(episodes)} episodes:\n")

for i, ep in enumerate(episodes, 1):
    print(f"{i}. {ep.title}")
    print(f"   Status: {ep.status}")
    print(f"   GCS Path: {ep.gcs_audio_path}")
    print(f"   Final Path: {ep.final_audio_path}")
    
    # Get playback URL
    playback_info = compute_playback_info(ep)
    print(f"   Playback URL: {playback_info.get('url')}")
    print(f"   Playback Type: {playback_info.get('playback_type')}")
    print()
