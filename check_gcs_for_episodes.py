"""
Check Google Cloud Storage for Cinema IRL episodes 195-201
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))

try:
    from google.cloud import storage
    
    # Your GCS bucket name (check your environment variables or settings)
    BUCKET_NAME = os.getenv("GCS_BUCKET", "podcastpro-media")
    
    print(f"Checking GCS bucket: {BUCKET_NAME}")
    print("=" * 60)
    
    # List all files in the episodes folder
    print("\nLooking for episode audio files...\n")
    
    try:
        # Try to list files
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        
        # Check for Cinema IRL episode files
        # They might be named with episode numbers or IDs
        patterns_to_check = [
            "episodes/",
            "final/",
            "media/",
            "cinema-irl/",
            "Cinema IRL/",
        ]
        
        for pattern in patterns_to_check:
            print(f"\n🔍 Checking: {pattern}")
            blobs = list(bucket.list_blobs(prefix=pattern, max_results=100))
            
            if blobs:
                print(f"   Found {len(blobs)} files")
                
                # Look for files that might be episodes 195-201
                for blob in blobs:
                    name = blob.name.lower()
                    # Check if filename contains episode numbers 195-201
                    for ep_num in range(195, 202):
                        if (f"e{ep_num}" in name or 
                            f"ep{ep_num}" in name or 
                            f"episode{ep_num}" in name or
                            f"_{ep_num}_" in name or
                            f"s2e{ep_num}" in name):
                            print(f"   ✅ FOUND: {blob.name}")
                            print(f"      Size: {blob.size / 1024 / 1024:.2f} MB")
                            print(f"      Updated: {blob.updated}")
                            print(f"      gs://{BUCKET_NAME}/{blob.name}")
            else:
                print(f"   (empty)")
        
        # Also try to list ALL files (limited) to see what's there
        print(f"\n\n📦 Sample of recent files in bucket:")
        all_blobs = list(bucket.list_blobs(max_results=50))
        for blob in all_blobs[:20]:
            print(f"   {blob.name} ({blob.size / 1024 / 1024:.2f} MB)")
        
        if len(all_blobs) > 20:
            print(f"   ... and {len(all_blobs) - 20} more files")
            
    except Exception as e:
        print(f"❌ Error accessing GCS: {e}")
        print("\nMake sure:")
        print("1. GOOGLE_APPLICATION_CREDENTIALS environment variable is set")
        print("2. You have the service account key file")
        print("3. The service account has Storage Object Viewer permissions")
        
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("\nMake sure google-cloud-storage is installed:")
    print("pip install google-cloud-storage")
