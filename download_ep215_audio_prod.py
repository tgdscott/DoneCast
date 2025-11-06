#!/usr/bin/env python3
"""
Download audio files for Episode 215 from GCS for comparison.
PRODUCTION VERSION - connects to production database via gcloud sql proxy

Prerequisites:
1. gcloud auth application-default login
2. Start Cloud SQL proxy in another terminal:
   gcloud sql connect podcast612-db-prod --user=postgres --database=podcast612

Usage:
    # Set production database URL
    export DATABASE_URL="postgresql://postgres:PASSWORD@127.0.0.1:5432/podcast612"
    python download_ep215_audio_prod.py
"""

import os
import sys
import json
from pathlib import Path

def main():
    print("=" * 80)
    print("EPISODE 215 AUDIO DOWNLOAD TOOL (Manual GCS Version)")
    print("=" * 80)
    
    print("\n⚠️  This script requires manual GCS download since DB connection is complex")
    print("\n📋 INSTRUCTIONS:")
    print("\n1. Run database query to get GCS paths:")
    print("   python check_ep215_db.py")
    print("   # Follow instructions to query production DB")
    print("\n2. Look for these fields in the result:")
    print("   - main_content MediaItem.gcs_audio_path (original)")
    print("   - meta_json.cleaned_audio_gcs_uri (cleaned)")
    print("   - episode.gcs_audio_path (final)")
    print("\n3. Download manually with gsutil:")
    print("   gsutil cp gs://ppp-media-us-west1/USER_ID/audio/FILENAME.mp3 ./01_original.mp3")
    print("   gsutil cp gs://ppp-media-us-west1/USER_ID/cleaned_audio/FILENAME.mp3 ./02_cleaned.mp3")
    print("   gsutil cp gs://ppp-media-us-west1/USER_ID/episodes/FILENAME.mp3 ./03_final.mp3")
    
    print("\n4. OR use GCS Console:")
    print("   https://console.cloud.google.com/storage/browser/ppp-media-us-west1")
    print("   Navigate to folders and download files")
    
    print("\n5. Compare in Audacity:")
    print("   - Open all 3 files")
    print("   - Check waveforms")
    print("   - Listen for quality differences")
    
    print("\n🔍 What to check:")
    print("   1. Does ORIGINAL have quality issues? → Your recording")
    print("   2. Does CLEANED sound worse? → Our clean_engine")
    print("   3. Does FINAL sound worse? → Our mixing/compression")
    
    print("\n💡 TIP: AssemblyAI returns the SAME audio you uploaded")
    print("   So ORIGINAL = what AssemblyAI processed")
    print("   Any audio modifications come from OUR pipeline")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
