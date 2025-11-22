"""Fix episode 213 cover by migrating from GCS to R2"""
import os
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from api.core.database import get_session
from api.models.podcast import Podcast, Episode
from infrastructure import gcs, r2
from sqlmodel import select

def migrate_episode_213_cover():
    """Migrate episode 213's cover from GCS to R2"""
    session = next(get_session())
    
    # Find Cinema IRL podcast
    podcast = session.exec(select(Podcast).where(Podcast.name == "Cinema IRL")).first()
    if not podcast:
        print("Cinema IRL podcast NOT FOUND")
        return False
    
    # Find episode 213
    episode = session.exec(
        select(Episode)
        .where(Episode.podcast_id == podcast.id)
        .where(Episode.episode_number == 213)
    ).first()
    
    if not episode:
        print("Episode 213 NOT FOUND")
        return False
    
    print(f"Found Episode 213: {episode.title}")
    print(f"  ID: {episode.id}")
    print(f"  Current gcs_cover_path: {episode.gcs_cover_path}")
    print(f"  Current cover_path: {episode.cover_path}")
    print()
    
    # Check if already migrated
    if episode.gcs_cover_path and (
        str(episode.gcs_cover_path).startswith("https://") and ".r2.cloudflarestorage.com" in str(episode.gcs_cover_path)
        or str(episode.gcs_cover_path).startswith("r2://")
    ):
        print("SUCCESS: Episode 213 already has R2 cover URL")
        return True
    
    # Get GCS path from cover_path
    gcs_path = None
    if episode.cover_path and str(episode.cover_path).startswith("gs://"):
        gcs_path = episode.cover_path
    elif episode.gcs_cover_path and str(episode.gcs_cover_path).startswith("gs://"):
        gcs_path = episode.gcs_cover_path
    
    if not gcs_path:
        print("ERROR: No GCS path found in cover_path or gcs_cover_path")
        return False
    
    print(f"Migrating from GCS: {gcs_path}")
    
    # Parse GCS path
    gcs_str = str(gcs_path)[5:]  # Remove "gs://"
    parts = gcs_str.split("/", 1)
    if len(parts) != 2:
        print(f"ERROR: Invalid GCS path format: {gcs_path}")
        return False
    
    gcs_bucket, gcs_key = parts
    print(f"  GCS Bucket: {gcs_bucket}")
    print(f"  GCS Key: {gcs_key}")
    
    # Download from GCS
    print("\nDownloading from GCS...")
    cover_bytes = gcs.download_bytes(gcs_bucket, gcs_key)
    if not cover_bytes:
        print("ERROR: Failed to download cover from GCS")
        print("   The file may not exist in GCS")
        print("   Attempting to find cover in R2 or other locations...")
        
        # Try to find the cover in R2 using the filename
        filename = os.path.basename(gcs_key)
        episode_id_str = str(episode.id)
        r2_bucket = os.getenv("R2_BUCKET", "ppp-media").strip()
        
        # Try common R2 paths
        from infrastructure.r2 import blob_exists, download_bytes as r2_download_bytes
        r2_candidates = [
            f"covers/episode/{episode_id_str}/{filename}",
            f"{str(episode.user_id).replace('-', '')}/episodes/{episode_id_str}/cover/{filename}",
        ]
        
        for r2_key in r2_candidates:
            if blob_exists(r2_bucket, r2_key):
                print(f"   Found cover in R2 at: {r2_key}")
                cover_bytes = r2_download_bytes(r2_bucket, r2_key)
                if cover_bytes:
                    print(f"   Downloaded {len(cover_bytes):,} bytes from R2")
                    # Update database directly with R2 URL
                    from infrastructure.r2 import generate_signed_url
                    r2_url = f"https://{r2_bucket}.{os.getenv('R2_ACCOUNT_ID', '').strip()}.r2.cloudflarestorage.com/{r2_key}"
                    episode.gcs_cover_path = r2_url
                    episode.cover_path = filename
                    session.add(episode)
                    session.commit()
                    print(f"SUCCESS: Updated episode 213 with existing R2 URL")
                    print(f"  New gcs_cover_path: {episode.gcs_cover_path}")
                    return True
                break
        
        # Try downloading from Spreaker remote_cover_url if available
        if episode.remote_cover_url:
            print(f"   Trying to download from Spreaker: {episode.remote_cover_url}")
            try:
                import requests
                response = requests.get(episode.remote_cover_url, timeout=30)
                if response.status_code == 200 and response.content:
                    cover_bytes = response.content
                    print(f"   Downloaded {len(cover_bytes):,} bytes from Spreaker")
                    # Continue with upload to R2 below
                else:
                    print(f"   Spreaker download failed: HTTP {response.status_code}")
                    return False
            except Exception as spreaker_err:
                print(f"   Spreaker download error: {spreaker_err}")
                return False
        elif episode.spreaker_episode_id:
            # Fetch cover from Spreaker API
            print(f"   Fetching cover from Spreaker API (episode ID: {episode.spreaker_episode_id})...")
            try:
                import requests
                spreaker_access_token = os.getenv("SPREAKER_ACCESS_TOKEN", "").strip()
                if not spreaker_access_token:
                    # Try to get from user's podcast settings (podcast already loaded above)
                    if podcast and hasattr(podcast, 'spreaker_access_token') and podcast.spreaker_access_token:
                        spreaker_access_token = podcast.spreaker_access_token
                
                if not spreaker_access_token:
                    print("   ERROR: No Spreaker access token available")
                    return False
                
                # Fetch episode details from Spreaker API
                api_url = f"https://api.spreaker.com/v2/episodes/{episode.spreaker_episode_id}"
                headers = {"Authorization": f"Bearer {spreaker_access_token}"}
                response = requests.get(api_url, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    episode_data = data.get("response", {}).get("episode", {})
                    cover_url = episode_data.get("image_url") or episode_data.get("image_original_url")
                    
                    if cover_url:
                        print(f"   Found cover URL in Spreaker: {cover_url}")
                        # Download the cover image
                        cover_response = requests.get(cover_url, timeout=30)
                        if cover_response.status_code == 200 and cover_response.content:
                            cover_bytes = cover_response.content
                            print(f"   Downloaded {len(cover_bytes):,} bytes from Spreaker")
                            # Continue with upload to R2 below
                        else:
                            print(f"   Failed to download cover image: HTTP {cover_response.status_code}")
                            return False
                    else:
                        print("   No cover URL found in Spreaker episode data")
                        return False
                else:
                    print(f"   Spreaker API request failed: HTTP {response.status_code}")
                    return False
            except Exception as spreaker_err:
                print(f"   Spreaker API error: {spreaker_err}")
                return False
        else:
            print("   Cover not found in R2 or Spreaker. Cannot migrate.")
            return False
    
    print(f"SUCCESS: Downloaded {len(cover_bytes):,} bytes")
    
    # Determine content type
    content_type = "image/jpeg"
    if gcs_key.lower().endswith(".png"):
        content_type = "image/png"
    elif gcs_key.lower().endswith(".webp"):
        content_type = "image/webp"
    
    # Build R2 key (use episode ID-based path like other episodes)
    r2_bucket = os.getenv("R2_BUCKET", "ppp-media").strip()
    episode_id_str = str(episode.id)
    user_id_str = str(episode.user_id).replace("-", "")
    
    # Extract filename from GCS key
    filename = os.path.basename(gcs_key)
    
    # Use same structure as other episodes: covers/episode/{episode_id}/{filename}
    r2_key = f"covers/episode/{episode_id_str}/{filename}"
    
    print(f"\nUploading to R2...")
    print(f"  R2 Bucket: {r2_bucket}")
    print(f"  R2 Key: {r2_key}")
    
    r2_url = r2.upload_bytes(r2_bucket, r2_key, cover_bytes, content_type=content_type)
    if not r2_url:
        print("ERROR: Failed to upload cover to R2")
        return False
    
    print(f"SUCCESS: Uploaded to R2: {r2_url}")
    
    # Update database
    print(f"\nUpdating database...")
    episode.gcs_cover_path = r2_url
    # Also update cover_path to the filename (like episodes 212 and 214)
    episode.cover_path = filename
    session.add(episode)
    session.commit()
    
    print(f"SUCCESS: Database updated")
    print(f"  New gcs_cover_path: {episode.gcs_cover_path}")
    print(f"  New cover_path: {episode.cover_path}")
    
    return True

if __name__ == "__main__":
    success = migrate_episode_213_cover()
    sys.exit(0 if success else 1)

