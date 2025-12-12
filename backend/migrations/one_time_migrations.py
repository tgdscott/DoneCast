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
    results["ensure_user_trial_columns"] = run_migration_once("ensure_user_trial_columns", _ensure_user_trial_columns)
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
    results["add_credit_wallet"] = run_migration_once("add_credit_wallet", _add_credit_wallet)
    results["add_admin_action_log"] = run_migration_once("add_admin_action_log", _add_admin_action_log)
    results["add_wallet_period_processed"] = run_migration_once("add_wallet_period_processed", _add_wallet_period_processed)
    results["add_promo_code_support"] = run_migration_once("add_promo_code_support", _add_promo_code_support)
    results["add_affiliate_code_support"] = run_migration_once("add_affiliate_code_support", _add_affiliate_code_support)
    results["add_advanced_audio_processing"] = run_migration_once("add_advanced_audio_processing", _add_advanced_audio_processing)
    results["add_podcast_format"] = run_migration_once("add_podcast_format", _add_podcast_format)
    results["add_promo_code_discount_fields"] = run_migration_once("add_promo_code_discount_fields", _add_promo_code_discount_fields)
    results["add_promo_code_usage_tracking"] = run_migration_once("add_promo_code_usage_tracking", _add_promo_code_usage_tracking)
    results["add_mediaitem_auphonic_fields"] = run_migration_once("add_mediaitem_auphonic_fields", _add_mediaitem_auphonic_fields)
    results["add_mediaitem_use_auphonic"] = run_migration_once("add_mediaitem_use_auphonic", _add_mediaitem_use_auphonic)
    # Force run use_auphonic again with a new key to ensure it runs if the previous one failed silently or needs retry
    results["ensure_mediaitem_use_auphonic_v2"] = run_migration_once("ensure_mediaitem_use_auphonic_v2", _add_mediaitem_use_auphonic)
    results["backfill_transcript_words"] = run_migration_once("backfill_transcript_words", _backfill_transcript_words)
    results["fix_episode_213_cover"] = run_migration_once("fix_episode_213_cover", _fix_episode_213_cover)
    results["cleanup_orphaned_records"] = run_migration_once("cleanup_orphaned_records", _cleanup_orphaned_records)
    results["add_audio_threshold_label"] = run_migration_once("add_audio_threshold_label", _add_audio_threshold_label)
    results["add_audio_threshold_label"] = run_migration_once("add_audio_threshold_label", _add_audio_threshold_label)
    results["add_episode_length_management"] = run_migration_once("add_episode_length_management", _add_episode_length_management)
    results["add_ai_metadata_enum"] = run_migration_once("add_ai_metadata_enum", _add_ai_metadata_enum)
    
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


def _ensure_user_trial_columns() -> bool:
    """Ensure user table has trial tracking columns (PostgreSQL)."""
    try:
        inspector = inspect(engine)
        cols = {col["name"] for col in inspector.get_columns("user")}
    except Exception as e:
        log.warning("[migrate] Could not inspect user table for trial columns: %s", e)
        return False

    needed = {"trial_started_at", "trial_expires_at"}
    missing = needed - cols
    
    if not missing:
        log.debug("[migrate] user trial columns already exist, skipping")
        return True

    for col in missing:
        if col == "trial_started_at":
            stmt = 'ALTER TABLE "user" ADD COLUMN trial_started_at TIMESTAMP'
        elif col == "trial_expires_at":
            stmt = 'ALTER TABLE "user" ADD COLUMN trial_expires_at TIMESTAMP'
        else:
            log.warning("[migrate] Unknown trial column: %s", col)
            continue
        
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
            log.info("[migrate] ✅ Added user.%s column", col)
        except Exception as e:
            log.warning("[migrate] Could not add user.%s: %s", col, e)
            return False
    
    # Add index on trial_expires_at if column exists (whether just added or already existed)
    try:
        inspector = inspect(engine)
        final_cols = {col["name"] for col in inspector.get_columns("user")}
        if "trial_expires_at" in final_cols:
            indexes = {idx["name"] for idx in inspector.get_indexes("user")}
            # Check for any index on trial_expires_at (might have different naming)
            trial_indexes = [idx for idx in inspector.get_indexes("user") if "trial_expires_at" in str(idx.get("column_names", []))]
            if not trial_indexes:
                with engine.begin() as conn:
                    conn.execute(text('CREATE INDEX IF NOT EXISTS ix_user_trial_expires_at ON "user" (trial_expires_at)'))
                log.info("[migrate] ✅ Added index on user.trial_expires_at")
    except Exception as e:
        log.warning("[migrate] Could not add index on trial_expires_at: %s", e)
        # Don't fail the migration if index creation fails
    
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


