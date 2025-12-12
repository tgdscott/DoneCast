"""
Migration: Add AI_METADATA_GENERATION to LedgerReason enum
Created: 2025-12-11
Fixes: invalid input value for enum ledgerreason: "AI_METADATA_GENERATION"

HISTORY:
This value was added to the Python Enum code but was missed in previous migration 100.
"""

from sqlalchemy import text
from api.core.database import engine
from api.core.logging import get_logger

logger = get_logger(__name__)

def upgrade():
    """Add AI_METADATA_GENERATION to ledgerreason type in PostgreSQL"""
    
    value = 'AI_METADATA_GENERATION'
    
    with engine.connect() as conn:
        # Check if value already exists
        result = conn.execute(text(f"""
            SELECT EXISTS (
                SELECT 1 
                FROM pg_enum 
                WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'ledgerreason')
                AND enumlabel = '{value}'
            )
        """))
        exists = result.scalar()
        
        if not exists:
            try:
                conn.execute(text(f"ALTER TYPE ledgerreason ADD VALUE '{value}'"))
                conn.commit()
                logger.info(f"[MIGRATION 103] ✓ Added '{value}' to ledgerreason enum")
            except Exception as e:
                logger.error(f"[MIGRATION 103] ✗ Failed to add '{value}': {e}")
                raise
        else:
            logger.info(f"[MIGRATION 103] - '{value}' already exists in enum")

if __name__ == "__main__":
    print("[MIGRATION 103] Running manual ledgerreason enum migration...")
    upgrade()
    print("[MIGRATION 103] ✓ Migration complete!")
