import sys
sys.path.insert(0, 'backend')

from api.models.podcast import Podcast
from uuid import uuid4

# Create a mock podcast to test the property
podcast = Podcast(
    id=uuid4(),
    user_id=uuid4(),
    title="Cinema IRL",
    slug="cinema-irl"
)

print(f"Podcast RSS Feed URL: {podcast.rss_feed_url}")
print(f"Expected: https://podcastplusplus.com/rss/cinema-irl/feed.xml")
print(f"Match: {podcast.rss_feed_url == 'https://podcastplusplus.com/rss/cinema-irl/feed.xml'}")

# Test without slug (should use ID)
podcast_no_slug = Podcast(
    id=uuid4(),
    user_id=uuid4(),
    title="Test Podcast"
)
print(f"\nPodcast without slug: {podcast_no_slug.rss_feed_url}")
print(f"Uses ID: {str(podcast_no_slug.id) in podcast_no_slug.rss_feed_url}")
