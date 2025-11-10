"""
ONE-TIME MIGRATIONS - Safe to clear after production verification

This file contains database migrations that need to run once, then can be deleted.
Once all migrations show "already exists, skipping" in production logs, you can:
1. Empty this file (keep the structure below)
2. Delete completed migration files from backend/migrations/

The system will automatically log when this file can be safely cleared.
"""
from __future__ import annotations

import logging
from sqlalchemy import inspect, text
from api.core.database import engine
from .migration_tracker import run_migration_once, get_pending_migrations

log = logging.getLogger(__name__)


def run_one_time_migrations() -> dict[str, bool]:
    """
    Execute all one-time migrations using tracker to prevent re-running.
    
    Returns:
        dict mapping migration name to completion status (True = completed/skipped)
    """
    results = {}
    
    # Run migrations only if not already completed (tracked in migration_tracker table)
    # Once they show "already completed, skipping" delete them and the function
    
    results["ensure_user_admin_column"] = run_migration_once("ensure_user_admin_column", _ensure_user_admin_column)
    results["ensure_user_role_column"] = run_migration_once("ensure_user_role_column", _ensure_user_role_column)
    results["ensure_user_terms_columns"] = run_migration_once("ensure_user_terms_columns", _ensure_user_terms_columns)
    results["ensure_episode_gcs_columns"] = run_migration_once("ensure_episode_gcs_columns", _ensure_episode_gcs_columns)
    results["ensure_rss_feed_columns"] = run_migration_once("ensure_rss_feed_columns", _ensure_rss_feed_columns)
    results["ensure_website_sections_columns"] = run_migration_once("ensure_website_sections_columns", _ensure_website_sections_columns)
    results["ensure_auphonic_columns"] = run_migration_once("ensure_auphonic_columns", _ensure_auphonic_columns)
    results["ensure_tier_configuration_tables"] = run_migration_once("ensure_tier_configuration_tables", _ensure_tier_configuration_tables)
    results["ensure_mediaitem_episode_tracking"] = run_migration_once("ensure_mediaitem_episode_tracking", _ensure_mediaitem_episode_tracking)
    results["ensure_feedback_enhanced_columns"] = run_migration_once("ensure_feedback_enhanced_columns", _ensure_feedback_enhanced_columns)
    results["audit_terms_acceptance"] = run_migration_once("audit_terms_acceptance", _audit_terms_acceptance)
    results["auto_migrate_terms_versions"] = run_migration_once("auto_migrate_terms_versions", _auto_migrate_terms_versions)
    results["add_ledgerreason_enum_values"] = run_migration_once("add_ledgerreason_enum_values", _add_ledgerreason_enum_values)
    results["add_transcription_error_field"] = run_migration_once("add_transcription_error_field", _add_transcription_error_field)
    results["add_episode_priority"] = run_migration_once("add_episode_priority", _add_episode_priority)
    results["add_sms_notification_fields"] = run_migration_once("add_sms_notification_fields", _add_sms_notification_fields)
    results["add_phone_verification_table"] = run_migration_once("add_phone_verification_table", _add_phone_verification_table)
    
    # Check for pending migrations
    pending = get_pending_migrations()
    if pending:
        log.warning(f"[migrations] Migrations with failures: {', '.join(pending)}")
    
    return results


# ============================================================================
# MIGRATION FUNCTIONS (Delete these after they run successfully in production)
# ============================================================================

def _ensure_user_admin_column() -> bool:
    """Ensure the user table has an is_admin flag (PostgreSQL)."""
    try:
        inspector = inspect(engine)
        cols = {col["name"] for col in inspector.get_columns("user")}
    except Exception as e:
        log.warning("[migrate] Could not inspect user table for is_admin: %s", e)
        return False

    if "is_admin" in cols:
        log.debug("[migrate] user.is_admin already exists, skipping")
        return True

    stmt = 'ALTER TABLE "user" ADD COLUMN is_admin BOOLEAN DEFAULT FALSE'
    try:
        with engine.begin() as conn:
            conn.execute(text(stmt))
        log.info("[migrate] ✅ Added user.is_admin column")
        return True
    except Exception as e:
        log.warning("[migrate] Could not add user.is_admin column: %s", e)
        return False


def _ensure_user_role_column() -> bool:
    """Ensure the user table has a role column (PostgreSQL)."""
    try:
        inspector = inspect(engine)
        cols = {col["name"] for col in inspector.get_columns("user")}
    except Exception as e:
        log.warning("[migrate] Could not inspect user table for role: %s", e)
        return False

    if "role" in cols:
        log.debug("[migrate] user.role already exists, skipping")
        return True

    stmt = 'ALTER TABLE "user" ADD COLUMN role VARCHAR(50)'
    try:
        with engine.begin() as conn:
            conn.execute(text(stmt))
        log.info("[migrate] ✅ Added user.role column")
        return True
    except Exception as e:
        log.warning("[migrate] Could not add user.role column: %s", e)
        return False


