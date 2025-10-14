"""
Check episode 204's audio paths and GCS state
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from api.core.database import get_session
from api.models.podcast import Episode
from sqlmodel import select

def main():
    session = next(get_session())
    
    # Find episode 204
    ep = session.exec(select(Episode).where(Episode.episode_number == 204)).first()
    
    if not ep:
        print("❌ Episode 204 not found!")
        return
    
    print(f"✅ Found episode 204")
    print(f"   ID: {ep.id}")
    print(f"   Title: {ep.title}")
    print(f"   Status: {ep.status}")
    print(f"   Publish At: {ep.publish_at}")
    print(f"   \n   Audio Paths:")
    print(f"   - final_audio_path: {ep.final_audio_path}")
    print(f"   - gcs_audio_path: {ep.gcs_audio_path}")
    print(f"   - spreaker_episode_id: {ep.spreaker_episode_id}")
    print(f"   \n   Duration: {ep.duration_ms}ms" if ep.duration_ms else "   Duration: None")
    
    # Check if GCS file exists
    if ep.gcs_audio_path and str(ep.gcs_audio_path).startswith("gs://"):
        print(f"\n   Checking GCS file...")
        try:
            from infrastructure.gcs import get_signed_url
            gcs_str = str(ep.gcs_audio_path)[5:]  # Remove "gs://"
            parts = gcs_str.split("/", 1)
            if len(parts) == 2:
                bucket, key = parts
                print(f"   Bucket: {bucket}")
                print(f"   Key: {key}")
                
                # Try to generate signed URL
                try:
                    url = get_signed_url(bucket, key, expiration=3600)
                    if url:
                        print(f"   ✅ Signed URL generated successfully")
                        print(f"   URL: {url[:80]}...")
                    else:
                        print(f"   ❌ get_signed_url returned None")
                except Exception as e:
                    print(f"   ❌ Failed to generate signed URL: {e}")
        except Exception as e:
            print(f"   ❌ Error checking GCS: {e}")
    else:
        print(f"\n   ⚠️  No GCS audio path or invalid format")
    
    # Test compute_playback_info
    print(f"\n   Testing compute_playback_info()...")
    try:
        from api.routers.episodes.common import compute_playback_info
        info = compute_playback_info(ep)
        print(f"   Playback Info:")
        for key, value in info.items():
            if key == 'playback_url' and value:
                print(f"   - {key}: {str(value)[:80]}...")
            else:
                print(f"   - {key}: {value}")
    except Exception as e:
        print(f"   ❌ Error in compute_playback_info: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
