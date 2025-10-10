from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta, timezone

from sqlmodel import select
from sqlalchemy import inspect, text

from api.core.database import engine, create_db_and_tables, session_scope
from api.core.config import settings
from api.models.podcast import Episode, Podcast
from api.core.logging import get_logger

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

log: logging.Logger = get_logger("api.startup_tasks")

# --- Environment-driven startup behavior ------------------------------------
_HEAVY_FLAG = (os.getenv("STARTUP_HEAVY_TASKS") or "off").strip().lower()
# Modes: off, on, auto. auto => enable in non-production envs only.
_APP_ENV = (os.getenv("APP_ENV") or os.getenv("ENV") or "dev").lower()
if _HEAVY_FLAG == "auto":
    _HEAVY_ENABLED = _APP_ENV not in {"prod", "production", "staging", "stage"}
else:
    _HEAVY_ENABLED = _HEAVY_FLAG in {"1", "true", "yes", "on"}

try:
    _ROW_LIMIT = int(os.getenv("STARTUP_ROW_LIMIT", "1000"))
    if _ROW_LIMIT <= 0:
        _ROW_LIMIT = 1000
except Exception:
    _ROW_LIMIT = 1000

def _timing(label: str):
    """Context manager for timing blocks with consistent logging."""
    from contextlib import contextmanager
    import time as _t
    @contextmanager
    def _cm():
        start = _t.time()
        try:
            yield
        finally:
            dur = _t.time() - start
            log.info("[startup] %s completed in %.2fs", label, dur)
    return _cm()


def _normalize_episode_paths(limit: int | None = None) -> None:
    """Ensure Episode paths store only basenames for local files."""
    try:
        with session_scope() as session:
            _limit = limit or _ROW_LIMIT
            q = select(Episode).limit(_limit)
            eps = session.exec(q).all()
            changed = 0
            for e in eps:
                c = False
                if e.final_audio_path:
                    base = os.path.basename(str(e.final_audio_path))
                    if base != e.final_audio_path:
                        e.final_audio_path = base
                        c = True
                if e.cover_path and not str(e.cover_path).lower().startswith(("http://", "https://")):
                    base = os.path.basename(str(e.cover_path))
                    if base != e.cover_path:
                        e.cover_path = base
                        c = True
                if c:
                    session.add(e)
                    changed += 1
            if changed:
                session.commit()
    except Exception as e:
        log.warning("_normalize_episode_paths failed: %s", e)


def _normalize_podcast_covers(limit: int | None = None) -> None:
    """Ensure Podcast.cover_path stores only a basename if it's a local path."""
    try:
        with session_scope() as session:
            _limit = limit or _ROW_LIMIT
            q = select(Podcast).limit(_limit)
            pods = session.exec(q).all()
            changed = 0
            for p in pods:
                try:
                    if p.cover_path and not str(p.cover_path).lower().startswith(("http://", "https://")):
                        base = os.path.basename(str(p.cover_path))
                        if base != p.cover_path:
                            p.cover_path = base
                            session.add(p)
                            changed += 1
                except Exception as e:
                    log.debug("skip normalize podcast cover for id=%s: %s", getattr(p, "id", "?"), e)
            if changed:
                session.commit()
    except Exception as e:
        log.warning("_normalize_podcast_covers failed: %s", e)


