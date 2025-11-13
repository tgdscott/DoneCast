"""
Migration 037: Add Admin Action Log Table

Creates adminactionlog table for tracking refund approvals/denials and credit awards.
"""
import logging
from sqlalchemy import text, inspect
from sqlmodel import Session

log = logging.getLogger(__name__)


def run_migration(session: Session) -> None:
    """Create adminactionlog table (PostgreSQL ONLY)"""
    
    log.info("[migration_037] Starting admin action log table migration (PostgreSQL)...")
    
    try:
        # Check if table already exists
        bind = session.get_bind()
        inspector = inspect(bind)
        tables = inspector.get_table_names()
        
        if 'adminactionlog' in tables:
            log.info("[migration_037] Admin action log table already exists, skipping...")
            return
        
        # Create adminactionlog table
        log.info("[migration_037] Creating adminactionlog table (PostgreSQL)...")
        session.execute(text("""
            CREATE TABLE adminactionlog (
                id SERIAL PRIMARY KEY,
                action_type VARCHAR(50) NOT NULL,
                admin_user_id UUID NOT NULL,
                target_user_id UUID NOT NULL,
                refund_notification_id UUID,
                refund_amount DOUBLE PRECISION,
                refund_entry_ids TEXT,
                denial_reason TEXT,
                credit_amount DOUBLE PRECISION,
                award_reason TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Create indexes
        log.info("[migration_037] Creating indexes...")
        session.execute(text("CREATE INDEX ix_adminactionlog_action_type ON adminactionlog (action_type)"))
        session.execute(text("CREATE INDEX ix_adminactionlog_admin_user_id ON adminactionlog (admin_user_id)"))
        session.execute(text("CREATE INDEX ix_adminactionlog_target_user_id ON adminactionlog (target_user_id)"))
        session.execute(text("CREATE INDEX ix_adminactionlog_created_at ON adminactionlog (created_at)"))
        session.execute(text("CREATE INDEX idx_admin_action_log_type_created ON adminactionlog (action_type, created_at)"))
        session.execute(text("CREATE INDEX idx_admin_action_log_admin_created ON adminactionlog (admin_user_id, created_at)"))
        session.execute(text("CREATE INDEX idx_admin_action_log_target_created ON adminactionlog (target_user_id, created_at)"))
        
        session.commit()
        
        log.info("[migration_037] ✅ Admin action log table created successfully")
        
    except Exception as e:
        log.error(f"[migration_037] ❌ Migration failed: {e}", exc_info=True)
        session.rollback()
        raise