def _add_credit_wallet() -> bool:
    """Add credit wallet table (migration 032)."""
    import importlib.util
    import os
    from sqlmodel import Session
    from api.core.database import engine
    
    try:
        migration_path_032 = os.path.join(os.path.dirname(__file__), '032_add_credit_wallet.py')
        spec_032 = importlib.util.spec_from_file_location('migration_032', migration_path_032)
        if spec_032 and spec_032.loader:
            module_032 = importlib.util.module_from_spec(spec_032)
            spec_032.loader.exec_module(module_032)
            with Session(engine) as session:
                module_032.run_migration(session)
        log.debug("[migrate] Credit wallet table verified")
        return True
    except Exception as e:
        log.warning("[migrate] Credit wallet migration failed: %s", e)
        return False


def _add_wallet_period_processed() -> bool:
    """Add wallet period processed table (migration 034)."""
    import importlib.util
    import os
    from sqlmodel import Session
    from api.core.database import engine
    
    try:
        migration_path_034 = os.path.join(os.path.dirname(__file__), '034_add_wallet_period_processed.py')
        spec_034 = importlib.util.spec_from_file_location('migration_034', migration_path_034)
        if spec_034 and spec_034.loader:
            module_034 = importlib.util.module_from_spec(spec_034)
            spec_034.loader.exec_module(module_034)
            with Session(engine) as session:
                module_034.run_migration(session)
        log.debug("[migrate] Wallet period processed table verified")
        return True
    except Exception as e:
        log.warning("[migrate] Wallet period processed migration failed: %s", e)
        return False


def _add_admin_action_log() -> bool:
    """Add admin action log table (migration 037)."""
    import importlib.util
    import os
    from sqlmodel import Session
    from api.core.database import engine
    
    try:
        migration_path_037 = os.path.join(os.path.dirname(__file__), '037_add_admin_action_log.py')
        spec_037 = importlib.util.spec_from_file_location('migration_037', migration_path_037)
        if spec_037 and spec_037.loader:
            module_037 = importlib.util.module_from_spec(spec_037)
            spec_037.loader.exec_module(module_037)
            with Session(engine) as session:
                module_037.run_migration(session)
        log.debug("[migrate] Admin action log table verified")
        return True
    except Exception as e:
        log.warning("[migrate] Admin action log migration failed: %s", e)
        return False


def _add_promo_code_support() -> bool:
    """Add promo code support (migration 038)."""
    import importlib.util
    import os
    from sqlmodel import Session
    from api.core.database import engine
    
    try:
        migration_path_038 = os.path.join(os.path.dirname(__file__), '038_add_promo_code_support.py')
        spec_038 = importlib.util.spec_from_file_location('migration_038', migration_path_038)
        if spec_038 and spec_038.loader:
            module_038 = importlib.util.module_from_spec(spec_038)
            spec_038.loader.exec_module(module_038)
            with Session(engine) as session:
                module_038.run_migration(session)
        log.debug("[migrate] Promo code support verified")
        return True
    except Exception as e:
        log.warning("[migrate] Promo code support migration failed: %s", e)
        return False


def _add_affiliate_code_support() -> bool:
    """Add affiliate code support (migration 039)."""
    import importlib.util
    import os
    from sqlmodel import Session
    from api.core.database import engine
    
    try:
        migration_path_039 = os.path.join(os.path.dirname(__file__), '039_add_affiliate_code_support.py')
        spec_039 = importlib.util.spec_from_file_location('migration_039', migration_path_039)
        if spec_039 and spec_039.loader:
            module_039 = importlib.util.module_from_spec(spec_039)
            spec_039.loader.exec_module(module_039)
            with Session(engine) as session:
                module_039.run_migration(session)
        log.debug("[migrate] Affiliate code support verified")
        return True
    except Exception as e:
        log.warning("[migrate] Affiliate code support migration failed: %s", e)
        return False


def _add_advanced_audio_processing() -> bool:
    """Add advanced audio processing flag to user table (migration 040)."""
    import importlib.util
    import os
    from sqlmodel import Session
    from api.core.database import engine
    
    try:
        migration_path_040 = os.path.join(os.path.dirname(__file__), '040_add_advanced_audio_flag.py')
        spec_040 = importlib.util.spec_from_file_location('migration_040', migration_path_040)
        if spec_040 and spec_040.loader:
            module_040 = importlib.util.module_from_spec(spec_040)
            spec_040.loader.exec_module(module_040)
            with Session(engine) as session:
                module_040.run_migration(session)
        log.debug("[migrate] Advanced audio processing flag verified")
        return True
    except Exception as e:
        log.warning("[migrate] Advanced audio processing migration failed: %s", e)
        return False


