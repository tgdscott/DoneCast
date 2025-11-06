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


# Obsolete migration functions removed Oct 2025 - now in migrations/one_time_migrations.py
# If you see imports errors, check that one_time_migrations.py is being called in run_startup_tasks()


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


def _recover_raw_file_transcripts(limit: int | None = None) -> None:
    """Recover transcript metadata for raw files from GCS after deployment.
    
    After a Cloud Run deployment (or server restart in dev), the ephemeral filesystem is wiped.
    This causes raw file transcripts to appear as "processing" even though they're complete.
    
    This function:
    1. Queries MediaTranscript table for all completed transcripts
    2. Checks if the local transcript file exists
    3. If not, downloads it from GCS using the stored metadata
    4. Restores files to local storage so they appear as "ready" to users
    
    PERFORMANCE: Uses small limit (50) by default to minimize startup time.
    
    NOTE: Now enabled in dev mode too - transcripts should survive server restarts.
    """
    # REMOVED: Dev mode check - transcripts should survive restarts in ALL environments
    
    # FAST PATH: Skip if TRANSCRIPTS_DIR already has files (container reuse, not fresh start)
    try:
        from api.core.paths import TRANSCRIPTS_DIR
        if TRANSCRIPTS_DIR.exists() and any(TRANSCRIPTS_DIR.iterdir()):
            log.debug("[startup] Transcripts directory already populated, skipping recovery")
            return
    except Exception:
        pass  # Continue to recovery if check fails
    
    try:
        with session_scope() as session:
            from api.models.transcription import MediaTranscript
            
            # Use smaller default limit (50) for faster startup - only recent transcripts need recovery
            _limit = limit if limit is not None else min(_ROW_LIMIT, 50)
            
            # Query all MediaTranscript records that have GCS metadata
            q = select(MediaTranscript).where(
                MediaTranscript.transcript_meta_json != "{}"
            ).limit(_limit)
            
            transcripts = session.exec(q).all()
            
            if not transcripts:
                log.debug("[startup] No transcript metadata to recover")
                return
            
            recovered = 0
            failed = 0
            skipped = 0
            
            for transcript_record in transcripts:
                try:
                    import json
                    from pathlib import Path
                    
                    filename = transcript_record.filename
                    stem = Path(filename).stem
                    
                    # Check if transcript already exists locally
                    local_candidates = [
                        TRANSCRIPTS_DIR / f"{stem}.json",
                        TRANSCRIPTS_DIR / f"{stem}.words.json",
                        TRANSCRIPTS_DIR / f"{stem}.original.json",
                        TRANSCRIPTS_DIR / f"{stem}.original.words.json",
                    ]
                    
                    already_exists = any(p.exists() for p in local_candidates)
                    if already_exists:
                        skipped += 1
                        continue  # Already recovered, skip
                    
                    # Parse metadata to get GCS location
                    meta = json.loads(transcript_record.transcript_meta_json)
                    gcs_uri = meta.get("gcs_json") or meta.get("gcs_uri")
                    bucket_stem = meta.get("bucket_stem") or meta.get("safe_stem") or stem
                    
                    if not gcs_uri:
                        # No GCS URI in metadata - skip (transcript may be local-only from dev)
                        continue
                    
                    # Determine bucket and key
                    if gcs_uri.startswith("gs://"):
                        # Parse gs://bucket/path format
                        parts = gcs_uri.replace("gs://", "").split("/", 1)
                        if len(parts) == 2:
                            bucket_name, key = parts
                        else:
                            bucket_name = os.getenv("TRANSCRIPTS_BUCKET", "").strip()
                            key = f"transcripts/{bucket_stem}.json"
                    else:
                        # Already a key path
                        bucket_name = os.getenv("TRANSCRIPTS_BUCKET", "").strip()
                        key = gcs_uri
                    
                    if not bucket_name or not key:
                        continue  # Missing configuration
                    
                    # Download from GCS
                    try:
                        from infrastructure.gcs import download_bytes
                        
                        content = download_bytes(bucket_name, key)
                        if content:
                            # Restore to local path
                            TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
                            local_path = TRANSCRIPTS_DIR / f"{stem}.json"
                            local_path.write_bytes(content)
                            
                            recovered += 1
                            log.debug(
                                "[startup] Recovered transcript from gs://%s/%s to %s",
                                bucket_name, key, local_path
                            )
                    except Exception as e:
                        failed += 1
                        log.debug(
                            "[startup] Failed to download transcript gs://%s/%s: %s",
                            bucket_name, key, e
                        )
                        
                except Exception as e:
                    log.debug("[startup] Failed to process transcript record: %s", e)
                    continue
            
            if recovered > 0 or skipped > 0 or failed > 0:
                log.info("[startup] Transcript recovery: %d recovered, %d skipped (already exist), %d failed", 
                        recovered, skipped, failed)
            else:
                log.debug("[startup] No transcripts needed recovery")
            
            # Explicit commit to finalize any session state
            try:
                session.commit()
            except Exception as commit_exc:
                log.warning("[startup] Transcript recovery commit failed: %s", commit_exc)
                session.rollback()
                
    except Exception as e:
        log.warning("[startup] Raw file transcript recovery failed: %s", e)
        # Ensure any failed transactions are cleaned up
        try:
            with session_scope() as cleanup_session:
                cleanup_session.rollback()
        except Exception:
            pass  # Cleanup failed, continuing


