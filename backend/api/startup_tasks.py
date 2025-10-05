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


def _normalize_episode_paths() -> None:
    """Ensure Episode paths store only basenames for local files."""
    try:
        with session_scope() as session:
            q = select(Episode).limit(5000)
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


def _normalize_podcast_covers() -> None:
    """Ensure Podcast.cover_path stores only a basename if it's a local path."""
    try:
        with session_scope() as session:
            q = select(Podcast).limit(5000)
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


def _backfill_mediaitem_expires_at() -> None:
    """Set expires_at for media items missing it (idempotent)."""
    try:
        with session_scope() as session:
            from api.models.podcast import MediaItem, MediaCategory

            q = select(MediaItem).filter((MediaItem.expires_at == None)).limit(5000)  # type: ignore
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


def run_startup_tasks() -> None:
    """Create tables and run all additive/idempotent startup tasks."""
    try:
        create_db_and_tables()
    except Exception as e:
        log.error("[startup] create_db_and_tables failed (continuing): %s", e)

    _normalize_episode_paths()
    _normalize_podcast_covers()
    _ensure_user_admin_column()
    _ensure_primary_admin()
    _ensure_user_terms_columns()
    _ensure_user_subscription_column()
    _backfill_mediaitem_expires_at()


__all__ = [
    "run_startup_tasks",
    "_compute_pt_expiry",
    "_normalize_episode_paths",
    "_normalize_podcast_covers",
    "_ensure_user_subscription_column",
    "_ensure_user_terms_columns",
    "_backfill_mediaitem_expires_at",
]