def _add_mediaitem_auphonic_fields() -> bool:
    """Add auphonic fields to MediaItem table (migration 011)."""
    try:
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("mediaitem")}
        
        needed = {
            "auphonic_processed",
            "auphonic_cleaned_audio_url",
            "auphonic_original_audio_url",
            "auphonic_output_file",
            "auphonic_metadata"
        }
        missing = needed - columns
        
        if not missing:
            log.debug("[migrate] MediaItem auphonic fields already exist")
            return True
        
        log.info(f"[migrate] Adding {len(missing)} missing auphonic fields to mediaitem table")
        with engine.begin() as conn:
            if "auphonic_processed" in missing:
                conn.execute(text("ALTER TABLE mediaitem ADD COLUMN IF NOT EXISTS auphonic_processed BOOLEAN DEFAULT FALSE"))
            if "auphonic_cleaned_audio_url" in missing:
                conn.execute(text("ALTER TABLE mediaitem ADD COLUMN IF NOT EXISTS auphonic_cleaned_audio_url TEXT"))
            if "auphonic_original_audio_url" in missing:
                conn.execute(text("ALTER TABLE mediaitem ADD COLUMN IF NOT EXISTS auphonic_original_audio_url TEXT"))
            if "auphonic_output_file" in missing:
                conn.execute(text("ALTER TABLE mediaitem ADD COLUMN IF NOT EXISTS auphonic_output_file TEXT"))
            if "auphonic_metadata" in missing:
                conn.execute(text("ALTER TABLE mediaitem ADD COLUMN IF NOT EXISTS auphonic_metadata TEXT"))
        
        log.info("[migrate] ✅ Added auphonic fields to mediaitem table")
        return True
    except Exception as e:
        log.error("[migrate] ❌ Failed to add auphonic fields to mediaitem: %s", e, exc_info=True)
        return False


def _add_mediaitem_use_auphonic() -> bool:
    """Add use_auphonic flag to MediaItem table (migration 044)."""
    try:
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("mediaitem")}
        
        if "use_auphonic" in columns:
            log.debug("[migrate] MediaItem.use_auphonic flag already exists")
            return True
        
        log.info("[migrate] Adding use_auphonic column to mediaitem table")
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE mediaitem ADD COLUMN use_auphonic BOOLEAN NOT NULL DEFAULT FALSE"))
        
        log.info("[migrate] ✅ Added use_auphonic column to mediaitem table")
        return True
    except Exception as e:
        log.error("[migrate] ❌ Failed to add use_auphonic to mediaitem: %s", e, exc_info=True)
        return False


def _add_podcast_format() -> bool:
    """Add format column to podcast table (migration 041)."""
    import importlib.util
    import os
    from sqlmodel import Session
    from api.core.database import engine
    
    try:
        migration_path_041 = os.path.join(os.path.dirname(__file__), '041_add_podcast_format.py')
        spec_041 = importlib.util.spec_from_file_location('migration_041', migration_path_041)
        if spec_041 and spec_041.loader:
            module_041 = importlib.util.module_from_spec(spec_041)
            spec_041.loader.exec_module(module_041)
            with Session(engine) as session:
                module_041.run_migration(session)
        log.debug("[migrate] Podcast format column verified")
        return True
    except Exception as e:
        log.warning("[migrate] Podcast format migration failed: %s", e)
        return False


def _add_promo_code_discount_fields() -> bool:
    """Add discount and credit fields to promo code table (migration 042)."""
    import importlib.util
    import os
    from sqlmodel import Session
    from api.core.database import engine
    
    try:
        migration_path_042 = os.path.join(os.path.dirname(__file__), '042_add_promo_code_discount_fields.py')
        spec_042 = importlib.util.spec_from_file_location('migration_042', migration_path_042)
        if spec_042 and spec_042.loader:
            module_042 = importlib.util.module_from_spec(spec_042)
            spec_042.loader.exec_module(module_042)
            with Session(engine) as session:
                module_042.run_migration(session)
        log.debug("[migrate] Promo code discount fields verified")
        return True
    except Exception as e:
        log.warning("[migrate] Promo code discount fields migration failed: %s", e)
        return False


