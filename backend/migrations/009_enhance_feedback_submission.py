"""
Migration 009: Enhance feedback_submission table with admin workflow and technical context fields

Adds columns for:
- Automatic browser/console/network context capture
- Admin workflow (notes, assignment, priority)
- Status tracking and history
"""

from sqlalchemy import text
from api.core.database import engine


def run():
    """Add new columns to feedback_submission table for enhanced bug reporting"""
    
    with engine.connect() as conn:
        # Check if columns already exist (idempotent migration)
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'feedback_submission' 
            AND column_name IN ('user_agent', 'console_errors', 'admin_notes')
        """))
        
        existing_columns = {row[0] for row in result}
        
        if 'user_agent' in existing_columns:
            print("Migration 009: Columns already exist, skipping")
            return
        
        print("Migration 009: Adding enhanced feedback_submission columns...")
        
        # Add technical context columns (auto-captured from browser)
        conn.execute(text("""
            ALTER TABLE feedback_submission
            ADD COLUMN IF NOT EXISTS user_agent TEXT,
            ADD COLUMN IF NOT EXISTS viewport_size VARCHAR(50),
            ADD COLUMN IF NOT EXISTS console_errors TEXT,
            ADD COLUMN IF NOT EXISTS network_errors TEXT,
            ADD COLUMN IF NOT EXISTS local_storage_data TEXT,
            ADD COLUMN IF NOT EXISTS reproduction_steps TEXT
        """))
        
        # Add admin workflow columns
        conn.execute(text("""
            ALTER TABLE feedback_submission
            ADD COLUMN IF NOT EXISTS admin_notes TEXT,
            ADD COLUMN IF NOT EXISTS assigned_to VARCHAR(255),
            ADD COLUMN IF NOT EXISTS priority VARCHAR(20) DEFAULT 'medium',
            ADD COLUMN IF NOT EXISTS related_issues TEXT,
            ADD COLUMN IF NOT EXISTS fix_version VARCHAR(50),
            ADD COLUMN IF NOT EXISTS status_history TEXT,
            ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMP WITH TIME ZONE
        """))
        
        conn.commit()
        print("Migration 009: Complete - added 13 columns to feedback_submission")


if __name__ == "__main__":
    run()
