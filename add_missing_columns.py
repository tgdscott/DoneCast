"""
Add all missing columns to the episode table that are in the model but not in the database.
Run this once to sync the database schema with the Episode model.
"""
import sqlite3
import sys
from pathlib import Path

def add_missing_columns():
    db_path = Path(__file__).parent / "database.db"
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get current columns
    cursor.execute("PRAGMA table_info(episode)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    print(f"✓ Found {len(existing_columns)} existing columns in episode table")
    
    # Define all columns that should exist (from Episode model)
    required_columns = {
        'gcs_audio_path': 'VARCHAR',
        'gcs_cover_path': 'VARCHAR',
        'has_numbering_conflict': 'BOOLEAN DEFAULT FALSE',
        'audio_file_size': 'INTEGER',
        'duration_ms': 'INTEGER',
        'original_guid': 'VARCHAR',
        'source_media_url': 'VARCHAR',
        'source_published_at': 'DATETIME',
        'source_checksum': 'VARCHAR',
    }
    
    # Find missing columns
    missing = {col: dtype for col, dtype in required_columns.items() if col not in existing_columns}
    
    if not missing:
        print("✓ All required columns already exist!")
        return
    
    print(f"\n📝 Adding {len(missing)} missing columns:")
    for col, dtype in missing.items():
        print(f"  - {col} ({dtype})")
        try:
            cursor.execute(f"ALTER TABLE episode ADD COLUMN {col} {dtype}")
            print(f"    ✓ Added {col}")
        except sqlite3.OperationalError as e:
            print(f"    ⚠️ {col}: {e}")
    
    conn.commit()
    
    # Verify all columns now exist
    cursor.execute("PRAGMA table_info(episode)")
    final_columns = {row[1] for row in cursor.fetchall()}
    still_missing = set(required_columns.keys()) - final_columns
    
    if still_missing:
        print(f"\n❌ Still missing: {still_missing}")
        sys.exit(1)
    else:
        print(f"\n✅ Success! Episode table now has {len(final_columns)} columns")
    
    conn.close()

if __name__ == "__main__":
    add_missing_columns()