def _add_promo_code_usage_tracking() -> bool:
    """Add promo code usage tracking table (migration 043)."""
    import importlib.util
    import os
    from sqlmodel import Session
    from api.core.database import engine
    
    try:
        migration_path_043 = os.path.join(os.path.dirname(__file__), '043_add_promo_code_usage_tracking.py')
        spec_043 = importlib.util.spec_from_file_location('migration_043', migration_path_043)
        if spec_043 and spec_043.loader:
            module_043 = importlib.util.module_from_spec(spec_043)
            spec_043.loader.exec_module(module_043)
            with Session(engine) as session:
                module_043.run_migration(session)
        log.debug("[migrate] Promo code usage tracking verified")
        return True
    except Exception as e:
        log.warning("[migrate] Promo code usage tracking migration failed: %s", e)
        return False


def _backfill_transcript_words() -> bool:
    """
    Backfill transcript words into MediaTranscript.transcript_meta_json for existing records.
    
    This migration downloads transcript JSON files from GCS and stores the words array
    directly in the database, enabling database-only transcript retrieval during assembly.
    
    Returns:
        True if migration completed successfully (or no records to migrate)
    """
    import json
    import os
    from pathlib import Path
    from sqlmodel import Session, select
    from api.core.database import engine
    from api.models.transcription import MediaTranscript
    
    try:
        with Session(engine) as session:
            # Find all MediaTranscript records that don't have words in metadata
            all_records = session.exec(select(MediaTranscript)).all()
            
            records_to_migrate = []
            for record in all_records:
                try:
                    meta = json.loads(record.transcript_meta_json or "{}")
                    words = meta.get("words")
                    # Check if words exist and is a non-empty list
                    if not words or not isinstance(words, list) or len(words) == 0:
                        records_to_migrate.append(record)
                except Exception:
                    # If JSON parsing fails, treat as needing migration
                    records_to_migrate.append(record)
            
            total_count = len(records_to_migrate)
            if total_count == 0:
                log.info("[migrate] ✅ No MediaTranscript records need word backfill - all have words in metadata")
                return True
            
            log.info(f"[migrate] 🔍 Found {total_count} MediaTranscript record(s) needing word backfill")
            
            # Try to download from GCS and backfill
            success_count = 0
            error_count = 0
            
            for i, record in enumerate(records_to_migrate, 1):
                try:
                    # Parse existing metadata
                    meta = json.loads(record.transcript_meta_json or "{}")
                    
                    # Get GCS location from metadata
                    gcs_bucket = meta.get("gcs_bucket") or os.getenv("TRANSCRIPTS_BUCKET") or os.getenv("MEDIA_BUCKET") or ""
                    gcs_key = meta.get("gcs_key")
                    gcs_uri = meta.get("gcs_json")
                    
                    if not gcs_bucket:
                        log.warning(f"[migrate] ⚠️ Record {record.id} ({record.filename}): No GCS bucket configured, skipping")
                        error_count += 1
                        continue
                    
                    # Determine GCS key - try multiple strategies
                    gcs_key = None
                    filename_str = str(record.filename)
                    
                    # Strategy 1: Use gcs_key from metadata
                    if not gcs_key:
                        gcs_key = meta.get("gcs_key")
                    
                    # Strategy 2: Extract from gcs_uri
                    if not gcs_key and gcs_uri:
                        if gcs_uri.startswith("gs://"):
                            parts = gcs_uri[5:].split("/", 1)
                            if len(parts) == 2:
                                gcs_key = parts[1]
                    
                    # Strategy 3: Use sanitize_filename (how transcripts are actually stored)
                    if not gcs_key:
                        try:
                            from api.services.audio.common import sanitize_filename
                            stem = Path(record.filename).stem
                            safe_stem = sanitize_filename(stem) or stem.replace(" ", "_").replace("/", "_")
                            gcs_key = f"transcripts/{safe_stem}.json"
                            log.info(f"[migrate] 🔍 Constructed GCS key using sanitize_filename: {gcs_key}")
                        except Exception:
                            stem = Path(record.filename).stem
                            safe_stem = stem.replace(" ", "_").replace("/", "_")
                            gcs_key = f"transcripts/{safe_stem}.json"
                            log.info(f"[migrate] 🔍 Constructed simple GCS key: {gcs_key}")
                    
                    # Download transcript from GCS - try multiple key patterns
                    log.info(f"[migrate] 📥 [{i}/{total_count}] Searching for transcript in GCS bucket: {gcs_bucket}")
                    
                    try:
                        from google.cloud import storage
                        from api.services.audio.common import sanitize_filename
                        client = storage.Client()
                        bucket_obj = client.bucket(gcs_bucket)
                        
                        stem = Path(record.filename).stem
                        try:
                            safe_stem = sanitize_filename(stem) or stem.replace(" ", "_").replace("/", "_")
                        except Exception:
                            safe_stem = stem.replace(" ", "_").replace("/", "_")
                        
                        # Build candidate keys to try
                        candidate_keys = []
                        if gcs_key:
                            candidate_keys.append(gcs_key)
                        candidate_keys.extend([
                            f"transcripts/{safe_stem}.json",
                            f"transcripts/{stem}.json",
                            f"transcripts/{Path(record.filename).name}.json",
                        ])
                        
                        # Also try with user_id path if we can extract it from filename
                        if filename_str.startswith("gs://"):
                            parts = filename_str[5:].split("/")
                            if len(parts) >= 2:
                                user_id_part = parts[1]  # user_id is typically the second part
                                candidate_keys.extend([
                                    f"transcripts/{user_id_part}/{safe_stem}.json",
                                    f"transcripts/{user_id_part}/{stem}.json",
                                ])
                        
                        # Remove duplicates while preserving order
                        seen = set()
                        unique_candidates = []
                        for key in candidate_keys:
                            if key and key not in seen:
                                seen.add(key)
                                unique_candidates.append(key)
                        
                        log.info(f"[migrate] 🔍 Trying {len(unique_candidates)} candidate keys: {unique_candidates[:3]}...")
                        
                        blob = None
                        found_key = None
                        for candidate_key in unique_candidates:
                            candidate_blob = bucket_obj.blob(candidate_key)
                            if candidate_blob.exists():
                                blob = candidate_blob
                                found_key = candidate_key
                                log.info(f"[migrate] ✅ Found transcript at: {candidate_key}")
                                break
                        
                        # Last resort: List all transcripts and try to match by stem
                        if not blob:
                            log.info(f"[migrate] 🔍 Listing transcripts in bucket to find match for stem '{stem}'...")
                            try:
                                blobs_list = list(bucket_obj.list_blobs(prefix="transcripts/"))
                                log.info(f"[migrate] 🔍 Found {len(blobs_list)} transcript(s) in bucket")
                                for candidate_blob in blobs_list:
                                    blob_name = candidate_blob.name
                                    # Check if blob name contains the stem (case-insensitive)
                                    if stem.lower() in blob_name.lower() or safe_stem.lower() in blob_name.lower():
                                        blob = candidate_blob
                                        found_key = blob_name
                                        log.info(f"[migrate] ✅ Found transcript by listing (stem match): {blob_name}")
                                        break
                            except Exception as list_err:
                                log.warning(f"[migrate] Failed to list transcripts: {list_err}")
                            
                            if not blob:
                                log.warning(f"[migrate] ⚠️ Record {record.id} ({record.filename}): Transcript not found in GCS. Tried keys: {unique_candidates[:5]}")
                                error_count += 1
                                continue
                        
                        # Download transcript JSON
                        transcript_data = blob.download_as_bytes()
                        if not transcript_data:
                            log.warning(f"[migrate] ⚠️ Record {record.id} ({record.filename}): Empty transcript file in GCS")
                            error_count += 1
                            continue
                        
                        # Parse transcript JSON
                        words = json.loads(transcript_data.decode("utf-8"))
                        
                        if not isinstance(words, list) or len(words) == 0:
                            log.warning(f"[migrate] ⚠️ Record {record.id} ({record.filename}): Transcript has no words (empty or invalid format)")
                            error_count += 1
                            continue
                        
                        # Update metadata with words
                        meta["words"] = words
                        record.transcript_meta_json = json.dumps(meta, ensure_ascii=False)
                        
                        session.add(record)
                        session.commit()
                        
                        success_count += 1
                        log.info(f"[migrate] ✅ [{i}/{total_count}] Backfilled {len(words)} words for record {record.id} ({record.filename})")
                        
                    except Exception as gcs_err:
                        log.error(f"[migrate] ❌ Record {record.id} ({record.filename}): GCS download failed: {gcs_err}", exc_info=True)
                        error_count += 1
                        continue
                        
                except Exception as record_err:
                    log.error(f"[migrate] ❌ Record {record.id}: Migration failed: {record_err}", exc_info=True)
                    error_count += 1
                    continue
            
            # Summary
            log.info(f"[migrate] 📊 Backfill complete: {success_count} succeeded, {error_count} failed out of {total_count} total")
            
            if success_count > 0:
                log.info(f"[migrate] ✅ Successfully backfilled words for {success_count} transcript(s)")
            
            if error_count > 0:
                log.warning(f"[migrate] ⚠️ Failed to backfill {error_count} transcript(s) - they may need manual review")
            
            # Return True if at least some succeeded (partial success is acceptable)
            return success_count > 0 or total_count == 0
            
    except Exception as e:
        log.error(f"[migrate] ❌ Transcript word backfill migration failed: {e}", exc_info=True)
        return False


