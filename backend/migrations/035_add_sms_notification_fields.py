"""
Migration 035: Add SMS Notification Fields to User Table

Adds phone number and SMS notification preference fields to the user table.
"""
import logging
from sqlalchemy import text, inspect
from sqlmodel import Session

log = logging.getLogger(__name__)


def run_migration(session: Session) -> None:
    """Add SMS notification fields to user table"""
    
    log.info("[migration_035] Starting SMS notification fields migration...")
    
    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        columns = {col['name']: col for col in inspector.get_columns('user')}
        
        # Add phone_number column
        if 'phone_number' not in columns:
            log.info("[migration_035] Adding phone_number column...")
            session.execute(text("""
                ALTER TABLE "user"
                ADD COLUMN phone_number VARCHAR(20)
            """))
            log.info("[migration_035] ✅ Added phone_number column")
        else:
            log.info("[migration_035] phone_number column already exists, skipping...")
        
        # Add sms_notifications_enabled column
        if 'sms_notifications_enabled' not in columns:
            log.info("[migration_035] Adding sms_notifications_enabled column...")
            session.execute(text("""
                ALTER TABLE "user"
                ADD COLUMN sms_notifications_enabled BOOLEAN DEFAULT FALSE
            """))
            log.info("[migration_035] ✅ Added sms_notifications_enabled column")
        else:
            log.info("[migration_035] sms_notifications_enabled column already exists, skipping...")
        
        # Add sms_notify_transcription_ready column
        if 'sms_notify_transcription_ready' not in columns:
            log.info("[migration_035] Adding sms_notify_transcription_ready column...")
            session.execute(text("""
                ALTER TABLE "user"
                ADD COLUMN sms_notify_transcription_ready BOOLEAN DEFAULT FALSE
            """))
            log.info("[migration_035] ✅ Added sms_notify_transcription_ready column")
        else:
            log.info("[migration_035] sms_notify_transcription_ready column already exists, skipping...")
        
        # Add sms_notify_publish column
        if 'sms_notify_publish' not in columns:
            log.info("[migration_035] Adding sms_notify_publish column...")
            session.execute(text("""
                ALTER TABLE "user"
                ADD COLUMN sms_notify_publish BOOLEAN DEFAULT FALSE
            """))
            log.info("[migration_035] ✅ Added sms_notify_publish column")
        else:
            log.info("[migration_035] sms_notify_publish column already exists, skipping...")
        
        # Add sms_notify_worker_down column
        if 'sms_notify_worker_down' not in columns:
            log.info("[migration_035] Adding sms_notify_worker_down column...")
            session.execute(text("""
                ALTER TABLE "user"
                ADD COLUMN sms_notify_worker_down BOOLEAN DEFAULT FALSE
            """))
            log.info("[migration_035] ✅ Added sms_notify_worker_down column")
        else:
            log.info("[migration_035] sms_notify_worker_down column already exists, skipping...")
        
        session.commit()
        
        log.info("[migration_035] ✅ SMS notification fields migration completed successfully")
        
    except Exception as e:
        log.error(f"[migration_035] ❌ Migration failed: {e}", exc_info=True)
        session.rollback()
        raise