def _ensure_user_subscription_column() -> None:
    """Idempotent additive migrations for SQLite tables and columns we use."""
    if engine.url.get_backend_name() != "sqlite":
        return
    try:
        with engine.connect() as conn:
            # --- user table
            res = conn.exec_driver_sql("PRAGMA table_info(user)")
            cols = [row[1] for row in res]

            if "audio_cleanup_settings_json" not in cols:
                try:
                    conn.exec_driver_sql("ALTER TABLE user ADD COLUMN audio_cleanup_settings_json TEXT NULL")
                    log.info("[migrate] Added user.audio_cleanup_settings_json")
                except Exception as ae:
                    log.info("[migrate] Could not add audio_cleanup_settings_json: %s", ae)

            if "subscription_expires_at" not in cols:
                conn.exec_driver_sql("ALTER TABLE user ADD COLUMN subscription_expires_at TIMESTAMP NULL")
                log.info("[migrate] Added user.subscription_expires_at")

            if "timezone" not in cols:
                conn.exec_driver_sql("ALTER TABLE user ADD COLUMN timezone VARCHAR(64) NULL DEFAULT 'UTC'")
                log.info("[migrate] Added user.timezone")

            if "stripe_customer_id" not in cols:
                conn.exec_driver_sql("ALTER TABLE user ADD COLUMN stripe_customer_id VARCHAR NULL")
                log.info("[migrate] Added user.stripe_customer_id")

            if "first_name" not in cols:
                try:
                    conn.exec_driver_sql("ALTER TABLE user ADD COLUMN first_name VARCHAR(80) NULL")
                    log.info("[migrate] Added user.first_name")
                except Exception as ne:
                    log.info("[migrate] Could not add first_name: %s", ne)

            if "last_name" not in cols:
                try:
                    conn.exec_driver_sql("ALTER TABLE user ADD COLUMN last_name VARCHAR(120) NULL")
                    log.info("[migrate] Added user.last_name")
                except Exception as ne:
                    log.info("[migrate] Could not add last_name: %s", ne)

            if "last_login" not in cols:
                try:
                    conn.exec_driver_sql("ALTER TABLE user ADD COLUMN last_login TIMESTAMP NULL")
                    log.info("[migrate] Added user.last_login")
                except Exception as le:
                    log.info("[migrate] Could not add last_login: %s", le)

            # --- episode table
            res_ep = conn.exec_driver_sql("PRAGMA table_info(episode)")
            cols_ep = [row[1] for row in res_ep]

            if "publish_at_local" not in cols_ep:
                conn.exec_driver_sql("ALTER TABLE episode ADD COLUMN publish_at_local VARCHAR(128) NULL")
                log.info("[migrate] Added episode.publish_at_local")

            if "meta_json" not in cols_ep:
                try:
                    conn.exec_driver_sql("ALTER TABLE episode ADD COLUMN meta_json TEXT NULL")
                    log.info("[migrate] Added episode.meta_json")
                except Exception as me:
                    log.info("[migrate] Could not add meta_json: %s", me)

            if "working_audio_name" not in cols_ep:
                try:
                    conn.exec_driver_sql("ALTER TABLE episode ADD COLUMN working_audio_name VARCHAR NULL")
                    log.info("[migrate] Added episode.working_audio_name")
                except Exception as we:
                    log.info("[migrate] Could not add working_audio_name: %s", we)

            if "remote_cover_url" not in cols_ep:
                conn.exec_driver_sql("ALTER TABLE episode ADD COLUMN remote_cover_url VARCHAR NULL")
                log.info("[migrate] Added episode.remote_cover_url")

            if "gcs_audio_path" not in cols_ep:
                conn.exec_driver_sql("ALTER TABLE episode ADD COLUMN gcs_audio_path VARCHAR NULL")
                log.info("[migrate] Added episode.gcs_audio_path")

            if "gcs_cover_path" not in cols_ep:
                conn.exec_driver_sql("ALTER TABLE episode ADD COLUMN gcs_cover_path VARCHAR NULL")
                log.info("[migrate] Added episode.gcs_cover_path")

            if "has_numbering_conflict" not in cols_ep:
                conn.exec_driver_sql("ALTER TABLE episode ADD COLUMN has_numbering_conflict BOOLEAN DEFAULT FALSE")
                log.info("[migrate] Added episode.has_numbering_conflict")

            if "created_at" not in cols_ep:
                conn.exec_driver_sql("ALTER TABLE episode ADD COLUMN created_at TIMESTAMP NULL")
                log.info("[migrate] Added episode.created_at")

            # Episode provenance columns
            try:
                if "original_guid" not in cols_ep:
                    conn.exec_driver_sql("ALTER TABLE episode ADD COLUMN original_guid VARCHAR NULL")
                    log.info("[migrate] Added episode.original_guid")
                if "source_media_url" not in cols_ep:
                    conn.exec_driver_sql("ALTER TABLE episode ADD COLUMN source_media_url VARCHAR NULL")
                    log.info("[migrate] Added episode.source_media_url")
                if "source_published_at" not in cols_ep:
                    conn.exec_driver_sql("ALTER TABLE episode ADD COLUMN source_published_at TIMESTAMP NULL")
                    log.info("[migrate] Added episode.source_published_at")
                if "source_checksum" not in cols_ep:
                    conn.exec_driver_sql("ALTER TABLE episode ADD COLUMN source_checksum VARCHAR NULL")
                    log.info("[migrate] Added episode.source_checksum")
            except Exception as pe:
                log.info("[migrate] Could not alter episode provenance columns: %s", pe)

            # --- podcast table
            res_pod = conn.exec_driver_sql("PRAGMA table_info(podcast)")
            cols_pod = [row[1] for row in res_pod]

            if "contact_email" not in cols_pod:
                conn.exec_driver_sql("ALTER TABLE podcast ADD COLUMN contact_email VARCHAR NULL")
                log.info("[migrate] Added podcast.contact_email")

            if "rss_url_locked" not in cols_pod:
                try:
                    conn.exec_driver_sql("ALTER TABLE podcast ADD COLUMN rss_url_locked VARCHAR NULL")
                    log.info("[migrate] Added podcast.rss_url_locked")
                except Exception as ie:
                    log.info("[migrate] Could not add rss_url_locked: %s", ie)

            if "remote_cover_url" not in cols_pod:
                try:
                    conn.exec_driver_sql("ALTER TABLE podcast ADD COLUMN remote_cover_url VARCHAR NULL")
                    log.info("[migrate] Added podcast.remote_cover_url")
                except Exception as re:
                    log.info("[migrate] Could not add remote_cover_url: %s", re)

            for cat_col in ("category_id", "category_2_id", "category_3_id"):
                if cat_col not in cols_pod:
                    try:
                        conn.exec_driver_sql(f"ALTER TABLE podcast ADD COLUMN {cat_col} INTEGER NULL")
                        log.info("[migrate] Added podcast.%s", cat_col)
                    except Exception as ce:
                        log.info("[migrate] Could not add %s: %s", cat_col, ce)

            # Ownership & provenance columns on podcast
            if "podcast_guid" not in cols_pod:
                try:
                    conn.exec_driver_sql("ALTER TABLE podcast ADD COLUMN podcast_guid VARCHAR NULL")
                    log.info("[migrate] Added podcast.podcast_guid")
                except Exception as pe:
                    log.info("[migrate] Could not add podcast_guid: %s", pe)
            if "feed_url_canonical" not in cols_pod:
                try:
                    conn.exec_driver_sql("ALTER TABLE podcast ADD COLUMN feed_url_canonical VARCHAR NULL")
                    log.info("[migrate] Added podcast.feed_url_canonical")
                except Exception as fe:
                    log.info("[migrate] Could not add feed_url_canonical: %s", fe)
            if "verification_method" not in cols_pod:
                try:
                    conn.exec_driver_sql("ALTER TABLE podcast ADD COLUMN verification_method VARCHAR NULL")
                    log.info("[migrate] Added podcast.verification_method")
                except Exception as ve:
                    log.info("[migrate] Could not add verification_method: %s", ve)
            if "verified_at" not in cols_pod:
                try:
                    conn.exec_driver_sql("ALTER TABLE podcast ADD COLUMN verified_at TIMESTAMP NULL")
                    log.info("[migrate] Added podcast.verified_at")
                except Exception as ve2:
                    log.info("[migrate] Could not add verified_at: %s", ve2)

            # --- subscription table
            res_sub = conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='subscription'"
            ).fetchone()
            if not res_sub:
                conn.exec_driver_sql(
                    """
CREATE TABLE subscription (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    stripe_subscription_id VARCHAR(255) NOT NULL,
    plan_key VARCHAR(64) NOT NULL,
    price_id VARCHAR(255) NOT NULL,
    status VARCHAR(64) NOT NULL DEFAULT 'incomplete',
    current_period_end TIMESTAMP NULL,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT 0,
    billing_cycle VARCHAR(16) NULL,
    subscription_started_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY(user_id) REFERENCES user(id)
);
"""
                )
                log.info("[migrate] Created subscription table")
            else:
                res_sub_cols = conn.exec_driver_sql("PRAGMA table_info(subscription)")
                sub_cols = [row[1] for row in res_sub_cols]
                for add_col, ddl in {
                    "billing_cycle": "VARCHAR(16) NULL",
                    "subscription_started_at": "TIMESTAMP NULL",
                }.items():
                    if add_col not in sub_cols:
                        try:
                            conn.exec_driver_sql(f"ALTER TABLE subscription ADD COLUMN {add_col} {ddl}")
                            log.info("[migrate] Added subscription.%s", add_col)
                        except Exception as ae:
                            log.info("[migrate] Could not add subscription.%s: %s", add_col, ae)

            # --- mediaitem columns
            try:
                res_media = conn.exec_driver_sql("PRAGMA table_info(mediaitem)")
                media_cols = [row[1] for row in res_media]
                if "trigger_keyword" not in media_cols:
                    conn.exec_driver_sql("ALTER TABLE mediaitem ADD COLUMN trigger_keyword VARCHAR NULL")
                    log.info("[migrate] Added mediaitem.trigger_keyword")
                if "expires_at" not in media_cols:
                    try:
                        conn.exec_driver_sql("ALTER TABLE mediaitem ADD COLUMN expires_at TIMESTAMP NULL")
                        log.info("[migrate] Added mediaitem.expires_at")
                    except Exception as ee:
                        log.info("[migrate] Could not add mediaitem.expires_at: %s", ee)
            except Exception as me:
                log.info("[migrate] Could not alter mediaitem: %s", me)
    except Exception as e:
        # Don't block startup on migration issues.
        log.warning("[migrate] Skipped some migrations: %s", e)