def _recover_stuck_processing_episodes(limit: int | None = None) -> None:
    """Check for episodes stuck in 'processing' status and mark them for retry if transcripts exist.
    
    This handles the case where:
    1. A deployment/restart happens while episodes are processing
    2. The assembly job is lost but the transcript was already generated
    3. Episodes remain stuck in 'processing' forever
    
    We'll mark these as 'error' with a specific message so users can retry them.
    
    PERFORMANCE: Uses small limit (30) by default to minimize startup time.
    """
    # SKIP IN LOCAL DEV: This recovery is for production Cloud Run ephemeral containers only
    if _APP_ENV in {"dev", "development", "local"}:
        log.debug("[startup] Skipping stuck episode recovery in local dev environment")
        return
    
    try:
        with session_scope() as session:
            from api.core.paths import TRANSCRIPTS_DIR
            
            # Use smaller default limit (30) for faster startup
            _limit = limit if limit is not None else min(_ROW_LIMIT, 30)
            
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
                except Exception as commit_exc:
                    log.warning("[startup] Failed to commit recovered episodes: %s", commit_exc)
                    session.rollback()
                    
    except Exception as e:
        log.warning("[startup] _recover_stuck_processing_episodes failed: %s", e)
        # Ensure any failed transactions are cleaned up
        try:
            with session_scope() as cleanup_session:
                cleanup_session.rollback()
        except Exception:
            pass  # Cleanup failed, continuing


# Additional obsolete migration functions removed - now in migrations/one_time_migrations.py


def run_startup_tasks() -> None:
    """Perform lightweight startup + optionally heavy normalization/backfill.

    Heavy tasks are gated by STARTUP_HEAVY_TASKS env flag (on/off/auto) and
    use STARTUP_ROW_LIMIT to cap per-start scans. Default is OFF in prod.
    
    PERFORMANCE: Recovery tasks run with aggressive limits (50/30) to minimize
    startup latency. Cloud Run has a 2-second health check threshold - exceeding
    this causes restart death spirals.
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

    # One-time migrations - can be disabled via DISABLE_STARTUP_MIGRATIONS env var
    # Set DISABLE_STARTUP_MIGRATIONS=1 in production after all migrations complete
    _DISABLE_MIGRATIONS = (os.getenv("DISABLE_STARTUP_MIGRATIONS") or "").strip().lower() in {"1", "true", "yes", "on"}
    if not _DISABLE_MIGRATIONS:
        with _timing("one_time_migrations"):
            from migrations.one_time_migrations import run_one_time_migrations
            results = run_one_time_migrations()
            
            # Smart cleanup detection
            if all(results.values()):
                log.info("✅ [startup] All one-time migrations complete!")
                log.info("📝 [startup] Safe to set DISABLE_STARTUP_MIGRATIONS=1 in production")
            else:
                incomplete = [name for name, done in results.items() if not done]
                log.info("⏳ [startup] Migrations still pending: %s", ", ".join(incomplete))
    else:
        log.info("[startup] Skipping one_time_migrations (DISABLE_STARTUP_MIGRATIONS=1)")
    
    # Audit users without terms acceptance (read-only, for monitoring)
    # Can be disabled via DISABLE_STARTUP_MIGRATIONS
    if not _DISABLE_MIGRATIONS:
        with _timing("audit_terms_acceptance"):
            try:
                import sys
                import importlib.util
                migration_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'migrations', '999_audit_terms_acceptance.py')
                spec = importlib.util.spec_from_file_location('audit_terms_migration', migration_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    with session_scope() as session:
                        module.audit_users_without_terms(session)
            except Exception as exc:
                log.warning("[startup] audit_terms_acceptance failed (non-critical): %s", exc)
    
    # Auto-migrate users with old terms versions to current (CRITICAL: prevents "accept terms daily" bug)
    # This ALWAYS runs even if DISABLE_STARTUP_MIGRATIONS=1 because it's critical for UX
    with _timing("auto_migrate_terms_versions"):
        try:
            import sys
            import importlib.util
            migration_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'migrations', '099_auto_update_terms_versions.py')
            spec = importlib.util.spec_from_file_location('auto_terms_migration', migration_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                with session_scope() as session:
                    try:
                        module.migrate(session)
                    except Exception as migration_exc:
                        # Ensure session is rolled back before raising
                        try:
                            session.rollback()
                        except Exception:
                            pass  # Already rolled back
                        raise migration_exc
        except Exception as exc:
            log.error("[startup] auto_migrate_terms_versions failed (CRITICAL): %s", exc)
            # Don't crash startup, but log loudly since this affects all users
            # CRITICAL: Explicitly rollback any dangling transactions in the connection pool
            try:
                with session_scope() as cleanup_session:
                    cleanup_session.rollback()
            except Exception:
                pass  # Cleanup failed, but we logged the original error
    
    # Always recover raw file transcripts - prevents "processing" state after deployment
    # Uses SMALL limit (50) to minimize startup time
    with _timing("recover_raw_file_transcripts"):
        _recover_raw_file_transcripts(limit=50)
    
    # Always recover stuck episodes - this is critical for good UX after deployments
    # Uses SMALL limit (30) to minimize startup time
    with _timing("recover_stuck_episodes"):
        _recover_stuck_processing_episodes(limit=30)

    if not _HEAVY_ENABLED:
        log.info("[startup] heavy tasks disabled (STARTUP_HEAVY_TASKS=%s)", _HEAVY_FLAG)
        return

    # Heavy / potentially slow tasks (currently none - old migrations removed Oct 15, 2025)
    log.info("[startup] heavy tasks complete")


__all__ = [
    "run_startup_tasks",
    "_compute_pt_expiry",
    "_recover_raw_file_transcripts",
    "_recover_stuck_processing_episodes",
]


