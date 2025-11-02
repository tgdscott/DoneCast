"""Migrate transcripts and cover images from GCS (or local GCS mirror) to Cloudflare R2.

This performs a real migration (no dry-run) and updates DB rows to reference r2:// paths.

It will:
 - Inspect `mediatranscript` rows whose `transcript_meta_json` contains `gs://`
 - Inspect `podcast.cover_path` and `podcast.remote_cover_url` for `gs://` references
 - Inspect `episode.gcs_cover_path` and `episode.cover_path` for `gs://` references
 - For each found GCS object, attempt to read from a local mirror directory if present
   (env var `GCS_MIRROR_DIR`) falling back to `infrastructure.gcs.download_bytes()`.
 - Upload the object bytes to R2 using `infrastructure.r2.upload_bytes()` into the
   configured `R2_BUCKET` with the same key path (everything after gs://<bucket>/).
 - Replace references to `gs://...` in DB rows with `r2://{R2_BUCKET}/{key}` and commit.

IMPORTANT:
 - This script makes irreversible DB updates. The repository already contains a DB dump
   and a local mirror of the GCS bucket under `C:\backups\podcastplus\gcs_ppp-media-us-west1`.
 - Do NOT run this unless you want the migration to be applied now (user requested "do it").
"""
import json
import logging
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv(Path(__file__).parent / '.env.local')

from infrastructure import gcs, r2

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('migrate_transcripts_and_covers')


def gs_parse(gs: str):
    """Return (bucket, key) for a gs:// URL or None."""
    if not gs or not gs.startswith('gs://'):
        return None
    rest = gs[5:]
    parts = rest.split('/', 1)
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def read_source_bytes(bucket: str, key: str, mirror_dir: Path | None = None) -> bytes | None:
    """Try to read object bytes from local mirror first, then GCS."""
    # Local mirror layout expected: <mirror_root>/<bucket>/<key>
    if mirror_dir:
        candidate = mirror_dir / bucket / key
        if candidate.exists():
            log.info('Reading from local mirror: %s', candidate)
            return candidate.read_bytes()

    # Fall back to GCS helper
    try:
        data = gcs.download_bytes(bucket, key)
        if data is not None:
            log.info('Read %d bytes from GCS gs://%s/%s', len(data), bucket, key)
            return data
    except Exception as e:
        log.warning('GCS download failed for gs://%s/%s: %s', bucket, key, e)

    return None


def upload_to_r2(r2_bucket: str, key: str, data: bytes) -> str | None:
    """Uploads bytes to R2, returns r2://... path on success."""
    ctype, _ = mimetypes.guess_type(key)
    content_type = ctype or 'application/octet-stream'
    try:
        url = r2.upload_bytes(r2_bucket, key, data, content_type=content_type)
        if url:
            return f'r2://{r2_bucket}/{key}'
    except Exception as e:
        log.error('Failed to upload to R2 %s: %s', key, e)
    return None


def replace_gs_strings_and_upload(obj: Any, mirror_dir: Path | None, r2_bucket: str) -> Any:
    """Walk a JSON-like structure, upload gs:// references to R2 and replace them.

    Returns the updated object.
    """
    if isinstance(obj, str):
        if obj.startswith('gs://'):
            parsed = gs_parse(obj)
            if not parsed:
                return obj
            bucket, key = parsed
            data = read_source_bytes(bucket, key, mirror_dir)
            if not data:
                log.error('Could not read source for %s', obj)
                return obj
            new_path = upload_to_r2(r2_bucket, key, data)
            if new_path:
                log.info('Migrated %s -> %s', obj, new_path)
                return new_path
            return obj
        return obj
    elif isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            out[k] = replace_gs_strings_and_upload(v, mirror_dir, r2_bucket)
        return out
    elif isinstance(obj, list):
        return [replace_gs_strings_and_upload(x, mirror_dir, r2_bucket) for x in obj]
    else:
        return obj


def migrate_media_transcripts(conn: Session, mirror_dir: Path | None, r2_bucket: str):
    log.info('Looking for MediaTranscript rows with gs:// references...')
    rows = conn.execute(text("SELECT id, filename, transcript_meta_json FROM mediatranscript WHERE transcript_meta_json ILIKE '%gs://%';")).fetchall()
    log.info('Found %d MediaTranscript rows to migrate', len(rows))
    migrated = 0
    for r in rows:
        id_, filename, meta_json = r
        try:
            meta = json.loads(meta_json or '{}')
        except Exception:
            log.exception('Invalid JSON for MediaTranscript id=%s', id_)
            continue

        new_meta = replace_gs_strings_and_upload(meta, mirror_dir, r2_bucket)
        if json.dumps(new_meta) != json.dumps(meta):
            conn.execute(text("UPDATE mediatranscript SET transcript_meta_json = :m, updated_at = now() WHERE id = :id"), {'m': json.dumps(new_meta), 'id': id_})
            migrated += 1
            log.info('Updated MediaTranscript %s', id_)

    log.info('MediaTranscript migration complete. Updated %d rows', migrated)


