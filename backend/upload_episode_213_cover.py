"""Upload cover image for episode 213 directly to R2.

Usage:
    python upload_episode_213_cover.py <path_to_cover_image.jpg>

This script will:
1. Find episode 213
2. Upload the cover image to R2
3. Update the database with the R2 URL
"""
import os
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from api.core.database import get_session
from api.models.podcast import Podcast, Episode
import infrastructure.r2 as r2_module
from sqlmodel import select

def upload_episode_213_cover(image_path: str) -> bool:
    """Upload cover image for episode 213 to R2."""
    session = next(get_session())
    
    # Find Cinema IRL podcast
    podcast = session.exec(select(Podcast).where(Podcast.name == "Cinema IRL")).first()
    if not podcast:
        print("ERROR: Cinema IRL podcast not found")
        return False
    
    # Find episode 213
    episode = session.exec(
        select(Episode)
        .where(Episode.podcast_id == podcast.id)
        .where(Episode.episode_number == 213)
    ).first()
    
    if not episode:
        print("ERROR: Episode 213 not found")
        return False
    
    print(f"Found Episode 213: {episode.title}")
    print(f"  ID: {episode.id}")
    
    # Check if already has R2 cover
    if episode.gcs_cover_path and (
        str(episode.gcs_cover_path).startswith("https://") and ".r2.cloudflarestorage.com" in str(episode.gcs_cover_path)
        or str(episode.gcs_cover_path).startswith("r2://")
    ):
        print(f"Episode 213 already has R2 cover: {episode.gcs_cover_path}")
        response = input("Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Cancelled")
            return False
    
    # Read the image file
    image_path_obj = Path(image_path)
    if not image_path_obj.exists():
        print(f"ERROR: Image file not found: {image_path}")
        return False
    
    print(f"\nReading image file: {image_path}")
    cover_bytes = image_path_obj.read_bytes()
    print(f"Read {len(cover_bytes):,} bytes")
    
    # Determine content type
    content_type = "image/jpeg"
    ext = image_path_obj.suffix.lower()
    if ext == ".png":
        content_type = "image/png"
    elif ext == ".webp":
        content_type = "image/webp"
    elif ext == ".gif":
        content_type = "image/gif"
    
    # Upload to R2
    r2_bucket = os.getenv("R2_BUCKET", "ppp-media").strip()
    episode_id_str = str(episode.id)
    filename = image_path_obj.name
    
    # Use same structure as other episodes: covers/episode/{episode_id}/{filename}
    r2_key = f"covers/episode/{episode_id_str}/{filename}"
    
    print(f"\nUploading to R2...")
    print(f"  R2 Bucket: {r2_bucket}")
    print(f"  R2 Key: {r2_key}")
    print(f"  Content Type: {content_type}")
    
    r2_url = r2_module.upload_bytes(r2_bucket, r2_key, cover_bytes, content_type=content_type)
    if not r2_url:
        print("ERROR: Failed to upload cover to R2")
        return False
    
    print(f"SUCCESS: Uploaded to R2: {r2_url}")
    
    # Update database
    print(f"\nUpdating database...")
    episode.gcs_cover_path = r2_url
    episode.cover_path = filename
    session.add(episode)
    session.commit()
    
    print(f"SUCCESS: Database updated")
    print(f"  New gcs_cover_path: {episode.gcs_cover_path}")
    print(f"  New cover_path: {episode.cover_path}")
    
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python upload_episode_213_cover.py <path_to_cover_image.jpg>")
        sys.exit(1)
    
    image_path = sys.argv[1]
    success = upload_episode_213_cover(image_path)
    sys.exit(0 if success else 1)

