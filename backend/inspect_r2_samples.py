"""Inspect samples of episodes stored on R2 and verify object existence.

Usage: python inspect_r2_samples.py

Prints up to 5 episodes whose gcs_audio_path starts with r2:// and checks whether
the referenced object exists in R2 using the project's infrastructure.r2.blob_exists().
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Ensure backend package imports work
sys.path.insert(0, str(Path(__file__).parent))

load_dotenv('.env.local')

db_url = os.getenv('DATABASE_URL')
if not db_url:
    print('DATABASE_URL not set (check backend/.env.local)')
    raise SystemExit(1)

engine = create_engine(db_url)

from infrastructure import r2

with engine.connect() as conn:
    rows = conn.execute(
        text("SELECT id, episode_number, title, gcs_audio_path FROM episode WHERE gcs_audio_path LIKE 'r2://%' ORDER BY created_at DESC LIMIT 5")
    ).fetchall()

    if not rows:
        print('No r2:// episodes found')
        raise SystemExit(0)

    for row in rows:
        id_, epnum, title, path = row
        print('\n---')
        print(f'id: {id_}  episode_number: {epnum}  title: {title}')
        print(f'path: {path}')

        # Try to parse r2://bucket/key
        if not path or not path.startswith('r2://'):
            print('  Not an r2 path, skipping existence check')
            continue

        parts = path[5:].split('/', 1)
        if len(parts) != 2:
            print('  Invalid r2 path format')
            continue

        bucket, key = parts
        exists = r2.blob_exists(bucket, key)
        print(f'  R2 object exists? {exists}')

print('\nDone')
