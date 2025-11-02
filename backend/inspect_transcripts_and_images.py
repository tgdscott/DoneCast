"""Inspect where transcripts and cover images are stored (R2 vs GCS).

Usage: python inspect_transcripts_and_images.py

Prints counts and up to 5 sample rows for:
 - MediaTranscript entries referencing r2:// or gs://
 - Podcast cover fields referencing r2:// or gs://
 - Episode cover fields referencing r2:// or gs://
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv('.env.local')

db_url = os.getenv('DATABASE_URL')
if not db_url:
    print('DATABASE_URL not set in backend/.env.local')
    raise SystemExit(1)

engine = create_engine(db_url)

with engine.connect() as conn:
    # Find transcript-related tables first to avoid undefined-table errors
    print('--- Looking for transcript-related tables in the database ---')
    tbls = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name ILIKE '%transcript%';")).fetchall()
    tbl_names = [t[0] for t in tbls]
    print('Found transcript tables:', tbl_names)

    # If a media_transcript-like table exists, search it for r2/gs refs
    candidate = None
    for name in tbl_names:
        if 'media' in name:
            candidate = name
            break

    if candidate:
        print(f"--- Inspecting table: {candidate} ---")
        res = conn.execute(text(f"SELECT COUNT(*) FROM {candidate} WHERE transcript_meta_json ILIKE '%r2://%';"))
        r2_count = res.scalar()
        res = conn.execute(text(f"SELECT COUNT(*) FROM {candidate} WHERE transcript_meta_json ILIKE '%gs://%';"))
        gcs_count = res.scalar()
        print(f'MediaTranscript referencing r2:// -> {r2_count}')
        print(f'MediaTranscript referencing gs:// -> {gcs_count}')
        print('\nSamples (r2):')
        rows = conn.execute(text(f"SELECT id, filename, transcript_meta_json FROM {candidate} WHERE transcript_meta_json ILIKE '%r2://%' ORDER BY updated_at DESC LIMIT 5")).fetchall()
        for r in rows:
            print('-', r[0], r[1], (str(r[2])[:200] + '...') if r[2] and len(str(r[2]))>200 else r[2])
    else:
        print('No media-transcript-like table found; skipping MediaTranscript checks')

    print('\n--- Podcasts cover fields ---')
    res = conn.execute(text("SELECT COUNT(*) FROM podcast WHERE remote_cover_url ILIKE '%r2://%' OR remote_cover_url ILIKE '%gs://%' OR cover_path ILIKE '%r2://%' OR cover_path ILIKE '%gs://%';"))
    pod_count = res.scalar()
    print(f'Podcasts with cover fields pointing to r2/gs: {pod_count}')
    rows = conn.execute(text("SELECT id, name, slug, remote_cover_url, cover_path FROM podcast WHERE remote_cover_url ILIKE '%r2://%' OR remote_cover_url ILIKE '%gs://%' OR cover_path ILIKE '%r2://%' OR cover_path ILIKE '%gs://%' LIMIT 5")).fetchall()
    for r in rows:
        print('-', r.id, r.name, r.slug)
        print('  remote_cover_url:', r.remote_cover_url)
        print('  cover_path:', r.cover_path)

    print('\n--- Episodes cover fields ---')
    res = conn.execute(text("SELECT COUNT(*) FROM episode WHERE gcs_cover_path ILIKE '%r2://%' OR gcs_cover_path ILIKE '%gs://%' OR cover_path ILIKE '%r2://%' OR cover_path ILIKE '%gs://%';"))
    ep_count = res.scalar()
    print(f'Episodes with cover fields pointing to r2/gs: {ep_count}')
    rows = conn.execute(text("SELECT id, title, episode_number, gcs_cover_path, cover_path FROM episode WHERE gcs_cover_path ILIKE '%r2://%' OR gcs_cover_path ILIKE '%gs://%' OR cover_path ILIKE '%r2://%' OR cover_path ILIKE '%gs://%' ORDER BY created_at DESC LIMIT 5")).fetchall()
    for r in rows:
        print('-', r.id, r.episode_number, r.title)
        print('  gcs_cover_path:', r.gcs_cover_path)
        print('  cover_path:', r.cover_path)

print('\nDone')