def _ensure_user_admin_column() -> None:
    """Ensure the user table has an is_admin flag (SQLite + Postgres)."""
    try:
        inspector = inspect(engine)
        cols = {col["name"] for col in inspector.get_columns("user")}
    except Exception as e:  # pragma: no cover - best effort
        log.warning("[migrate] Could not inspect user table for is_admin: %s", e)
        return

    if "is_admin" in cols:
        return

    dialect = engine.dialect.name.lower()
    if "sqlite" in dialect:
        stmt = "ALTER TABLE user ADD COLUMN is_admin INTEGER DEFAULT 0"
    else:
        stmt = 'ALTER TABLE "user" ADD COLUMN is_admin BOOLEAN DEFAULT FALSE'

    try:
        with engine.begin() as conn:
            conn.execute(text(stmt))
        log.info("[migrate] Added user.is_admin column")
    except Exception as e:  # pragma: no cover - additive migration best effort
        log.warning("[migrate] Could not add user.is_admin column: %s", e)


def _ensure_primary_admin() -> None:
    """Ensure ADMIN_EMAIL user has is_admin flag set."""
    admin_email = getattr(settings, 'ADMIN_EMAIL', None)
    if not admin_email:
        return
    admin_email = admin_email.lower()
    try:
        with engine.begin() as conn:
            dialect = engine.dialect.name.lower()
            if 'sqlite' in dialect:
                stmt = "UPDATE user SET is_admin = 1 WHERE lower(email) = :email"
            else:
                stmt = 'UPDATE \"user\" SET is_admin = TRUE WHERE lower(email) = :email'
            result = conn.execute(text(stmt), {'email': admin_email})
            if result.rowcount:
                log.info('[startup] Ensured admin account flag for %s', admin_email)
    except Exception as e:
        log.warning('[startup] Could not ensure admin flag for %s: %s', admin_email, e)