def _fix_episode_213_cover() -> bool:
    """Fix episode 213 cover - checks if already fixed, otherwise skips (manual upload required)."""
    try:
        from sqlmodel import Session, select
        from api.core.database import get_session
        from api.models.podcast import Podcast, Episode
        
        session: Session = next(get_session())
        
        # Find Cinema IRL podcast
        podcast = session.exec(select(Podcast).where(Podcast.name == "Cinema IRL")).first()
        if not podcast:
            log.warning("[migrate] Cinema IRL podcast not found, skipping episode 213 cover fix")
            return False
        
        # Find episode 213
        episode = session.exec(
            select(Episode)
            .where(Episode.podcast_id == podcast.id)
            .where(Episode.episode_number == 213)
        ).first()
        
        if not episode:
            log.warning("[migrate] Episode 213 not found, skipping cover fix")
            return False
        
        # Check if already fixed
        if episode.gcs_cover_path and (
            str(episode.gcs_cover_path).startswith("https://") and ".r2.cloudflarestorage.com" in str(episode.gcs_cover_path)
            or str(episode.gcs_cover_path).startswith("r2://")
        ):
            log.debug("[migrate] Episode 213 already has R2 cover URL, skipping")
            return True
        
        # Not fixed yet - log that manual upload is needed
        log.info("[migrate] Episode 213 cover needs manual upload. Use upload_episode_213_cover.py script to fix.")
        return False
        
    except Exception as e:
        log.error(f"[migrate] ❌ Episode 213 cover fix migration check failed: {e}", exc_info=True)
        return False


