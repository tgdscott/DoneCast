#!/usr/bin/env python3
"""Check if a MediaItem has a GCS URL stored in the database."""

import os
import sys
from pathlib import Path

# Add backend to path
backend_root = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_root))

from sqlmodel import Session, select
from api.core.database import get_engine
from api.models.podcast import MediaItem, MediaCategory
from uuid import UUID

def check_media_item(filename: str):
    """Check if MediaItem has GCS URL."""
    engine = get_engine()
    with Session(engine) as session:
        # Find MediaItem by filename
        query = select(MediaItem).where(MediaItem.filename == filename)
        items = list(session.exec(query).all())
        
        if not items:
            print(f"❌ No MediaItem found with filename: {filename}")
            return
        
        for item in items:
            print(f"\n✅ Found MediaItem:")
            print(f"  ID: {item.id}")
            print(f"  Filename: {item.filename}")
            print(f"  Filename starts with gs://: {item.filename.startswith('gs://') if item.filename else False}")
            print(f"  Filename starts with http: {item.filename.startswith('http') if item.filename else False}")
            print(f"  Category: {item.category}")
            print(f"  User ID: {item.user_id}")
            print(f"  Filesize: {item.filesize}")
            print(f"  Created: {getattr(item, 'created_at', 'N/A')}")
            
            if item.filename and not (item.filename.startswith("gs://") or item.filename.startswith("http")):
                print(f"\n⚠️  WARNING: MediaItem does NOT have a GCS URL!")
                print(f"   This file was likely uploaded before the GCS URL storage feature was implemented.")
                print(f"   Solution: Upload a NEW file - it will have a GCS URL stored in the database.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_media_item_gcs_url.py <filename>")
        print("Example: python check_media_item_gcs_url.py 'b6d5f77e699e444ba31ae1b4cb15feb4_7e341a63ae64460e84228febd46a718c_47Intro.mp3'")
        sys.exit(1)
    
    filename = sys.argv[1]
    check_media_item(filename)