def _compute_pt_expiry(created_at_utc: datetime, days: int = 14) -> datetime:
    """Compute UTC expiry aligned to 2am America/Los_Angeles."""
    try:
        pt = ZoneInfo("America/Los_Angeles") if ZoneInfo else None
    except Exception:
        pt = None

    if not pt:
        # Fallback: approximate 2am PT as 10:00 UTC (DST ignored) for dev.
        first_boundary_utc = created_at_utc.replace(minute=0, second=0, microsecond=0)
        if created_at_utc.hour >= 10:
            first_boundary_utc = (first_boundary_utc + timedelta(days=1)).replace(hour=10)
        else:
            first_boundary_utc = first_boundary_utc.replace(hour=10)
        return first_boundary_utc + timedelta(days=days)

    created_pt = created_at_utc.astimezone(pt)
    first_boundary_pt = created_pt.replace(hour=2, minute=0, second=0, microsecond=0)
    if created_pt >= first_boundary_pt:
        first_boundary_pt = (first_boundary_pt + timedelta(days=1)).replace(hour=2)
    expiry_pt = first_boundary_pt + timedelta(days=days)
    return expiry_pt.astimezone(ZoneInfo("UTC") if ZoneInfo else timezone.utc)


def _backfill_mediaitem_expires_at(limit: int | None = None) -> None:
    """Set expires_at for media items missing it (idempotent)."""
    try:
        with session_scope() as session:
            from api.models.podcast import MediaItem, MediaCategory
            _limit = limit or _ROW_LIMIT
            q = select(MediaItem).filter((MediaItem.expires_at == None)).limit(_limit)  # type: ignore
            items = session.exec(q).all()
            changed = 0
            for m in items:
                try:
                    if getattr(m, "category", None) == getattr(MediaCategory, "main_content", None):
                        ca = getattr(m, "created_at", None) or datetime.utcnow()
                        m.expires_at = _compute_pt_expiry(ca)
                        session.add(m)
                        changed += 1
                except Exception:
                    continue
            if changed:
                session.commit()
                log.info("[migrate] Backfilled expires_at for %s media items", changed)
    except Exception as e:
        log.warning("_backfill_mediaitem_expires_at failed: %s", e)