def _cleanup_orphaned_records() -> bool:
    """
    Detect and report orphaned records that escaped deletion.
    
    This migration checks for:
    - Episodes without valid podcast_id
    - EpisodeSections without valid podcast_id or episode_id
    - MediaItems without valid user_id
    - Templates without valid podcast_id
    - PodcastWebsites without valid podcast_id
    - PodcastDistributionStatus without valid podcast_id
    
    Returns:
        True if check completed (even if orphaned records found)
    """
    try:
        from sqlmodel import Session, select, text
        from api.core.database import get_session
        from api.models.podcast import (
            Podcast, Episode, EpisodeSection, MediaItem, 
            PodcastTemplate, PodcastDistributionStatus
        )
        from api.models.user import User
        
        session: Session = next(get_session())
        
        orphaned_count = 0
        orphaned_details = []
        
        # 1. Check episodes without valid podcast_id
        try:
            episodes_query = text("""
                SELECT e.id, e.title, e.podcast_id, e.user_id
                FROM episode e
                LEFT JOIN podcast p ON e.podcast_id = p.id
                WHERE p.id IS NULL
            """)
            orphaned_episodes = session.execute(episodes_query).fetchall()
            if orphaned_episodes:
                count = len(orphaned_episodes)
                orphaned_count += count
                orphaned_details.append(f"Episodes without valid podcast_id: {count}")
                log.warning(f"[cleanup] Found {count} orphaned episodes")
                for ep in orphaned_episodes[:10]:  # Log first 10
                    log.warning(f"[cleanup]   - Episode {ep[0]} ({ep[1]}) podcast_id={ep[2]} user_id={ep[3]}")
        except Exception as e:
            log.warning(f"[cleanup] Failed to check orphaned episodes: {e}")
        
        # 2. Check episodes without valid user_id
        try:
            episodes_no_user_query = text("""
                SELECT e.id, e.title, e.podcast_id, e.user_id
                FROM episode e
                LEFT JOIN "user" u ON e.user_id = u.id
                WHERE u.id IS NULL
            """)
            orphaned_episodes_user = session.execute(episodes_no_user_query).fetchall()
            if orphaned_episodes_user:
                count = len(orphaned_episodes_user)
                orphaned_count += count
                orphaned_details.append(f"Episodes without valid user_id: {count}")
                log.warning(f"[cleanup] Found {count} episodes without valid user_id")
        except Exception as e:
            log.warning(f"[cleanup] Failed to check episodes without user_id: {e}")
        
        # 3. Check episode sections without valid podcast_id
        try:
            sections_query = text("""
                SELECT es.id, es.tag, es.podcast_id, es.episode_id
                FROM episodesection es
                LEFT JOIN podcast p ON es.podcast_id = p.id
                WHERE p.id IS NULL
            """)
            orphaned_sections = session.execute(sections_query).fetchall()
            if orphaned_sections:
                count = len(orphaned_sections)
                orphaned_count += count
                orphaned_details.append(f"EpisodeSections without valid podcast_id: {count}")
                log.warning(f"[cleanup] Found {count} orphaned episode sections")
        except Exception as e:
            log.warning(f"[cleanup] Failed to check orphaned episode sections: {e}")
        
        # 4. Check episode sections without valid episode_id (but episode_id is not null)
        try:
            sections_episode_query = text("""
                SELECT es.id, es.tag, es.podcast_id, es.episode_id
                FROM episodesection es
                WHERE es.episode_id IS NOT NULL
                AND NOT EXISTS (SELECT 1 FROM episode e WHERE e.id = es.episode_id)
            """)
            orphaned_sections_ep = session.execute(sections_episode_query).fetchall()
            if orphaned_sections_ep:
                count = len(orphaned_sections_ep)
                orphaned_count += count
                orphaned_details.append(f"EpisodeSections with invalid episode_id: {count}")
                log.warning(f"[cleanup] Found {count} episode sections with invalid episode_id")
        except Exception as e:
            log.warning(f"[cleanup] Failed to check episode sections with invalid episode_id: {e}")
        
        # 5. Check media items without valid user_id
        try:
            media_query = text("""
                SELECT m.id, m.filename, m.category, m.user_id
                FROM mediaitem m
                LEFT JOIN "user" u ON m.user_id = u.id
                WHERE u.id IS NULL
            """)
            orphaned_media = session.execute(media_query).fetchall()
            if orphaned_media:
                count = len(orphaned_media)
                orphaned_count += count
                orphaned_details.append(f"MediaItems without valid user_id: {count}")
                log.warning(f"[cleanup] Found {count} orphaned media items")
        except Exception as e:
            log.warning(f"[cleanup] Failed to check orphaned media items: {e}")
        
        # 6. Check templates without valid podcast_id (but podcast_id is not null)
        try:
            templates_query = text("""
                SELECT t.id, t.name, t.podcast_id, t.user_id
                FROM podcasttemplate t
                WHERE t.podcast_id IS NOT NULL
                AND NOT EXISTS (SELECT 1 FROM podcast p WHERE p.id = t.podcast_id)
            """)
            orphaned_templates = session.execute(templates_query).fetchall()
            if orphaned_templates:
                count = len(orphaned_templates)
                orphaned_count += count
                orphaned_details.append(f"Templates with invalid podcast_id: {count}")
                log.warning(f"[cleanup] Found {count} templates with invalid podcast_id")
        except Exception as e:
            log.warning(f"[cleanup] Failed to check orphaned templates: {e}")
        
        # 7. Check podcast websites without valid podcast_id
        try:
            websites_query = text("""
                SELECT w.id, w.podcast_id, w.status
                FROM podcastwebsite w
                LEFT JOIN podcast p ON w.podcast_id = p.id
                WHERE p.id IS NULL
            """)
            orphaned_websites = session.execute(websites_query).fetchall()
            if orphaned_websites:
                count = len(orphaned_websites)
                orphaned_count += count
                orphaned_details.append(f"PodcastWebsites without valid podcast_id: {count}")
                log.warning(f"[cleanup] Found {count} orphaned podcast websites")
        except Exception as e:
            log.warning(f"[cleanup] Failed to check orphaned podcast websites: {e}")
        
        # 8. Check distribution status without valid podcast_id
        try:
            dist_query = text("""
                SELECT d.id, d.podcast_id, d.platform_key
                FROM podcastdistributionstatus d
                LEFT JOIN podcast p ON d.podcast_id = p.id
                WHERE p.id IS NULL
            """)
            orphaned_dist = session.execute(dist_query).fetchall()
            if orphaned_dist:
                count = len(orphaned_dist)
                orphaned_count += count
                orphaned_details.append(f"PodcastDistributionStatus without valid podcast_id: {count}")
                log.warning(f"[cleanup] Found {count} orphaned distribution status records")
        except Exception as e:
            log.warning(f"[cleanup] Failed to check orphaned distribution status: {e}")
        
        # 9. CRITICAL: Delete episodes without valid podcast_id (data integrity violation)
        # You cannot have an episode without a show - these must be deleted
        try:
            episodes_no_podcast_query = text("""
                SELECT e.id, e.title, e.podcast_id, e.user_id
                FROM episode e
                LEFT JOIN podcast p ON e.podcast_id = p.id
                WHERE p.id IS NULL
            """)
            orphaned_episodes_no_podcast = session.execute(episodes_no_podcast_query).fetchall()
            if orphaned_episodes_no_podcast:
                count = len(orphaned_episodes_no_podcast)
                log.error(f"[cleanup] ⚠️ CRITICAL: Found {count} episodes without valid podcast_id - these will be deleted")
                log.error("[cleanup] Episodes cannot exist without a podcast - deleting orphaned episodes...")
                
                # Delete these episodes (they're invalid data)
                for ep_row in orphaned_episodes_no_podcast:
                    ep_id = ep_row[0]
                    ep_title = ep_row[1]
                    try:
                        # Delete episode and cascade to related records
                        delete_stmt = text("DELETE FROM episode WHERE id = :ep_id")
                        session.execute(delete_stmt, {"ep_id": ep_id})
                        log.warning(f"[cleanup] Deleted orphaned episode {ep_id} ({ep_title}) - no valid podcast")
                    except Exception as del_err:
                        log.error(f"[cleanup] Failed to delete orphaned episode {ep_id}: {del_err}")
                
                # Commit deletions
                try:
                    session.commit()
                    log.info(f"[cleanup] ✅ Deleted {count} orphaned episodes without podcasts")
                    orphaned_details.append(f"DELETED: {count} episodes without valid podcast_id")
                except Exception as commit_err:
                    log.error(f"[cleanup] Failed to commit episode deletions: {commit_err}")
                    session.rollback()
        except Exception as e:
            log.error(f"[cleanup] Failed to cleanup episodes without podcasts: {e}", exc_info=True)
        
        # Summary
        if orphaned_count > 0:
            log.error(f"[cleanup] ⚠️ Found {orphaned_count} total orphaned records:")
            for detail in orphaned_details:
                log.error(f"[cleanup]   - {detail}")
            log.error("[cleanup] Review logs above and manually delete orphaned records using admin endpoints")
            log.error("[cleanup] Or run SQL cleanup queries (see migration code for examples)")
            return True  # Migration completed, but orphaned records exist
        else:
            log.info("[cleanup] ✅ No orphaned records found - database is clean")
            return True
            
    except Exception as e:
        log.error(f"[cleanup] ❌ Orphaned records check failed: {e}", exc_info=True)
        return False


