"""
Migration: Add is_global and owner_id fields to MusicAsset

Date: 2025-10-12
"""

import os
import sys
from pathlib import Path

# Add backend to path for imports
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from sqlalchemy import text
from api.core.database import engine


def migrate():
    """Add is_global and owner_id columns to musicasset table"""
    
    with engine.begin() as conn:
        # Check if columns already exist
        result = conn.execute(text("""
            SELECT COUNT(*) as count
            FROM pragma_table_info('musicasset')
            WHERE name IN ('is_global', 'owner_id')
        """))
        existing_count = result.scalar()
        
        if existing_count == 2:
            print("✓ Columns already exist, skipping migration")
            return
        
        print("Adding is_global and owner_id columns to musicasset table...")
        
        # Add is_global column (default False for existing records)
        if existing_count == 0:
            conn.execute(text("""
                ALTER TABLE musicasset 
                ADD COLUMN is_global BOOLEAN DEFAULT 0 NOT NULL
            """))
            print("  ✓ Added is_global column")
        
        # Add owner_id column (nullable, foreign key to user.id)
        try:
            conn.execute(text("""
                ALTER TABLE musicasset 
                ADD COLUMN owner_id VARCHAR(36) REFERENCES user(id)
            """))
            print("  ✓ Added owner_id column")
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                raise
            print("  ✓ owner_id column already exists")
        
        # Create index on owner_id for faster lookups
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_musicasset_owner_id 
                ON musicasset(owner_id)
            """))
            print("  ✓ Created index on owner_id")
        except Exception as e:
            print(f"  ⚠ Index creation skipped: {e}")
        
        # Mark all existing assets as global (admin-uploaded)
        result = conn.execute(text("""
            UPDATE musicasset 
            SET is_global = 1
            WHERE owner_id IS NULL
        """))
        count = result.rowcount
        print(f"  ✓ Marked {count} existing assets as global")
        
        print("\n✅ Migration completed successfully!")


def rollback():
    """Remove the added columns (for testing/development only)"""
    print("⚠️  Warning: Rolling back migration will remove is_global and owner_id columns")
    
    with engine.begin() as conn:
        # SQLite doesn't support DROP COLUMN directly, so we need to recreate the table
        # For now, just warn - in production, use proper migration tools
        print("Rollback not implemented for SQLite. Use proper migration tool for production.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Migrate MusicAsset table")
    parser.add_argument("--rollback", action="store_true", help="Rollback the migration")
    args = parser.parse_args()
    
    if args.rollback:
        rollback()
    else:
        migrate()
