"""
Migration 036: Add Phone Verification Table

Creates phoneverification table for phone number verification codes.
"""
import logging
from sqlalchemy import text, inspect
from sqlmodel import Session

log = logging.getLogger(__name__)


def run_migration(session: Session) -> None:
    """Create phoneverification table"""
    
    log.info("[migration_036] Starting phone verification table migration...")
    
    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        tables = inspector.get_table_names()
        
        if 'phoneverification' in tables:
            log.info("[migration_036] Phone verification table already exists, skipping...")
            return
        
        # Create phoneverification table
        log.info("[migration_036] Creating phoneverification table...")
        session.execute(text("""
            CREATE TABLE phoneverification (
                id UUID PRIMARY KEY,
                user_id UUID NOT NULL,
                phone_number VARCHAR(20) NOT NULL,
                code VARCHAR(6) NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                verified_at TIMESTAMP,
                used BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_phoneverification_user FOREIGN KEY (user_id) REFERENCES "user"(id)
            )
        """))
        
        # Create indexes
        log.info("[migration_036] Creating indexes...")
        session.execute(text("CREATE INDEX ix_phoneverification_user_id ON phoneverification (user_id)"))
        session.execute(text("CREATE INDEX ix_phoneverification_phone_number ON phoneverification (phone_number)"))
        session.execute(text("CREATE INDEX ix_phoneverification_code ON phoneverification (code)"))
        session.execute(text("CREATE INDEX ix_phoneverification_used ON phoneverification (used)"))
        
        session.commit()
        
        log.info("[migration_036] ✅ Phone verification table created successfully")
        
    except Exception as e:
        log.error(f"[migration_036] ❌ Migration failed: {e}", exc_info=True)
        session.rollback()
        raise



