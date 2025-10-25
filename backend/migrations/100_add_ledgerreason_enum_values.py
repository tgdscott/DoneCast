"""
Migration: Add missing LedgerReason enum values to database
Created: 2024-10-24
Fixes: psycopg.errors.InvalidTextRepresentation for TRANSCRIPTION, ASSEMBLY, etc.

CRITICAL: This fixes the database enum mismatch that causes container crashes
when trying to debit credits for transcription/assembly/storage operations.
"""

from sqlalchemy import text
from api.core.database import engine
from api.core.logging_config import get_logger

logger = get_logger(__name__)


def upgrade():
    """Add missing enum values to ledgerreason type in PostgreSQL"""
    
    enum_values_to_add = [
        'TRANSCRIPTION',
        'ASSEMBLY', 
        'STORAGE',
        'AUPHONIC_PROCESSING',
        'TTS_GENERATION'
    ]
    
    with engine.connect() as conn:
        # Check which values already exist
        result = conn.execute(text("""
            SELECT enumlabel 
            FROM pg_enum 
            WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'ledgerreason')
        """))
        existing_values = {row[0] for row in result}
        
        logger.info(f"[MIGRATION 100] Existing ledgerreason enum values: {existing_values}")
        
        # Add missing values
        for value in enum_values_to_add:
            if value not in existing_values:
                try:
                    conn.execute(text(f"ALTER TYPE ledgerreason ADD VALUE '{value}'"))
                    conn.commit()
                    logger.info(f"[MIGRATION 100] ✓ Added '{value}' to ledgerreason enum")
                except Exception as e:
                    logger.error(f"[MIGRATION 100] ✗ Failed to add '{value}': {e}")
                    raise
            else:
                logger.info(f"[MIGRATION 100] - '{value}' already exists in enum")
        
        # Verify final state
        result = conn.execute(text("""
            SELECT enumlabel 
            FROM pg_enum 
            WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'ledgerreason')
            ORDER BY enumlabel
        """))
        final_values = [row[0] for row in result]
        logger.info(f"[MIGRATION 100] Final ledgerreason enum values: {final_values}")


if __name__ == "__main__":
    """Allow running migration manually for emergency hotfix"""
    print("[MIGRATION 100] Running manual ledgerreason enum migration...")
    upgrade()
    print("[MIGRATION 100] ✓ Migration complete!")
