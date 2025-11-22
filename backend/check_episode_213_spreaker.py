"""Check if episode 213 is published to Spreaker and get cover URL"""
from api.core.database import get_session
from api.models.podcast import Podcast, Episode
from sqlmodel import select

session = next(get_session())

# Find Cinema IRL podcast
podcast = session.exec(select(Podcast).where(Podcast.name == "Cinema IRL")).first()
if not podcast:
    print("Cinema IRL podcast NOT FOUND")
    exit(1)

# Find episode 213
episode = session.exec(
    select(Episode)
    .where(Episode.podcast_id == podcast.id)
    .where(Episode.episode_number == 213)
).first()

if not episode:
    print("Episode 213 NOT FOUND")
    exit(1)

print(f"Episode 213: {episode.title}")
print(f"  Status: {episode.status}")
print(f"  Spreaker Episode ID: {episode.spreaker_episode_id}")
print(f"  Remote Cover URL: {episode.remote_cover_url}")
print(f"  Publish At: {episode.publish_at}")

if episode.spreaker_episode_id:
    print(f"\nEpisode is published to Spreaker!")
    print(f"  Spreaker ID: {episode.spreaker_episode_id}")
    if episode.remote_cover_url:
        print(f"  Cover URL: {episode.remote_cover_url}")
    else:
        print("  WARNING: No remote_cover_url stored")
        print("  You can fetch it from Spreaker API if needed")
else:
    print("\nEpisode is NOT published to Spreaker yet")
    print("  Will be published on: {episode.publish_at}")

