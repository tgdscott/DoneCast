"""
Migration 030: Optimize ProcessingMinutesLedger for Invoice Queries

Ensures proper indexing for credit ledger invoice-style queries:
- episode_id index (already exists, verify)
- created_at index for time-based filtering
- Composite index on (user_id, episode_id, created_at) for episode invoice queries

NOTE: PostgreSQL only (SQLite no longer supported)
"""
import logging
from sqlalchemy import text, inspect
from sqlmodel import Session

log = logging.getLogger(__name__)


def run_migration(session: Session) -> None:
    """Optimize indexes for credit ledger invoice queries"""
    
    log.info("[migration_030] Starting ledger index optimization...")
    
    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        
        # Get existing indexes
        indexes = {idx['name']: idx for idx in inspector.get_indexes('processingminutesledger')}
        
        # 1. Ensure created_at has an index for time-based queries
        if 'ix_processingminutesledger_created_at' not in indexes:
            log.info("[migration_030] Creating index on created_at...")
            session.execute(text(
                "CREATE INDEX ix_processingminutesledger_created_at "
                "ON processingminutesledger (created_at)"
            ))
            session.commit()
            log.info("[migration_030] ✅ Created created_at index")
        else:
            log.info("[migration_030] created_at index already exists")
        
        # 2. Create composite index for efficient episode invoice queries
        # This speeds up: "SELECT * FROM ledger WHERE user_id=X AND episode_id=Y ORDER BY created_at DESC"
        composite_idx_name = 'ix_ledger_user_episode_time'
        if composite_idx_name not in indexes:
            log.info("[migration_030] Creating composite index for episode invoices...")
            session.execute(text(
                f"CREATE INDEX {composite_idx_name} "
                "ON processingminutesledger (user_id, episode_id, created_at DESC)"
            ))
            session.commit()
            log.info(f"[migration_030] ✅ Created composite index {composite_idx_name}")
        else:
            log.info(f"[migration_030] Composite index {composite_idx_name} already exists")
        
        # 3. Verify episode_id index exists (should be created by SQLModel Field(index=True))
        episode_idx_exists = any('episode_id' in idx['name'] for idx in indexes.values())
        if episode_idx_exists:
            log.info("[migration_030] ✅ episode_id index verified")
        else:
            log.warning("[migration_030] ⚠️ episode_id index not found (should exist from model definition)")
            # Create it manually if missing
            session.execute(text(
                "CREATE INDEX ix_processingminutesledger_episode_id "
                "ON processingminutesledger (episode_id)"
            ))
            session.commit()
            log.info("[migration_030] ✅ Created missing episode_id index")
        
        log.info("[migration_030] ✅ Ledger index optimization completed successfully")
        
    except Exception as e:
        log.error(f"[migration_030] ❌ Migration failed: {e}")
        session.rollback()
        raise


__all__ = ["run_migration"]
