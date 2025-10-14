"""
Test script to verify the music upload fix works correctly.
Run this AFTER restarting the API server.
"""
import os
import sys
import tempfile
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

print("="*60)
print("MUSIC UPLOAD FIX - VERIFICATION TEST")
print("="*60)
print()

# 1. Check environment
print("1. Environment Check:")
print("-" * 40)
media_bucket = os.getenv("MEDIA_BUCKET")
app_env = os.getenv("APP_ENV", os.getenv("ENV", "unknown"))
print(f"   MEDIA_BUCKET: {media_bucket or '(not set)'}")
print(f"   APP_ENV: {app_env}")
print()

# 2. Check if GCS will fallback to local
print("2. GCS Fallback Logic:")
print("-" * 40)
try:
    from infrastructure import gcs
    
    is_dev = gcs._is_dev_env()
    looks_local = gcs._looks_like_local_bucket(media_bucket or "")
    should_fallback = gcs._should_fallback(media_bucket or "")
    
    print(f"   Is dev environment: {is_dev}")
    print(f"   Looks like local bucket: {looks_local}")
    print(f"   Should fallback to local: {should_fallback}")
    print()
    
    if should_fallback:
        print("   ℹ️  GCS will use LOCAL file storage (dev mode)")
        local_dir = gcs._resolve_local_media_dir()
        print(f"   Local media dir: {local_dir}")
        print(f"   Dir exists: {local_dir.exists()}")
    else:
        print("   ℹ️  GCS will use CLOUD storage")
        print(f"   Bucket: {media_bucket}")
        
        # Check if GCS client can be initialized
        try:
            client = gcs._get_gcs_client()
            if client:
                print("   ✓ GCS client initialized")
            else:
                print("   ⚠️  GCS client is None (will fallback to local)")
        except Exception as e:
            print(f"   ⚠️  GCS client error: {e}")
    
    print()
except Exception as e:
    print(f"   ❌ Error checking GCS: {e}")
    import traceback
    traceback.print_exc()
    print()

# 3. Test file upload simulation
print("3. File Upload Simulation:")
print("-" * 40)
try:
    # Create a test audio file
    test_content = b"fake audio data for testing" * 1000  # ~27KB
    
    print(f"   Test file size: {len(test_content)} bytes")
    
    # Test the upload path logic
    if media_bucket:
        test_key = f"music/test_{Path(tempfile.mktemp()).name}.mp3"
        print(f"   Test key: {test_key}")
        
        # Simulate what the endpoint does
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            tmp.write(test_content)
            temp_path = tmp.name
        
        print(f"   Created temp file: {temp_path}")
        print(f"   Temp file exists: {os.path.exists(temp_path)}")
        
        try:
            with open(temp_path, "rb") as f:
                stored_uri = gcs.upload_fileobj(
                    media_bucket,
                    test_key,
                    f,
                    content_type="audio/mpeg"
                )
            print(f"   ✓ Upload succeeded!")
            print(f"   Stored URI: {stored_uri}")
            
            # Check what path would be saved
            if stored_uri.startswith("gs://"):
                filename_stored = stored_uri
            else:
                filename_stored = f"/static/media/{Path(stored_uri).name}"
            print(f"   Database path: {filename_stored}")
            
        except Exception as e:
            print(f"   ❌ Upload failed: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)
                print(f"   Cleaned up temp file")
    else:
        print("   ⚠️  No MEDIA_BUCKET set, testing local only")
        from api.core.paths import MEDIA_DIR
        music_dir = MEDIA_DIR / "music"
        music_dir.mkdir(parents=True, exist_ok=True)
        
        test_file = music_dir / f"test_{Path(tempfile.mktemp()).name}.mp3"
        test_file.write_bytes(test_content)
        
        print(f"   ✓ Wrote to: {test_file}")
        print(f"   File exists: {test_file.exists()}")
        
        filename_stored = f"/static/media/music/{test_file.name}"
        print(f"   Database path: {filename_stored}")
        
        # Clean up
        test_file.unlink()
        print(f"   Cleaned up test file")
    
    print()
except Exception as e:
    print(f"   ❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
    print()

# 4. Check the actual endpoint code
print("4. Endpoint Code Check:")
print("-" * 40)
try:
    music_file = Path("backend/api/routers/admin/music.py")
    if music_file.exists():
        with open(music_file) as f:
            content = f.read()
            
        if "async def admin_upload_music_asset" in content:
            print("   ✓ Endpoint is async")
        else:
            print("   ❌ Endpoint is NOT async")
        
        if "await file.read()" in content:
            print("   ✓ Uses await file.read()")
        else:
            print("   ❌ Does NOT use await file.read()")
        
        if "tempfile.NamedTemporaryFile" in content:
            print("   ✓ Uses temp file for GCS")
        else:
            print("   ❌ Does NOT use temp file")
        
        if "[admin-music-upload]" in content:
            print("   ✓ Has logging tags")
        else:
            print("   ⚠️  Missing logging tags")
    else:
        print(f"   ❌ File not found: {music_file}")
    print()
except Exception as e:
    print(f"   ❌ Check failed: {e}")
    print()

print("="*60)
print("TEST COMPLETE")
print("="*60)
print()
print("If all checks passed, the fix should work.")
print("If GCS upload simulation failed, that's the problem to fix.")
print()