def _ensure_user_terms_columns() -> None:
    """Ensure columns for tracking terms acceptance exist across engines."""
    backend = engine.url.get_backend_name()
    if backend == "sqlite":
        try:
            with engine.connect() as conn:
                res = conn.exec_driver_sql("PRAGMA table_info(user)")
                cols = {row[1] for row in res}
                if "terms_version_accepted" not in cols:
                    conn.exec_driver_sql("ALTER TABLE user ADD COLUMN terms_version_accepted TEXT NULL")
                    log.info("[migrate] Added user.terms_version_accepted")
                if "terms_accepted_at" not in cols:
                    conn.exec_driver_sql("ALTER TABLE user ADD COLUMN terms_accepted_at TIMESTAMP NULL")
                    log.info("[migrate] Added user.terms_accepted_at")
                if "terms_accepted_ip" not in cols:
                    conn.exec_driver_sql("ALTER TABLE user ADD COLUMN terms_accepted_ip VARCHAR(64) NULL")
                    log.info("[migrate] Added user.terms_accepted_ip")
        except Exception as exc:  # pragma: no cover
            log.warning("[migrate] Unable to ensure user terms columns (sqlite): %s", exc)
    else:
        statements = [
            'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS terms_version_accepted VARCHAR(64)',
            'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS terms_accepted_at TIMESTAMP NULL',
            'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS terms_accepted_ip VARCHAR(64) NULL',
        ]
        try:
            with engine.connect() as conn:
                for stmt in statements:
                    conn.exec_driver_sql(stmt)
        except Exception as exc:  # pragma: no cover
            log.warning("[migrate] Unable to ensure user terms columns (%s): %s", backend, exc)


