#!/usr/bin/env python3
"""
Download audio files for Episode 215 from GCS for comparison.
This helps identify where audio quality issues originate.

Usage:
    python download_ep215_audio.py
    
Downloads:
1. Original uploaded audio (what you sent to AssemblyAI)
2. Cleaned audio from our pipeline (if exists)
3. Final published episode audio

Then you can compare with audio software (Audacity, etc.)
"""

import os
import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from google.cloud import storage
from api.core.config import settings
from api.core.database import get_session
from api.models.podcast import Episode, MediaItem
from sqlmodel import select

def download_from_gcs(gs_uri: str, local_path: Path):
    """Download a file from GCS to local path."""
    if not gs_uri or not gs_uri.startswith("gs://"):
        print(f"  ❌ Invalid GCS URI: {gs_uri}")
        return False
    
    try:
        # Parse gs://bucket/path/to/file.mp3
        parts = gs_uri.replace("gs://", "").split("/", 1)
        bucket_name = parts[0]
        blob_name = parts[1] if len(parts) > 1 else ""
        
        print(f"  📥 Downloading from gs://{bucket_name}/{blob_name}")
        
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        local_path.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(local_path))
        
        size_mb = local_path.stat().st_size / (1024 * 1024)
        print(f"  ✅ Downloaded: {local_path.name} ({size_mb:.2f} MB)")
        return True
    except Exception as e:
        print(f"  ❌ Download failed: {e}")
        return False

def main():
    print("=" * 80)
    print("EPISODE 215 AUDIO DOWNLOAD TOOL")
    print("=" * 80)
    
    output_dir = Path("ep215_audio_comparison")
    output_dir.mkdir(exist_ok=True)
    print(f"\n📁 Output directory: {output_dir.absolute()}\n")
    
    session = next(get_session())
    
    # Get Episode 215
    ep = session.exec(select(Episode).where(Episode.id == 215)).first()
    if not ep:
        print("❌ Episode 215 not found in database!")
        return
    
    print(f"📻 Episode: {ep.title}")
    print(f"   Status: {ep.status}")
    print(f"   Working audio: {ep.working_audio_name}\n")
    
    meta = json.loads(ep.meta_json or '{}')
    downloads = []
    
    # 1. Original/Main Content Audio
    print("1️⃣  ORIGINAL AUDIO (what went to AssemblyAI)")
    if ep.main_content_id:
        media = session.get(MediaItem, ep.main_content_id)
        if media and media.gcs_audio_path:
            local_file = output_dir / f"01_original_{Path(media.filename or 'audio.mp3').name}"
            if download_from_gcs(media.gcs_audio_path, local_file):
                downloads.append(("Original Upload", local_file))
        else:
            print(f"  ℹ️  GCS path not found for main_content_id={ep.main_content_id}")
    else:
        print("  ℹ️  No main_content_id set")
    
    # 2. Cleaned Audio from our pipeline
    print("\n2️⃣  CLEANED AUDIO (our processing)")
    cleaned_gcs = meta.get('cleaned_audio_gcs_uri')
    if cleaned_gcs:
        local_file = output_dir / f"02_cleaned_{Path(cleaned_gcs).name}"
        if download_from_gcs(cleaned_gcs, local_file):
            downloads.append(("Our Cleaned Audio", local_file))
    else:
        print("  ℹ️  No cleaned_audio_gcs_uri in meta_json")
    
    # 3. Final Episode Audio
    print("\n3️⃣  FINAL EPISODE AUDIO (published)")
    if ep.gcs_audio_path:
        local_file = output_dir / f"03_final_{Path(ep.gcs_audio_path).name}"
        if download_from_gcs(ep.gcs_audio_path, local_file):
            downloads.append(("Final Episode", local_file))
    elif ep.final_audio_path:
        # Try R2/Cloudflare
        print(f"  ℹ️  Has R2 path: {ep.final_audio_path}")
        print("  ⚠️  R2 download not implemented - use Cloudflare dashboard")
    else:
        print("  ℹ️  No gcs_audio_path or final_audio_path")
    
    # Summary
    print("\n" + "=" * 80)
    print(f"✅ DOWNLOAD COMPLETE - {len(downloads)} files")
    print("=" * 80)
    
    if downloads:
        print("\n📂 Downloaded files:")
        for label, path in downloads:
            size_mb = path.stat().st_size / (1024 * 1024)
            print(f"   {label:20} → {path.name} ({size_mb:.2f} MB)")
        
        print(f"\n🎧 Open these files in Audacity/audio software to compare:")
        print(f"   cd {output_dir.absolute()}")
        print(f"   # Then open all .mp3 files in your audio editor")
        
        print("\n🔍 What to check:")
        print("   1. Does ORIGINAL have quality issues? → Problem is your recording")
        print("   2. Does CLEANED sound worse than ORIGINAL? → Problem is our clean_engine")
        print("   3. Does FINAL sound worse than CLEANED? → Problem is mixing/compression")
        print("   4. If CLEANED doesn't exist, clean_engine didn't run (expected for this episode)")
    else:
        print("\n⚠️  No files downloaded - check GCS paths in database")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
