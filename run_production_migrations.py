"""
Run RSS feed migrations on production PostgreSQL database.

This script connects directly to your Cloud SQL database and adds the required columns.
Run this ONCE to enable RSS feeds on production.

Usage:
    python run_production_migrations.py
"""

import os
import sys
from sqlalchemy import create_engine, text

def run_migrations():
    # Get database credentials from environment or prompt
    db_url = os.environ.get('DATABASE_URL')
    
    if not db_url:
        print("ERROR: DATABASE_URL environment variable not set")
        print("\nSet it like this:")
        print('$env:DATABASE_URL = "postgresql://user:password@/dbname?host=/cloudsql/project:region:instance"')
        print("\nOr use Cloud SQL Proxy:")
        print('$env:DATABASE_URL = "postgresql://user:password@localhost:5432/dbname"')
        sys.exit(1)
    
    print(f"Connecting to database...")
    engine = create_engine(db_url)
    
    # PostgreSQL migrations - add all missing columns
    episode_columns = [
        'ALTER TABLE episode ADD COLUMN IF NOT EXISTS gcs_audio_path VARCHAR',
        'ALTER TABLE episode ADD COLUMN IF NOT EXISTS gcs_cover_path VARCHAR',
        'ALTER TABLE episode ADD COLUMN IF NOT EXISTS has_numbering_conflict BOOLEAN DEFAULT FALSE',
        'ALTER TABLE episode ADD COLUMN IF NOT EXISTS audio_file_size INTEGER',
        'ALTER TABLE episode ADD COLUMN IF NOT EXISTS duration_ms INTEGER',
        'ALTER TABLE episode ADD COLUMN IF NOT EXISTS original_guid VARCHAR',
        'ALTER TABLE episode ADD COLUMN IF NOT EXISTS source_media_url VARCHAR',
        'ALTER TABLE episode ADD COLUMN IF NOT EXISTS source_published_at TIMESTAMP',
        'ALTER TABLE episode ADD COLUMN IF NOT EXISTS source_checksum VARCHAR',
    ]
    
    podcast_columns = [
        'ALTER TABLE podcast ADD COLUMN IF NOT EXISTS slug VARCHAR(100) UNIQUE',
    ]
    
    try:
        with engine.connect() as conn:
            print("\n📝 Adding episode columns...")
            for stmt in episode_columns:
                col_name = stmt.split('ADD COLUMN IF NOT EXISTS ')[1].split(' ')[0]
                print(f"  - {col_name}")
                conn.execute(text(stmt))
                conn.commit()
            
            print("\n📝 Adding podcast columns...")
            for stmt in podcast_columns:
                col_name = stmt.split('ADD COLUMN IF NOT EXISTS ')[1].split(' ')[0]
                print(f"  - {col_name}")
                conn.execute(text(stmt))
                conn.commit()
            
            print("\n✅ All columns added successfully!")
            
            # Now generate slugs for existing podcasts
            print("\n🔧 Generating slugs for existing podcasts...")
            
            # Get podcasts without slugs
            result = conn.execute(text("SELECT id, name FROM podcast WHERE slug IS NULL"))
            podcasts = result.fetchall()
            
            if not podcasts:
                print("  ✓ All podcasts already have slugs")
            else:
                import re
                for podcast_id, name in podcasts:
                    # Generate slug from name
                    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
                    
                    # Ensure uniqueness
                    base_slug = slug
                    counter = 1
                    while True:
                        check = conn.execute(text("SELECT id FROM podcast WHERE slug = :slug"), {"slug": slug})
                        if not check.fetchone():
                            break
                        slug = f"{base_slug}-{counter}"
                        counter += 1
                    
                    # Update podcast with slug
                    conn.execute(
                        text("UPDATE podcast SET slug = :slug WHERE id = :id"),
                        {"slug": slug, "id": podcast_id}
                    )
                    conn.commit()
                    print(f"  ✨ {name} → {slug}")
                
                print(f"\n  ✅ Generated {len(podcasts)} slug(s)")
            
            print("\n" + "="*60)
            print("✅ PRODUCTION MIGRATIONS COMPLETE!")
            print("="*60)
            print("\nYour RSS feeds are now ready:")
            print("  https://app.podcastplusplus.com/api/rss/cinema-irl/feed.xml")
            print("  https://app.podcastplusplus.com/api/rss/the-von-murder-show/feed.xml")
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    run_migrations()