def _ensure_rss_feed_columns() -> None:
    """Add columns needed for self-hosted RSS feed generation.
    
    Adds:
    - episode.audio_file_size: File size in bytes (required for RSS <enclosure> tag)
    - episode.duration_ms: Duration in milliseconds (for iTunes <duration> tag)
    - podcast.slug: Friendly URL slug (e.g., 'my-awesome-podcast')
    """
    backend = engine.url.get_backend_name()
    if backend == "sqlite":
        try:
            with engine.connect() as conn:
                # Episode columns
                res = conn.exec_driver_sql("PRAGMA table_info(episode)")
                cols = {row[1] for row in res}
                
                if "audio_file_size" not in cols:
                    conn.exec_driver_sql("ALTER TABLE episode ADD COLUMN audio_file_size INTEGER")
                    log.info("[migrate] Added episode.audio_file_size for RSS enclosures")
                
                if "duration_ms" not in cols:
                    conn.exec_driver_sql("ALTER TABLE episode ADD COLUMN duration_ms INTEGER")
                    log.info("[migrate] Added episode.duration_ms for iTunes duration tag")
                
                # Podcast slug column
                res = conn.exec_driver_sql("PRAGMA table_info(podcast)")
                pod_cols = {row[1] for row in res}
                
                if "slug" not in pod_cols:
                    # SQLite doesn't support adding UNIQUE columns, enforce at app level
                    conn.exec_driver_sql("ALTER TABLE podcast ADD COLUMN slug VARCHAR(100)")
                    log.info("[migrate] Added podcast.slug for friendly RSS URLs")
                    
                    # Auto-generate slugs for existing podcasts
                    import re
                    from sqlmodel import Session, select
                    from api.models.podcast import Podcast
                    
                    with Session(engine) as session:
                        podcasts = session.exec(select(Podcast)).all()
                        for podcast in podcasts:
                            if not podcast.slug:
                                # Generate slug from name: "My Awesome Podcast" -> "my-awesome-podcast"
                                slug = re.sub(r'[^a-z0-9]+', '-', podcast.name.lower()).strip('-')
                                # Ensure uniqueness
                                base_slug = slug
                                counter = 1
                                while session.exec(select(Podcast).where(Podcast.slug == slug)).first():
                                    slug = f"{base_slug}-{counter}"
                                    counter += 1
                                podcast.slug = slug
                                session.add(podcast)
                        session.commit()
                        log.info("[migrate] Auto-generated slugs for %d existing podcast(s)", len(podcasts))
        except Exception as exc:  # pragma: no cover
            log.warning("[migrate] Unable to ensure RSS feed columns (sqlite): %s", exc)
    else:
        # PostgreSQL
        statements = [
            'ALTER TABLE episode ADD COLUMN IF NOT EXISTS audio_file_size INTEGER',
            'ALTER TABLE episode ADD COLUMN IF NOT EXISTS duration_ms INTEGER',
            'ALTER TABLE episode ADD COLUMN IF NOT EXISTS episode_type VARCHAR(20) DEFAULT \'full\'',
            'ALTER TABLE podcast ADD COLUMN IF NOT EXISTS slug VARCHAR(100) UNIQUE',
            'ALTER TABLE podcast ADD COLUMN IF NOT EXISTS is_explicit BOOLEAN DEFAULT FALSE',
            'ALTER TABLE podcast ADD COLUMN IF NOT EXISTS itunes_category VARCHAR(100)',
        ]
        try:
            with engine.connect() as conn:
                for stmt in statements:
                    conn.exec_driver_sql(stmt)
                conn.commit()  # Commit the schema changes before querying
                log.info("[migrate] Ensured RSS feed columns exist (PostgreSQL)")
                
                # Auto-generate slugs for existing podcasts
                import re
                from sqlmodel import Session, select
                from api.models.podcast import Podcast
                
                with Session(engine) as session:
                    podcasts = session.exec(select(Podcast).where(Podcast.slug == None)).all()
                    if podcasts:
                        for podcast in podcasts:
                            slug = re.sub(r'[^a-z0-9]+', '-', podcast.name.lower()).strip('-')
                            # Ensure uniqueness
                            base_slug = slug
                            counter = 1
                            while session.exec(select(Podcast).where(Podcast.slug == slug)).first():
                                slug = f"{base_slug}-{counter}"
                                counter += 1
                            podcast.slug = slug
                            session.add(podcast)
                        session.commit()
                        log.info("[migrate] Auto-generated slugs for %d existing podcast(s)", len(podcasts))
        except Exception as exc:  # pragma: no cover
            log.warning("[migrate] Unable to ensure RSS feed columns (%s): %s", backend, exc)


def _kill_zombie_assembly_processes() -> None:
    """Kill any orphaned assembly worker processes from previous restarts.
    
    This prevents zombie processes from blocking the event loop.
    """
    try:
        import psutil
        current_pid = os.getpid()
        killed = 0
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.pid == current_pid:
                    continue
                    
                cmdline = proc.info.get('cmdline') or []
                cmdline_str = ' '.join(cmdline)
                
                # Look for assembly worker processes
                if 'assemble' in cmdline_str.lower() and 'python' in cmdline_str.lower():
                    log.warning("[startup] Killing zombie assembly process: pid=%s cmd=%s", 
                              proc.pid, cmdline_str[:100])
                    proc.kill()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
                
        if killed > 0:
            log.info("[startup] Killed %d zombie assembly process(es)", killed)
    except ImportError:
        log.debug("[startup] psutil not available; skipping zombie process cleanup")
    except Exception as e:
        log.warning("[startup] Zombie process cleanup failed: %s", e)


