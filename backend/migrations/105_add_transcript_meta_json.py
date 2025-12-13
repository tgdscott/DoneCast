"""Add transcript_meta_json to media items.

This migration adds the transcript_meta_json column to the mediaitem table.
This column stores GCS transcript location metadata for worker lookups during assembly.

Expected to run: On server startup
Rollback: ALTER TABLE mediaitem DROP COLUMN IF EXISTS transcript_meta_json;
"""

def upgrade(engine):
    """Add transcript_meta_json column to mediaitem table."""
    import logging
    from sqlalchemy import text
    
    log = logging.getLogger("migrations")
    log.info("[migration] Adding transcript_meta_json to mediaitem table")
    
    try:
        with engine.begin() as conn:
            # Add the column
            conn.execute(text("""
                ALTER TABLE mediaitem
                ADD COLUMN IF NOT EXISTS transcript_meta_json TEXT;
            """))
            
            log.info("[migration] ✅ Added transcript_meta_json column")
            
    except Exception as e:
        log.error(f"[migration] ❌ Failed to add transcript_meta_json: {e}", exc_info=True)
        raise


def downgrade(engine):
    """Remove transcript_meta_json column from mediaitem table."""
    import logging
    from sqlalchemy import text
    
    log = logging.getLogger("migrations")
    log.info("[migration] Removing transcript_meta_json from mediaitem table")
    
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                ALTER TABLE mediaitem
                DROP COLUMN IF EXISTS transcript_meta_json;
            """))
            
            log.info("[migration] ✅ Removed transcript_meta_json column")
            
    except Exception as e:
        log.error(f"[migration] ❌ Failed to remove transcript_meta_json: {e}", exc_info=True)
        raise
