"""Comprehensive migration helper

Find remaining transcripts and cover images still stored in GCS (gs://...) or referenced
via remote URLs (Spreaker remote_cover_url). Upload the bytes to R2 and update DB fields
to use an r2:// path. Produce an audit CSV with before/after values.

Usage: run from backend/ directory:
    python migrate_remaining_transcripts_and_covers_to_r2.py

This script prefers the local GCS mirror found at
`C:\backups\podcastplus\gcs_ppp-media-us-west1` when downloading gs:// objects.

WARNING: This performs in-place DB updates (the user previously requested "do it for real").
Make sure you have the DB dump in backups before running.
"""

from __future__ import annotations

import csv
import json
import logging
import mimetypes
import os
import re
import sys
from pathlib import Path
from typing import Optional

from sqlmodel import SQLModel, Session, create_engine, select, text

# Import project infra helpers
try:
    from api.models.transcription import MediaTranscript
    from api.models.podcast import Podcast, Episode
except Exception:
    # If run from backend/ directly, adjust path
    sys.path.append(str(Path(__file__).resolve().parent))
    from api.models.transcription import MediaTranscript
    from api.models.podcast import Podcast, Episode

from infrastructure import r2 as r2lib
from infrastructure import gcs as gcslib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migrate_remaining")

# Config
DB_URL = os.getenv("DATABASE_URL")
R2_BUCKET = os.getenv("R2_BUCKET", "ppp-media")
LOCAL_GCS_MIRROR = Path(r"C:\backups\podcastplus\gcs_ppp-media-us-west1")
AUDIT_CSV = Path("migration_audit_transcripts_and_covers.csv")


def parse_gs_uri(uri: str) -> Optional[tuple[str, str]]:
    if not uri or not uri.startswith("gs://"):
        return None
    # gs://bucket/path/to/file
    parts = uri[5:].split("/", 1)
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def download_gs_bytes(bucket: str, key: str) -> Optional[bytes]:
    # Prefer local mirror if it exists
    local_candidate = LOCAL_GCS_MIRROR / bucket / Path(key)
    if local_candidate.exists():
        logger.info(f"Reading from local mirror: {local_candidate}")
        return local_candidate.read_bytes()

    logger.info(f"Downloading from GCS: gs://{bucket}/{key}")
    return gcslib.download_gcs_bytes(bucket, key)


def download_remote_url(url: str) -> Optional[bytes]:
    import requests

    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.content
        logger.warning(f"Remote URL fetch failed {url} -> {r.status_code}")
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch remote URL {url}: {e}")
        return None


def choose_mime_type(name: str, default: str = "application/octet-stream") -> str:
    t, _ = mimetypes.guess_type(name)
    return t or default


def r2_key_for_transcript(filename: str) -> str:
    base = Path(filename).name
    return f"transcripts/{base}"


def r2_key_for_podcast_cover(podcast_id: str, filename: str) -> str:
    base = Path(filename).name
    return f"covers/podcast/{podcast_id}/{base}"


def r2_key_for_episode_cover(episode_id: str, filename: str) -> str:
    base = Path(filename).name
    return f"covers/episode/{episode_id}/{base}"


def make_r2_path(bucket: str, key: str) -> str:
    return f"r2://{bucket}/{key}"


def audit_row(writer, table: str, row_id: str, column: str, before: str, after: str):
    writer.writerow({
        "table": table,
        "id": row_id,
        "column": column,
        "before": before or "",
        "after": after or "",
    })