def _ensure_user_terms_columns() -> bool:
    """Ensure user table has terms acceptance columns (PostgreSQL)."""
    try:
        inspector = inspect(engine)
        cols = {col["name"] for col in inspector.get_columns("user")}
    except Exception as e:
        log.warning("[migrate] Could not inspect user table for terms columns: %s", e)
        return False

    needed = {"terms_accepted_at", "terms_version_accepted"}
    missing = needed - cols
    
    if not missing:
        log.debug("[migrate] user terms columns already exist, skipping")
        return True

    for col in missing:
        if col == "terms_accepted_at":
            stmt = 'ALTER TABLE "user" ADD COLUMN terms_accepted_at TIMESTAMP'
        else:
            stmt = 'ALTER TABLE "user" ADD COLUMN terms_version_accepted VARCHAR(50)'
        
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
            log.info("[migrate] ✅ Added user.%s column", col)
        except Exception as e:
            log.warning("[migrate] Could not add user.%s: %s", col, e)
            return False
    
    return True


def _ensure_episode_gcs_columns() -> bool:
    """Ensure episode table has GCS path columns (PostgreSQL)."""
    try:
        inspector = inspect(engine)
        cols = {col["name"] for col in inspector.get_columns("episode")}
    except Exception as e:
        log.warning("[migrate] Could not inspect episode table: %s", e)
        return False

    if "gcs_audio_path" in cols:
        log.debug("[migrate] episode GCS columns already exist, skipping")
        return True

    stmt = 'ALTER TABLE episode ADD COLUMN gcs_audio_path VARCHAR(512)'
    try:
        with engine.begin() as conn:
            conn.execute(text(stmt))
        log.info("[migrate] ✅ Added episode.gcs_audio_path column")
        return True
    except Exception as e:
        log.warning("[migrate] Could not add episode.gcs_audio_path: %s", e)
        return False


def _ensure_rss_feed_columns() -> bool:
    """Ensure rssfeed table has OP3 analytics columns (PostgreSQL)."""
    try:
        inspector = inspect(engine)
        cols = {col["name"] for col in inspector.get_columns("rssfeed")}
    except Exception as e:
        log.warning("[migrate] Could not inspect rssfeed table: %s", e)
        return False

    needed = {"op3_prefix_enabled", "op3_custom_prefix"}
    missing = needed - cols
    
    if not missing:
        log.debug("[migrate] rssfeed columns already exist, skipping")
        return True

    for col in missing:
        if col == "op3_prefix_enabled":
            stmt = 'ALTER TABLE rssfeed ADD COLUMN op3_prefix_enabled BOOLEAN DEFAULT TRUE'
        else:
            stmt = 'ALTER TABLE rssfeed ADD COLUMN op3_custom_prefix VARCHAR(255)'
        
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
            log.info("[migrate] ✅ Added rssfeed.%s column", col)
        except Exception as e:
            log.warning("[migrate] Could not add rssfeed.%s: %s", col, e)
            return False
    
    return True


def _ensure_website_sections_columns() -> bool:
    """Ensure podcastwebsite table has sections_order column (PostgreSQL)."""
    try:
        inspector = inspect(engine)
        cols = {col["name"] for col in inspector.get_columns("podcastwebsite")}
    except Exception as e:
        log.warning("[migrate] Could not inspect podcastwebsite table: %s", e)
        return False

    if "sections_order" in cols:
        log.debug("[migrate] podcastwebsite.sections_order already exists, skipping")
        return True

    stmt = 'ALTER TABLE podcastwebsite ADD COLUMN sections_order TEXT'
    try:
        with engine.begin() as conn:
            conn.execute(text(stmt))
        log.info("[migrate] ✅ Added podcastwebsite.sections_order column")
        return True
    except Exception as e:
        log.warning("[migrate] Could not add podcastwebsite.sections_order: %s", e)
        return False


