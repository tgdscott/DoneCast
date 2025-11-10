"""
Migration 032: Add Credit Wallet Table

Creates creditwallet table for tracking monthly, purchased, and rollover credits per billing period.

PostgreSQL ONLY.
"""
import logging
from sqlalchemy import text, inspect
from sqlmodel import Session

log = logging.getLogger(__name__)


def run_migration(session: Session) -> None:
    """Create creditwallet table (PostgreSQL ONLY)"""
    
    log.info("[migration_032] Starting credit wallet table migration (PostgreSQL)...")
    
    try:
        # Check if table already exists
        bind = session.get_bind()
        inspector = inspect(bind)
        tables = inspector.get_table_names()
        
        if 'creditwallet' in tables:
            log.info("[migration_032] Credit wallet table already exists, skipping...")
            return
        
        # Create creditwallet table
        log.info("[migration_032] Creating creditwallet table (PostgreSQL)...")
        session.execute(text("""
            CREATE TABLE creditwallet (
                id UUID PRIMARY KEY,
                user_id UUID NOT NULL,
                period VARCHAR(7) NOT NULL,
                monthly_credits DOUBLE PRECISION DEFAULT 0.0,
                rollover_credits DOUBLE PRECISION DEFAULT 0.0,
                purchased_credits DOUBLE PRECISION DEFAULT 0.0,
                used_credits DOUBLE PRECISION DEFAULT 0.0,
                used_monthly_rollover DOUBLE PRECISION DEFAULT 0.0,
                used_purchased DOUBLE PRECISION DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_wallet_user_period UNIQUE (user_id, period)
            )
        """))
        
        # Create indexes
        log.info("[migration_032] Creating indexes...")
        session.execute(text("CREATE INDEX ix_creditwallet_user_id ON creditwallet (user_id)"))
        session.execute(text("CREATE INDEX ix_creditwallet_period ON creditwallet (period)"))
        
        session.commit()
        
        log.info("[migration_032] ✅ Credit wallet table created successfully")
        
    except Exception as e:
        log.error(f"[migration_032] ❌ Migration failed: {e}", exc_info=True)
        session.rollback()
        raise