def main() -> None:
    if not DB_URL:
        logger.error("DATABASE_URL is not set in environment")
        sys.exit(1)

    engine = create_engine(DB_URL)

    # Open audit CSV
    with AUDIT_CSV.open("w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["table", "id", "column", "before", "after"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        with Session(engine) as session:
            # 1) MediaTranscript entries where filename or transcript_meta_json references gs://
            logger.info("Scanning MediaTranscript for GCS references...")
            stmt = select(MediaTranscript)
            transcripts = session.exec(stmt).all()
            for t in transcripts:
                migrated = False
                # filename may itself be a gs:// URI
                if t.filename and t.filename.startswith("gs://"):
                    parsed = parse_gs_uri(t.filename)
                    if parsed:
                        bucket, key = parsed
                        data = download_gs_bytes(bucket, key)
                        if data:
                            key_r2 = r2_key_for_transcript(key)
                            mime = choose_mime_type(key)
                            url = r2lib.upload_bytes(R2_BUCKET, key_r2, data, content_type=mime)
                            if url:
                                before = t.filename
                                t.filename = make_r2_path(R2_BUCKET, key_r2)
                                session.add(t)
                                session.commit()
                                audit_row(writer, "mediatranscript", str(t.id), "filename", before, t.filename)
                                logger.info(f"Migrated MediaTranscript {t.id} filename -> {t.filename}")
                                migrated = True

                # transcript_meta_json may contain gcs:// references (naive substring search)
                try:
                    meta = t.transcript_meta_json or ""
                    if "gs://" in meta:
                        # Find all gs:// URIs in the JSON blob and migrate them
                        uris = re.findall(r"gs://[A-Za-z0-9_.\-\/]+", meta)
                        updated_meta = meta
                        for uri in sorted(set(uris)):
                            parsed = parse_gs_uri(uri)
                            if not parsed:
                                continue
                            bucket, key = parsed
                            data = download_gs_bytes(bucket, key)
                            if not data:
                                logger.warning(f"Could not download {uri} for MediaTranscript {t.id}")
                                continue
                            key_r2 = r2_key_for_transcript(key)
                            mime = choose_mime_type(key)
                            url = r2lib.upload_bytes(R2_BUCKET, key_r2, data, content_type=mime)
                            if url:
                                r2_uri = make_r2_path(R2_BUCKET, key_r2)
                                updated_meta = updated_meta.replace(uri, r2_uri)
                                logger.info(f"Replaced {uri} -> {r2_uri} in MediaTranscript {t.id}")
                                migrated = True

                        if migrated and updated_meta != meta:
                            before = t.transcript_meta_json
                            t.transcript_meta_json = updated_meta
                            session.add(t)
                            session.commit()
                            audit_row(writer, "mediatranscript", str(t.id), "transcript_meta_json", before, t.transcript_meta_json)

                except Exception as e:
                    logger.exception(f"Error processing MediaTranscript {t.id}: {e}")

            # 2) Podcasts: cover_path gs:// or remote_cover_url -> fetch & upload
            logger.info("Scanning Podcast covers...")
            podcasts = session.exec(select(Podcast)).all()
            for p in podcasts:
                # Prefer migrating cover_path if it's gs://
                try:
                    if p.cover_path and p.cover_path.startswith("gs://"):
                        parsed = parse_gs_uri(p.cover_path)
                        if parsed:
                            bucket, key = parsed
                            data = download_gs_bytes(bucket, key)
                            if data:
                                key_r2 = r2_key_for_podcast_cover(str(p.id), key)
                                mime = choose_mime_type(key)
                                url = r2lib.upload_bytes(R2_BUCKET, key_r2, data, content_type=mime)
                                if url:
                                    before = p.cover_path
                                    p.cover_path = make_r2_path(R2_BUCKET, key_r2)
                                    session.add(p)
                                    session.commit()
                                    audit_row(writer, "podcast", str(p.id), "cover_path", before, p.cover_path)
                                    logger.info(f"Migrated podcast {p.id} cover_path -> {p.cover_path}")

                    # If no cover_path but remote_cover_url exists (e.g., Spreaker CDN), fetch and upload
                    if (not p.cover_path or p.cover_path.startswith("http")) and p.remote_cover_url:
                        # If remote_cover_url already points to r2:// leave it
                        if p.remote_cover_url.startswith("r2://"):
                            continue
                        data = download_remote_url(p.remote_cover_url)
                        if data:
                            # derive filename from URL
                            fname = Path(p.remote_cover_url.split("?")[0]).name or f"podcast_{p.id}_cover.jpg"
                            key_r2 = r2_key_for_podcast_cover(str(p.id), fname)
                            mime = choose_mime_type(fname)
                            url = r2lib.upload_bytes(R2_BUCKET, key_r2, data, content_type=mime)
                            if url:
                                before = p.cover_path
                                p.cover_path = make_r2_path(R2_BUCKET, key_r2)
                                session.add(p)
                                session.commit()
                                audit_row(writer, "podcast", str(p.id), "cover_path", before, p.cover_path)
                                logger.info(f"Fetched remote_cover_url and migrated podcast {p.id} cover -> {p.cover_path}")

                except Exception as e:
                    logger.exception(f"Error processing Podcast {p.id}: {e}")

            # 3) Episodes: gcs_cover_path or cover_path or remote_cover_url
            logger.info("Scanning Episode covers (gcs_cover_path, cover_path, remote_cover_url)...")
            episodes = session.exec(select(Episode)).all()
            for ep in episodes:
                try:
                    # gcs_cover_path preferred
                    if getattr(ep, "gcs_cover_path", None) and str(ep.gcs_cover_path).startswith("gs://"):
                        parsed = parse_gs_uri(ep.gcs_cover_path)
                        if parsed:
                            bucket, key = parsed
                            data = download_gs_bytes(bucket, key)
                            if data:
                                key_r2 = r2_key_for_episode_cover(str(ep.id), key)
                                mime = choose_mime_type(key)
                                url = r2lib.upload_bytes(R2_BUCKET, key_r2, data, content_type=mime)
                                if url:
                                    before = ep.gcs_cover_path
                                    ep.gcs_cover_path = make_r2_path(R2_BUCKET, key_r2)
                                    # also update cover_path to the r2 path for UI fallback
                                    before_cov = ep.cover_path
                                    ep.cover_path = ep.gcs_cover_path
                                    session.add(ep)
                                    session.commit()
                                    audit_row(writer, "episode", str(ep.id), "gcs_cover_path", before, ep.gcs_cover_path)
                                    audit_row(writer, "episode", str(ep.id), "cover_path", before_cov, ep.cover_path)
                                    logger.info(f"Migrated episode {ep.id} gcs_cover_path -> {ep.gcs_cover_path}")

                    # fallback: cover_path that is gs://
                    elif ep.cover_path and ep.cover_path.startswith("gs://"):
                        parsed = parse_gs_uri(ep.cover_path)
                        if parsed:
                            bucket, key = parsed
                            data = download_gs_bytes(bucket, key)
                            if data:
                                key_r2 = r2_key_for_episode_cover(str(ep.id), key)
                                mime = choose_mime_type(key)
                                url = r2lib.upload_bytes(R2_BUCKET, key_r2, data, content_type=mime)
                                if url:
                                    before = ep.cover_path
                                    ep.cover_path = make_r2_path(R2_BUCKET, key_r2)
                                    session.add(ep)
                                    session.commit()
                                    audit_row(writer, "episode", str(ep.id), "cover_path", before, ep.cover_path)
                                    logger.info(f"Migrated episode {ep.id} cover_path -> {ep.cover_path}")

                    # fallback: episode.remote_cover_url (Spreaker)
                    elif ep.remote_cover_url and not ep.remote_cover_url.startswith("r2://"):
                        data = download_remote_url(ep.remote_cover_url)
                        if data:
                            fname = Path(ep.remote_cover_url.split("?")[0]).name or f"episode_{ep.id}_cover.jpg"
                            key_r2 = r2_key_for_episode_cover(str(ep.id), fname)
                            mime = choose_mime_type(fname)
                            url = r2lib.upload_bytes(R2_BUCKET, key_r2, data, content_type=mime)
                            if url:
                                before = ep.cover_path
                                ep.cover_path = make_r2_path(R2_BUCKET, key_r2)
                                session.add(ep)
                                session.commit()
                                audit_row(writer, "episode", str(ep.id), "cover_path", before, ep.cover_path)
                                logger.info(f"Fetched and migrated episode {ep.id} remote_cover_url -> {ep.cover_path}")

                except Exception as e:
                    logger.exception(f"Error processing Episode {ep.id}: {e}")

    logger.info(f"Migration finished, audit written to {AUDIT_CSV}")


if __name__ == "__main__":
    main()
