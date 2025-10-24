"""
Migration 028: Add Credits Field to ProcessingMinutesLedger (PostgreSQL ONLY)

Adds:
- credits (float) column - precise credit amount with multipliers
- cost_breakdown_json (str) column - JSON cost calculation details

Backfills existing records with 1.5x minute conversion.

NOTE: SQLite is NO LONGER SUPPORTED. This migration ONLY works with PostgreSQL.
"""
import json
import logging
from sqlalchemy import text, inspect
from sqlmodel import Session

log = logging.getLogger(__name__)


def run_migration(session: Session) -> None:
    """Add credits field and backfill existing data (PostgreSQL ONLY)"""
    
    log.info("[migration_028] Starting credits field migration (PostgreSQL)...")
    
    try:
        # Check if credits column already exists using SQLAlchemy inspector
        bind = session.get_bind()
        inspector = inspect(bind)
        columns = {col['name'] for col in inspector.get_columns('processingminutesledger')}
        
        if 'credits' in columns:
            log.info("[migration_028] Credits column already exists, skipping...")
            return
        
        # Add credits column (default 0.0) - PostgreSQL ONLY
        log.info("[migration_028] Adding credits column (PostgreSQL)...")
        session.execute(text(
            "ALTER TABLE processingminutesledger ADD COLUMN credits DOUBLE PRECISION DEFAULT 0.0"
        ))
        
        # Add cost_breakdown_json column (nullable) - PostgreSQL ONLY
        log.info("[migration_028] Adding cost_breakdown_json column (PostgreSQL)...")
        session.execute(text(
            "ALTER TABLE processingminutesledger ADD COLUMN cost_breakdown_json VARCHAR"
        ))
        
        session.commit()
        
        # Backfill existing records with 1.5x conversion
        log.info("[migration_028] Backfilling existing records with credits (1.5x minutes)...")
        
        # Get count of records to backfill
        count_result = session.execute(text(
            "SELECT COUNT(*) FROM processingminutesledger WHERE credits = 0.0"
        ))
        count = count_result.scalar() or 0
        log.info(f"[migration_028] Found {count} records to backfill")
        
        if count > 0:
            # Update credits = minutes * 1.5
            session.execute(text(
                "UPDATE processingminutesledger SET credits = minutes * 1.5 WHERE credits = 0.0"
            ))
            
            # Add simple cost breakdown for backfilled records
            breakdown = json.dumps({
                "base_credits": "calculated_from_minutes",
                "multiplier": 1.5,
                "source": "backfill_migration_028"
            })
            
            session.execute(text(
                f"UPDATE processingminutesledger SET cost_breakdown_json = :breakdown WHERE cost_breakdown_json IS NULL"
            ), {"breakdown": breakdown})
            
            session.commit()
            log.info(f"[migration_028] ✅ Backfilled {count} records with credits")
        
        log.info("[migration_028] ✅ Credits field migration completed successfully")
        
    except Exception as e:
        log.error(f"[migration_028] ❌ Migration failed: {e}")
        session.rollback()
        raise


__all__ = ["run_migration"]