def _recover_stuck_processing_episodes(limit: int | None = None) -> None:
    """Check for episodes stuck in 'processing' status and mark them for retry if transcripts exist.
    
    This handles the case where:
    1. A deployment/restart happens while episodes are processing
    2. The assembly job is lost but the transcript was already generated
    3. Episodes remain stuck in 'processing' forever
    
    We'll mark these as 'error' with a specific message so users can retry them.
    """
    try:
        with session_scope() as session:
            from api.core.paths import TRANSCRIPTS_DIR
            
            _limit = limit or _ROW_LIMIT
            
            # Find episodes in processing status that are older than 30 minutes
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=30)
            
            try:
                q = select(Episode).where(
                    Episode.status == "processing"
                )
                if hasattr(Episode, 'processed_at'):
                    q = q.where(Episode.processed_at < cutoff_time)
                elif hasattr(Episode, 'created_at'):
                    q = q.where(Episode.created_at < cutoff_time)
                
                q = q.limit(_limit)
                episodes = session.exec(q).all()
            except Exception:
                # If the query fails due to schema issues, skip this recovery
                log.debug("[startup] Unable to query stuck episodes", exc_info=True)
                return
            
            recovered = 0
            for ep in episodes:
                try:
                    # Check if transcript exists for this episode
                    transcript_exists = False
                    
                    # Try to find transcript by episode ID
                    if hasattr(ep, 'id') and ep.id:
                        transcript_path = TRANSCRIPTS_DIR / f"{ep.id}.json"
                        if transcript_path.exists():
                            transcript_exists = True
                    
                    # Also check by title/output filename if available
                    if not transcript_exists and hasattr(ep, 'title') and ep.title:
                        # Sanitize title to potential filename
                        safe_title = "".join(c for c in str(ep.title) if c.isalnum() or c in (' ', '-', '_')).strip()
                        safe_title = safe_title.replace(' ', '_')
                        if safe_title:
                            transcript_path = TRANSCRIPTS_DIR / f"{safe_title}.json"
                            if transcript_path.exists():
                                transcript_exists = True
                    
                    if transcript_exists:
                        # Transcript exists but episode is stuck - mark it for retry
                        try:
                            from api.models.podcast import EpisodeStatus as _EpStatus
                            ep.status = _EpStatus.error  # type: ignore
                        except Exception:
                            ep.status = "error"  # type: ignore
                        
                        # Set a helpful error message
                        ep.spreaker_publish_error = "Episode was interrupted during processing. Transcript exists. Click 'Retry' to complete assembly."
                        
                        session.add(ep)
                        recovered += 1
                        
                        log.info(
                            "[startup] Marked episode %s (%s) for retry - transcript exists but status was stuck in processing",
                            ep.id if hasattr(ep, 'id') else '?',
                            ep.title if hasattr(ep, 'title') else 'untitled'
                        )
                    else:
                        # No transcript found and processing for 30+ minutes - likely failed
                        # Mark as error so user knows to re-upload or investigate
                        try:
                            from api.models.podcast import EpisodeStatus as _EpStatus
                            ep.status = _EpStatus.error  # type: ignore
                        except Exception:
                            ep.status = "error"  # type: ignore
                        
                        ep.spreaker_publish_error = "Episode processing timed out or was interrupted. Please retry or re-upload your audio."
                        
                        session.add(ep)
                        recovered += 1
                        
                        log.warning(
                            "[startup] Marked episode %s (%s) as error - stuck in processing for 30+ min with no transcript",
                            ep.id if hasattr(ep, 'id') else '?',
                            ep.title if hasattr(ep, 'title') else 'untitled'
                        )
                        
                except Exception:
                    log.debug("[startup] Failed to check/recover episode", exc_info=True)
                    continue
            
            if recovered > 0:
                try:
                    session.commit()
                    log.info("[startup] Recovered %d stuck episodes (marked for retry)", recovered)
                except Exception:
                    log.warning("[startup] Failed to commit recovered episodes", exc_info=True)
                    
    except Exception as e:
        log.warning("[startup] _recover_stuck_processing_episodes failed: %s", e)