def migrate_podcast_covers(conn: Session, mirror_dir: Path | None, r2_bucket: str):
    log.info('Looking for Podcasts with gs:// covers...')
    rows = conn.execute(text("SELECT id, remote_cover_url, cover_path FROM podcast WHERE (remote_cover_url ILIKE '%gs://%' OR cover_path ILIKE '%gs://%');")).fetchall()
    log.info('Found %d podcasts to migrate', len(rows))
    migrated = 0
    for r in rows:
        id_, remote_cover_url, cover_path = r
        updated = False
        new_remote = remote_cover_url
        new_cover = cover_path

        for field, val in [('remote_cover_url', remote_cover_url), ('cover_path', cover_path)]:
            if val and isinstance(val, str) and val.startswith('gs://'):
                parsed = gs_parse(val)
                if not parsed:
                    continue
                bucket, key = parsed
                data = read_source_bytes(bucket, key, mirror_dir)
                if not data:
                    log.error('Could not read source for podcast %s field %s: %s', id_, field, val)
                    continue
                newpath = upload_to_r2(r2_bucket, key, data)
                if newpath:
                    if field == 'remote_cover_url':
                        new_remote = newpath
                    else:
                        new_cover = newpath
                    updated = True
                    log.info('Podcast %s: migrated %s -> %s', id_, val, newpath)

        if updated:
            conn.execute(text("UPDATE podcast SET remote_cover_url = :r, cover_path = :c WHERE id = :id"), {'r': new_remote, 'c': new_cover, 'id': id_})
            migrated += 1

    log.info('Podcast cover migration complete. Updated %d podcasts', migrated)


def migrate_episode_covers(conn: Session, mirror_dir: Path | None, r2_bucket: str):
    log.info('Looking for Episodes with gs:// covers...')
    rows = conn.execute(text("SELECT id, gcs_cover_path, cover_path FROM episode WHERE (gcs_cover_path ILIKE '%gs://%' OR cover_path ILIKE '%gs://%');")).fetchall()
    log.info('Found %d episodes to migrate', len(rows))
    migrated = 0
    for r in rows:
        id_, gcs_cover_path, cover_path = r
        updated = False
        new_gcs = gcs_cover_path
        new_cover = cover_path

        for field, val in [('gcs_cover_path', gcs_cover_path), ('cover_path', cover_path)]:
            if val and isinstance(val, str) and val.startswith('gs://'):
                parsed = gs_parse(val)
                if not parsed:
                    continue
                bucket, key = parsed
                data = read_source_bytes(bucket, key, mirror_dir)
                if not data:
                    log.error('Could not read source for episode %s field %s: %s', id_, field, val)
                    continue
                newpath = upload_to_r2(r2_bucket, key, data)
                if newpath:
                    if field == 'gcs_cover_path':
                        new_gcs = newpath
                    else:
                        new_cover = newpath
                    updated = True
                    log.info('Episode %s: migrated %s -> %s', id_, val, newpath)

        if updated:
            conn.execute(text("UPDATE episode SET gcs_cover_path = :g, cover_path = :c WHERE id = :id"), {'g': new_gcs, 'c': new_cover, 'id': id_})
            migrated += 1

    log.info('Episode cover migration complete. Updated %d episodes', migrated)


def main():
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        log.error('DATABASE_URL not set in .env.local')
        sys.exit(1)

    engine = create_engine(database_url)
    r2_bucket = os.getenv('R2_BUCKET') or os.getenv('R2_BUCKET', '').strip()
    if not r2_bucket:
        log.error('R2_BUCKET not configured in .env.local')
        sys.exit(1)

    mirror_env = os.getenv('GCS_MIRROR_DIR')
    mirror_dir = Path(mirror_env) if mirror_env else Path(r'C:\backups\podcastplus\gcs_ppp-media-us-west1')
    if not mirror_dir.exists():
        log.warning('Local GCS mirror not found at %s — script will attempt direct GCS downloads', mirror_dir)
        mirror_dir = None

    with Session(engine) as session:
        migrate_media_transcripts(session, mirror_dir, r2_bucket)
        migrate_podcast_covers(session, mirror_dir, r2_bucket)
        migrate_episode_covers(session, mirror_dir, r2_bucket)
        session.commit()

    log.info('Migration finished — review logs and run verification checks (e.g., sample r2.blob_exists)')


if __name__ == '__main__':
    main()
