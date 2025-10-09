"""
Manually run RSS feed migrations (columns + slugs).

Run this if you want to test migrations without starting the full API.
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

import re
from sqlmodel import Session, select
from api.models.podcast import Podcast, Episode
from api.core.database import engine

print("\n" + "="*60)
print("RSS FEED MIGRATIONS")
print("="*60 + "\n")

# Check/add episode columns
print("📝 Checking episode table...")
with engine.connect() as conn:
    res = conn.exec_driver_sql("PRAGMA table_info(episode)")
    cols = {row[1] for row in res}
    
    added = []
    if "audio_file_size" not in cols:
        conn.exec_driver_sql("ALTER TABLE episode ADD COLUMN audio_file_size INTEGER")
        added.append("audio_file_size")
    
    if "duration_ms" not in cols:
        conn.exec_driver_sql("ALTER TABLE episode ADD COLUMN duration_ms INTEGER")
        added.append("duration_ms")
    
    if added:
        print(f"  ✅ Added: {', '.join(added)}")
    else:
        print(f"  ✓ Already has required columns")

# Check/add podcast slug column
print("\n📝 Checking podcast table...")
with engine.connect() as conn:
    res = conn.exec_driver_sql("PRAGMA table_info(podcast)")
    cols = {row[1] for row in res}
    
    if "slug" not in cols:
        # SQLite doesn't support adding UNIQUE columns directly
        conn.exec_driver_sql("ALTER TABLE podcast ADD COLUMN slug VARCHAR(100)")
        print(f"  ✅ Added: slug (uniqueness enforced at application level)")
    else:
        print(f"  ✓ Already has slug column")

# Generate slugs for podcasts without them
print("\n🔧 Generating slugs...")
with Session(engine) as session:
    podcasts = session.exec(select(Podcast)).all()
    generated = 0
    
    for podcast in podcasts:
        if not podcast.slug:
            # Generate slug from name
            slug = re.sub(r'[^a-z0-9]+', '-', podcast.name.lower()).strip('-')
            
            # Ensure uniqueness
            base_slug = slug
            counter = 1
            while session.exec(select(Podcast).where(Podcast.slug == slug)).first():
                slug = f"{base_slug}-{counter}"
                counter += 1
            
            podcast.slug = slug
            session.add(podcast)
            generated += 1
            print(f"  ✨ {podcast.name} → {slug}")
    
    if generated > 0:
        session.commit()
        print(f"\n  ✅ Generated {generated} slug(s)")
    else:
        print(f"  ✓ All podcasts already have slugs")

print("\n" + "="*60)
print("✅ MIGRATIONS COMPLETE!")
print("="*60)
print("\nYour RSS feed URLs are now:")
with Session(engine) as session:
    podcasts = session.exec(select(Podcast)).all()
    for podcast in podcasts:
        if podcast.slug:
            print(f"\n  📻 {podcast.name}")
            print(f"     http://localhost:8000/api/rss/{podcast.slug}/feed.xml")
print("\n")
