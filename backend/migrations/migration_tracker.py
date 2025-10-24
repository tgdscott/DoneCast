"""
MIGRATION TRACKER - Prevents re-running one-time migrations on every startup

Creates a simple tracking table to record completed migrations.
Once a migration runs successfully, it never runs again.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from sqlalchemy import text, inspect
from api.core.database import engine

log = logging.getLogger(__name__)


def _ensure_migration_tracker_table():
    """Create the migration_tracker table if it doesn't exist."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS migration_tracker (
                migration_name VARCHAR(255) PRIMARY KEY,
                executed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                success BOOLEAN NOT NULL DEFAULT TRUE
            )
        """))
        conn.commit()


def is_migration_completed(migration_name: str) -> bool:
    """Check if a migration has already been completed."""
    _ensure_migration_tracker_table()
    
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT success FROM migration_tracker WHERE migration_name = :name"),
            {"name": migration_name}
        )
        row = result.fetchone()
        return row is not None and row[0] is True


def mark_migration_completed(migration_name: str, success: bool = True):
    """Mark a migration as completed in the tracker."""
    _ensure_migration_tracker_table()
    
    with engine.connect() as conn:
        # Use UPSERT (INSERT ... ON CONFLICT) for PostgreSQL
        conn.execute(text("""
            INSERT INTO migration_tracker (migration_name, executed_at, success)
            VALUES (:name, :executed_at, :success)
            ON CONFLICT (migration_name) 
            DO UPDATE SET executed_at = :executed_at, success = :success
        """), {
            "name": migration_name,
            "executed_at": datetime.now(timezone.utc),
            "success": success
        })
        conn.commit()


def run_migration_once(migration_name: str, migration_func: callable) -> bool:
    """
    Run a migration only if it hasn't been completed before.
    
    Args:
        migration_name: Unique identifier for the migration
        migration_func: Function to execute (should return bool)
        
    Returns:
        True if migration completed or was already done
    """
    if is_migration_completed(migration_name):
        log.debug(f"[migration_tracker] {migration_name} already completed, skipping")
        return True
    
    try:
        log.info(f"[migration_tracker] Running {migration_name}...")
        result = migration_func()
        
        if result:
            mark_migration_completed(migration_name, success=True)
            log.info(f"[migration_tracker] ✅ {migration_name} completed successfully")
        else:
            log.warning(f"[migration_tracker] ⚠️ {migration_name} returned False")
        
        return result
    except Exception as e:
        log.error(f"[migration_tracker] ❌ {migration_name} failed: {e}")
        mark_migration_completed(migration_name, success=False)
        return False


def get_pending_migrations() -> list[str]:
    """Get list of migrations that have not completed successfully."""
    _ensure_migration_tracker_table()
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT migration_name 
            FROM migration_tracker 
            WHERE success = FALSE
        """))
        return [row[0] for row in result.fetchall()]
