"""
Quick R2 upload test script
Run from project root: python test_r2_upload.py
"""
import sys
import os
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

# Load environment from .env.local
from dotenv import load_dotenv
env_path = backend_dir / ".env.local"
load_dotenv(env_path)

print(f"✓ Loaded environment from {env_path}")
print(f"  STORAGE_BACKEND = {os.getenv('STORAGE_BACKEND')}")
print(f"  R2_BUCKET = {os.getenv('R2_BUCKET')}")
print(f"  R2_ACCOUNT_ID = {os.getenv('R2_ACCOUNT_ID')}")
access_key = os.getenv('R2_ACCESS_KEY_ID', '')
secret_key = os.getenv('R2_SECRET_ACCESS_KEY', '')
print(f"  R2_ACCESS_KEY_ID = {access_key[:8] if access_key else 'NOT SET'}...")
print(f"  R2_SECRET_ACCESS_KEY = {secret_key[:8] if secret_key else 'NOT SET'}...")
print()

# Import storage module
from api.infrastructure import storage

# Create test file
test_content = b"This is a test audio file for R2 upload verification"
test_filename = "test-r2-upload.txt"

print(f"📤 Uploading test file: {test_filename}")
print(f"   Content size: {len(test_content)} bytes")
print()

try:
    # Upload using storage abstraction (should route to R2)
    # Note: bucket_name is ignored, uses configured bucket from env
    gcs_path = storage.upload_bytes(
        bucket_name="",  # Ignored - uses STORAGE_BACKEND config
        key=test_filename,
        data=test_content,
        content_type="text/plain"
    )
    
    print(f"✅ Upload successful!")
    print(f"   Returned path: {gcs_path}")
    print()
    
    # Generate signed URL
    print(f"🔗 Generating signed URL for playback test...")
    signed_url = storage.generate_signed_url("", test_filename, expiration=3600)  # 1 hour
    print(f"   URL (valid for 1 hour):")
    print(f"   {signed_url}")
    print()
    
    # Verify file exists
    print(f"🔍 Verifying file exists in storage...")
    exists = storage.blob_exists("", test_filename)
    print(f"   File exists: {exists}")
    print()
    
    if exists:
        print("✅ R2 UPLOAD TEST PASSED!")
        print()
        print("Next steps:")
        print("  1. Open Cloudflare Dashboard → R2 → ppp-media bucket")
        print(f"     Verify '{test_filename}' appears in file list")
        print("  2. Copy signed URL above and paste in browser")
        print("     Should download the test file with content:")
        print(f"     '{test_content.decode('utf-8')}'")
        print()
        print("  3. Clean up test file:")
        print(f"     storage.delete_blob('{test_filename}')")
    else:
        print("❌ File upload succeeded but exists check failed")
        print("   This might indicate a configuration issue")
    
except Exception as e:
    print(f"❌ UPLOAD FAILED!")
    print(f"   Error: {e}")
    print()
    import traceback
    traceback.print_exc()
    sys.exit(1)