def _ensure_auphonic_columns() -> bool:
    """Run Auphonic column migrations (010, 011, 026)."""
    import importlib.util
    import os
    
    try:
        # Migration 010: Add auphonic fields to episode table
        migration_path = os.path.join(os.path.dirname(__file__), '010_add_auphonic_fields.py')
        spec = importlib.util.spec_from_file_location('migration_010', migration_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.run()
        
        # Migration 011: Add auphonic fields to mediaitem table
        migration_path_011 = os.path.join(os.path.dirname(__file__), '011_add_auphonic_mediaitem_fields.py')
        spec_011 = importlib.util.spec_from_file_location('migration_011', migration_path_011)
        if spec_011 and spec_011.loader:
            module_011 = importlib.util.module_from_spec(spec_011)
            spec_011.loader.exec_module(module_011)
            module_011.run()
        
        # Migration 026: Add Auphonic metadata fields
        migration_path_026 = os.path.join(os.path.dirname(__file__), '026_add_auphonic_metadata_fields.py')
        spec_026 = importlib.util.spec_from_file_location('migration_026', migration_path_026)
        if spec_026 and spec_026.loader:
            module_026 = importlib.util.module_from_spec(spec_026)
            spec_026.loader.exec_module(module_026)
            from api.core.database import engine
            module_026.migrate(engine)
        
        log.debug("[migrate] Auphonic columns verified")
        return True
    except Exception as e:
        log.warning("[migrate] Auphonic column migration failed: %s", e)
        return False


def _ensure_tier_configuration_tables() -> bool:
    """Initialize tier configuration system (migration 027, 028, 030)."""
    import importlib.util
    import os
    from sqlmodel import Session
    from api.core.database import engine
    
    try:
        # Migration 027: Initialize tier configuration system
        migration_path_027 = os.path.join(os.path.dirname(__file__), '027_initialize_tier_configuration.py')
        spec_027 = importlib.util.spec_from_file_location('migration_027', migration_path_027)
        if spec_027 and spec_027.loader:
            module_027 = importlib.util.module_from_spec(spec_027)
            spec_027.loader.exec_module(module_027)
            with Session(engine) as session:
                module_027.run_migration(session)
        
        # Migration 028: Add credits field to ProcessingMinutesLedger
        migration_path_028 = os.path.join(os.path.dirname(__file__), '028_add_credits_to_ledger.py')
        spec_028 = importlib.util.spec_from_file_location('migration_028', migration_path_028)
        if spec_028 and spec_028.loader:
            module_028 = importlib.util.module_from_spec(spec_028)
            spec_028.loader.exec_module(module_028)
            with Session(engine) as session:
                module_028.run_migration(session)
        
        # Migration 030: Optimize ledger indexes for invoice queries
        migration_path_030 = os.path.join(os.path.dirname(__file__), '030_optimize_ledger_indexes.py')
        spec_030 = importlib.util.spec_from_file_location('migration_030', migration_path_030)
        if spec_030 and spec_030.loader:
            module_030 = importlib.util.module_from_spec(spec_030)
            spec_030.loader.exec_module(module_030)
            with Session(engine) as session:
                module_030.run_migration(session)
        
        log.debug("[migrate] Tier configuration verified")
        return True
    except Exception as e:
        log.warning("[migrate] Tier configuration migration failed: %s", e)
        return False


def _ensure_mediaitem_episode_tracking() -> bool:
    """Add used_in_episode_id to mediaitem (migration 029)."""
    import importlib.util
    import os
    
    try:
        migration_path_029 = os.path.join(os.path.dirname(__file__), '029_add_mediaitem_used_in_episode.py')
        spec_029 = importlib.util.spec_from_file_location('migration_029', migration_path_029)
        if spec_029 and spec_029.loader:
            module_029 = importlib.util.module_from_spec(spec_029)
            spec_029.loader.exec_module(module_029)
            module_029.run()
        log.debug("[migrate] MediaItem episode tracking verified")
        return True
    except Exception as e:
        log.warning("[migrate] MediaItem tracking migration failed: %s", e)
        return False


def _ensure_feedback_enhanced_columns() -> bool:
    """Add enhanced context columns to feedback_submission (migration 030)."""
    import importlib.util
    import os
    
    try:
        migration_path_030 = os.path.join(os.path.dirname(__file__), '030_add_feedback_enhanced_columns.py')
        spec_030 = importlib.util.spec_from_file_location('migration_030_feedback', migration_path_030)
        if spec_030 and spec_030.loader:
            module_030 = importlib.util.module_from_spec(spec_030)
            spec_030.loader.exec_module(module_030)
            module_030.run_migration()
        log.debug("[migrate] Feedback enhanced columns verified")
        return True
    except Exception as e:
        log.warning("[migrate] Feedback columns migration failed: %s", e)
        return False


def _audit_terms_acceptance() -> bool:
    """One-time audit of terms acceptance (migration 999)."""
    import importlib.util
    import os
    from api.core.database import session_scope
    
    try:
        migration_path = os.path.join(os.path.dirname(__file__), '999_audit_terms_acceptance.py')
        spec = importlib.util.spec_from_file_location('audit_terms_migration', migration_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with session_scope() as session:
                module.audit_users_without_terms(session)
        log.debug("[migrate] Terms audit completed")
        return True
    except Exception as e:
        log.warning("[migrate] Terms audit failed: %s", e)
        return False


def _auto_migrate_terms_versions() -> bool:
    """Auto-update old terms versions (migration 099)."""
    import importlib.util
    import os
    from api.core.database import session_scope
    
    try:
        migration_path = os.path.join(os.path.dirname(__file__), '099_auto_update_terms_versions.py')
        spec = importlib.util.spec_from_file_location('auto_terms_migration', migration_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with session_scope() as session:
                module.migrate(session)
        log.debug("[migrate] Terms version migration completed")
        return True
    except Exception as e:
        log.warning("[migrate] Terms version migration failed: %s", e)
        return False


def _add_ledgerreason_enum_values() -> bool:
    """Add missing enum values to ledgerreason (migration 100)."""
    import importlib.util
    import os
    
    try:
        migration_path = os.path.join(os.path.dirname(__file__), '100_add_ledgerreason_enum_values.py')
        spec = importlib.util.spec_from_file_location('ledger_enum_migration', migration_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.upgrade()
        log.debug("[migrate] LedgerReason enum migration completed")
        return True
    except Exception as e:
        log.warning("[migrate] LedgerReason enum migration failed: %s", e)
        return False


def _add_transcription_error_field() -> bool:
    """Add transcription_error field to MediaItem table (migration 031)."""
    try:
        inspector = inspect(engine)
        cols = {col["name"] for col in inspector.get_columns("mediaitem")}
    except Exception as e:
        log.warning("[migrate] Could not inspect mediaitem table for transcription_error: %s", e)
        return False

    if "transcription_error" in cols:
        log.debug("[migrate] mediaitem.transcription_error already exists, skipping")
        return True

    stmt = 'ALTER TABLE mediaitem ADD COLUMN transcription_error TEXT DEFAULT NULL'
    try:
        with engine.begin() as conn:
            conn.execute(text(stmt))
        log.info("[migrate] ✅ Added mediaitem.transcription_error column")
        return True
    except Exception as e:
        log.warning("[migrate] Could not add mediaitem.transcription_error column: %s", e)
        return False


def _add_episode_priority() -> bool:
    """Add priority column to episode table (migration 033)."""
    import importlib.util
    import os
    from sqlmodel import Session
    from api.core.database import engine
    
    try:
        migration_path_033 = os.path.join(os.path.dirname(__file__), '033_add_episode_priority.py')
        spec_033 = importlib.util.spec_from_file_location('migration_033', migration_path_033)
        if spec_033 and spec_033.loader:
            module_033 = importlib.util.module_from_spec(spec_033)
            spec_033.loader.exec_module(module_033)
            with Session(engine) as session:
                module_033.run_migration(session)
        log.debug("[migrate] Episode priority column verified")
        return True
    except Exception as e:
        log.warning("[migrate] Episode priority migration failed: %s", e)
        return False


def _add_sms_notification_fields() -> bool:
    """Add SMS notification fields to user table (migration 035)."""
    import importlib.util
    import os
    from sqlmodel import Session
    from api.core.database import engine
    
    try:
        migration_path_035 = os.path.join(os.path.dirname(__file__), '035_add_sms_notification_fields.py')
        spec_035 = importlib.util.spec_from_file_location('migration_035', migration_path_035)
        if spec_035 and spec_035.loader:
            module_035 = importlib.util.module_from_spec(spec_035)
            spec_035.loader.exec_module(module_035)
            with Session(engine) as session:
                module_035.run_migration(session)
        log.debug("[migrate] SMS notification fields verified")
        return True
    except Exception as e:
        log.warning("[migrate] SMS notification fields migration failed: %s", e)
        return False


def _add_phone_verification_table() -> bool:
    """Add phone verification table (migration 036)."""
    import importlib.util
    import os
    from sqlmodel import Session
    from api.core.database import engine
    
    try:
        migration_path_036 = os.path.join(os.path.dirname(__file__), '036_add_phone_verification_table.py')
        spec_036 = importlib.util.spec_from_file_location('migration_036', migration_path_036)
        if spec_036 and spec_036.loader:
            module_036 = importlib.util.module_from_spec(spec_036)
            spec_036.loader.exec_module(module_036)
            with Session(engine) as session:
                module_036.run_migration(session)
        log.debug("[migrate] Phone verification table verified")
        return True
    except Exception as e:
        log.warning("[migrate] Phone verification table migration failed: %s", e)
        return False

