#!/usr/bin/env python3
"""
Standalone script to backfill transcript words into MediaTranscript table.

This script can be run manually to test the migration or backfill transcripts
outside of the normal startup migration flow.

Usage:
    python backend/scripts/backfill_transcript_words.py
"""

import os
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# Load environment variables
from dotenv import load_dotenv
env_path = backend_dir.parent / ".env.local"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

# Now import after env is loaded
from migrations.one_time_migrations import _backfill_transcript_words

if __name__ == "__main__":
    print("=" * 80)
    print("Transcript Words Backfill Migration")
    print("=" * 80)
    print()
    print("This script will:")
    print("  1. Find all MediaTranscript records without words in transcript_meta_json")
    print("  2. Download transcript JSON files from GCS")
    print("  3. Store words directly in the database")
    print()
    print("Starting migration...")
    print()
    
    success = _backfill_transcript_words()
    
    print()
    print("=" * 80)
    if success:
        print("✅ Migration completed successfully!")
    else:
        print("❌ Migration completed with errors (check logs above)")
    print("=" * 80)
    
    sys.exit(0 if success else 1)