def _add_audio_threshold_label() -> bool:
    """Add audio_processing_threshold_label column to user table (migration 101)."""
    import importlib.util
    import os
    
    try:
        migration_path_101 = os.path.join(os.path.dirname(__file__), '101_add_audio_threshold_label.py')
        spec_101 = importlib.util.spec_from_file_location('migration_101', migration_path_101)
        if spec_101 and spec_101.loader:
            module_101 = importlib.util.module_from_spec(spec_101)
            spec_101.loader.exec_module(module_101)
            module_101.upgrade()
        log.debug("[migrate] Audio threshold label column verified")
        return True
    except Exception as e:
        log.warning("[migrate] Audio threshold label migration failed: %s", e)
        return False


def _add_episode_length_management() -> bool:
    """Add episode length management fields to templates and users (migration 102)."""
    import importlib.util
    import os
    
    try:
        migration_path_102 = os.path.join(os.path.dirname(__file__), '102_add_episode_length_management.py')
        spec_102 = importlib.util.spec_from_file_location('migration_102', migration_path_102)
        if spec_102 and spec_102.loader:
            module_102 = importlib.util.module_from_spec(spec_102)
            spec_102.loader.exec_module(module_102)
            from sqlmodel import Session
            from api.core.database import engine
            with Session(engine) as session:
                module_102.migrate(session)
        log.debug("[migrate] Episode length management fields verified")
        return True
    except Exception as e:
        log.warning("[migrate] Episode length management migration failed: %s", e)
        return False


def _add_ai_metadata_enum() -> bool:
    """Add AI_METADATA_GENERATION to ledgerreason enum (migration 103)."""
    import importlib.util
    import os
    
    try:
        migration_path = os.path.join(os.path.dirname(__file__), '103_add_ai_metadata_enum.py')
        spec = importlib.util.spec_from_file_location('migration_103', migration_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.upgrade()
        log.debug("[migrate] AI Metadata Enum migration completed")
        return True
    except Exception as e:
        log.warning("[migrate] AI Metadata Enum migration failed: %s", e)
        return False
