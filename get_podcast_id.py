"""
Quick helper to find your podcast ID for testing the RSS feed.
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from sqlmodel import Session, select
from api.models.podcast import Podcast
from api.core.database import engine

print("\n" + "="*60)
print("YOUR PODCAST IDs")
print("="*60 + "\n")

with Session(engine) as session:
    podcasts = session.exec(select(Podcast)).all()
    
    if not podcasts:
        print("❌ No podcasts found in database.")
        print("\nCreate a podcast first through your app!\n")
        sys.exit(1)
    
    for podcast in podcasts:
        print(f"Podcast: {podcast.name}")
        print(f"ID:      {podcast.id}")
        
        if podcast.slug:
            print(f"Slug:    {podcast.slug} ✨")
            print(f"RSS URL: http://localhost:8000/api/rss/{podcast.slug}/feed.xml 👈 Use this!")
            print(f"         http://localhost:8000/api/rss/{podcast.id}/feed.xml (also works)")
        else:
            print(f"Slug:    (will be auto-generated on next API start)")
            print(f"RSS URL: http://localhost:8000/api/rss/{podcast.id}/feed.xml")
        
        print("-" * 60)
    
    print(f"\nTotal: {len(podcasts)} podcast(s) found")
    print("\n💡 Friendly URLs are much nicer: /rss/my-awesome-podcast/feed.xml")
    print("   Copy the RSS URL above and paste it in your browser!")
    print("   Or validate it at: https://castfeedvalidator.com/\n")
