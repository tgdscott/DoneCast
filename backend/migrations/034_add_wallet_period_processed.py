"""
Migration 034: Add WalletPeriodProcessed table for rollover idempotency.

Creates walletperiodprocessed table to track which billing periods have been
processed for credit rollover, preventing double-processing.
"""
import logging
from sqlalchemy import text, inspect
from sqlmodel import Session

log = logging.getLogger(__name__)


def run_migration(session: Session) -> None:
    """Create walletperiodprocessed table (PostgreSQL ONLY)"""
    
    log.info("[migration_034] Starting wallet period processed table migration (PostgreSQL)...")
    
    try:
        # Check if table already exists
        bind = session.get_bind()
        inspector = inspect(bind)
        tables = inspector.get_table_names()
        
        if 'walletperiodprocessed' in tables:
            log.info("[migration_034] Wallet period processed table already exists, skipping...")
            return
        
        # Create walletperiodprocessed table
        log.info("[migration_034] Creating walletperiodprocessed table (PostgreSQL)...")
        session.execute(text("""
            CREATE TABLE walletperiodprocessed (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                period VARCHAR(7) NOT NULL UNIQUE,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_count INTEGER DEFAULT 0,
                rollover_total DOUBLE PRECISION DEFAULT 0.0
            )
        """))
        
        # Create index on period (already unique, but index helps lookups)
        log.info("[migration_034] Creating indexes...")
        session.execute(text("CREATE INDEX IF NOT EXISTS ix_walletperiodprocessed_period ON walletperiodprocessed (period)"))
        
        session.commit()
        
        log.info("[migration_034] ✅ Wallet period processed table created successfully")
        
    except Exception as e:
        log.error(f"[migration_034] ❌ Migration failed: {e}", exc_info=True)
        session.rollback()
        raise