def _ensure_episode_gcs_columns() -> None:
    """Add GCS and import-related columns to episode table.
    
    These columns support:
    - GCS storage paths for audio/cover retention
    - Episode import from external feeds
    - Numbering conflict detection
    """
    backend = engine.url.get_backend_name()
    
    if backend == "sqlite":
        try:
            with engine.connect() as conn:
                res = conn.exec_driver_sql("PRAGMA table_info(episode)")
                cols = {row[1] for row in res}
                
                columns_to_add = {
                    'gcs_audio_path': 'VARCHAR',
                    'gcs_cover_path': 'VARCHAR',
                    'has_numbering_conflict': 'BOOLEAN DEFAULT FALSE',
                    'original_guid': 'VARCHAR',
                    'source_media_url': 'VARCHAR',
                    'source_published_at': 'DATETIME',
                    'source_checksum': 'VARCHAR',
                }
                
                for col_name, col_type in columns_to_add.items():
                    if col_name not in cols:
                        conn.exec_driver_sql(f"ALTER TABLE episode ADD COLUMN {col_name} {col_type}")
                        log.info("[migrate] Added episode.%s", col_name)
                        
        except Exception as exc:
            log.warning("[migrate] Unable to ensure episode GCS columns (sqlite): %s", exc)
    else:
        # PostgreSQL
        statements = [
            'ALTER TABLE episode ADD COLUMN IF NOT EXISTS gcs_audio_path VARCHAR',
            'ALTER TABLE episode ADD COLUMN IF NOT EXISTS gcs_cover_path VARCHAR',
            'ALTER TABLE episode ADD COLUMN IF NOT EXISTS has_numbering_conflict BOOLEAN DEFAULT FALSE',
            'ALTER TABLE episode ADD COLUMN IF NOT EXISTS original_guid VARCHAR',
            'ALTER TABLE episode ADD COLUMN IF NOT EXISTS source_media_url VARCHAR',
            'ALTER TABLE episode ADD COLUMN IF NOT EXISTS source_published_at TIMESTAMP',
            'ALTER TABLE episode ADD COLUMN IF NOT EXISTS source_checksum VARCHAR',
        ]
        try:
            with engine.connect() as conn:
                for stmt in statements:
                    conn.exec_driver_sql(stmt)
                log.info("[migrate] Ensured episode GCS columns exist (PostgreSQL)")
        except Exception as exc:
            log.warning("[migrate] Unable to ensure episode GCS columns (postgresql): %s", exc)


def run_startup_tasks() -> None:
    """Perform lightweight startup + optionally heavy normalization/backfill.

    Heavy tasks are gated by STARTUP_HEAVY_TASKS env flag (on/off/auto) and
    use STARTUP_ROW_LIMIT to cap per-start scans. Default is OFF in prod.
    """
    log.info("[startup] begin (env=%s heavy=%s row_limit=%s)", _APP_ENV, _HEAVY_ENABLED, _ROW_LIMIT)

    # Kill any zombie processes from previous crashes/restarts
    with _timing("kill_zombie_processes"):
        _kill_zombie_assembly_processes()

    with _timing("create_db_and_tables"):
        try:
            create_db_and_tables()
        except Exception as e:
            log.error("[startup] create_db_and_tables failed (continuing): %s", e)

    # Always-on lightweight additive steps
    with _timing("ensure_user_admin_column"):
        _ensure_user_admin_column()
    with _timing("ensure_primary_admin"):
        _ensure_primary_admin()
    with _timing("ensure_user_terms_columns"):
        _ensure_user_terms_columns()
    with _timing("ensure_user_subscription_column"):
        _ensure_user_subscription_column()
    with _timing("ensure_episode_gcs_columns"):
        _ensure_episode_gcs_columns()
    with _timing("ensure_rss_feed_columns"):
        _ensure_rss_feed_columns()
    
    # Always recover stuck episodes - this is critical for good UX after deployments
    with _timing("recover_stuck_episodes"):
        _recover_stuck_processing_episodes()

    if not _HEAVY_ENABLED:
        log.info("[startup] heavy tasks disabled (STARTUP_HEAVY_TASKS=%s)", _HEAVY_FLAG)
        return

    # Heavy / potentially slow tasks
    with _timing("normalize_episode_paths"):
        _normalize_episode_paths()
    with _timing("normalize_podcast_covers"):
        _normalize_podcast_covers()
    with _timing("backfill_mediaitem_expires_at"):
        _backfill_mediaitem_expires_at()

    log.info("[startup] heavy tasks complete")


__all__ = [
    "run_startup_tasks",
    "_compute_pt_expiry",
    "_normalize_episode_paths",
    "_normalize_podcast_covers",
    "_ensure_user_subscription_column",
    "_ensure_user_terms_columns",
    "_backfill_mediaitem_expires_at",
    "_recover_stuck_processing_episodes",
]


