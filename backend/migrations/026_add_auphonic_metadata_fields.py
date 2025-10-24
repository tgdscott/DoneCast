"""Add Auphonic metadata fields to Episode table.

Adds columns for AI-generated metadata from Auphonic Whisper ASR:
- brief_summary: Short 1-2 paragraph summary (for show notes)
- long_summary: Detailed multi-paragraph summary (for marketing)
- episode_tags: JSON array of AI-extracted keywords (for SEO)
- episode_chapters: JSON array of chapter markers with timestamps (for podcast apps)

Migration: 026
Created: 2025-10-21
"""

from sqlalchemy import text


def migrate(engine):
    """Add Auphonic metadata columns to episode table."""
    with engine.begin() as conn:
        # Check if columns already exist (idempotent)
        inspector = __import__('sqlalchemy').inspect(engine)
        existing_columns = {col['name'] for col in inspector.get_columns('episode')}
        
        migrations_needed = []
        
        if 'brief_summary' not in existing_columns:
            migrations_needed.append(
                "ALTER TABLE episode ADD COLUMN brief_summary TEXT DEFAULT NULL"
            )
        
        if 'long_summary' not in existing_columns:
            migrations_needed.append(
                "ALTER TABLE episode ADD COLUMN long_summary TEXT DEFAULT NULL"
            )
        
        if 'episode_tags' not in existing_columns:
            migrations_needed.append(
                "ALTER TABLE episode ADD COLUMN episode_tags TEXT DEFAULT '[]'"
            )
        
        if 'episode_chapters' not in existing_columns:
            migrations_needed.append(
                "ALTER TABLE episode ADD COLUMN episode_chapters TEXT DEFAULT '[]'"
            )
        
        if migrations_needed:
            for sql in migrations_needed:
                conn.execute(text(sql))
            print(f"✅ Migration 026: Added {len(migrations_needed)} Auphonic metadata columns")
        else:
            print("✅ Migration 026: All Auphonic metadata columns already exist")


def rollback(engine):
    """Remove Auphonic metadata columns (for testing only)."""
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE episode DROP COLUMN IF EXISTS brief_summary"))
        conn.execute(text("ALTER TABLE episode DROP COLUMN IF EXISTS long_summary"))
        conn.execute(text("ALTER TABLE episode DROP COLUMN IF EXISTS episode_tags"))
        conn.execute(text("ALTER TABLE episode DROP COLUMN IF EXISTS episode_chapters"))
        print("✅ Migration 026 rolled back: Auphonic metadata columns removed")
