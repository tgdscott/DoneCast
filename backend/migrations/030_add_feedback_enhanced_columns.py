"""
Migration 030: Add enhanced technical context columns to feedback_submission table

These columns were added to the FeedbackSubmission model to capture more detailed
debugging information when users report bugs through the AI Assistant (Mike).

Columns added:
- user_agent: Full user agent string
- viewport_size: Browser viewport dimensions (e.g., "1920x1080")
- console_errors: Captured console errors (JSON array)
- network_errors: Failed network requests (JSON array)
- local_storage_data: Relevant localStorage/sessionStorage data
- reproduction_steps: User-provided steps to reproduce the bug

Date: October 23, 2025
"""

import sys
import os
from pathlib import Path

# Add backend to sys.path for imports
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from sqlmodel import Session
from api.core.database import engine
import logging

log = logging.getLogger(__name__)

def run_migration():
    """Add enhanced technical context columns to feedback_submission table."""
    log.info("Running migration 030: Add enhanced context columns to feedback_submission")
    
    with Session(engine) as session:
        # Check if columns already exist (for idempotency)
        result = session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'feedback_submission'
        """))
        existing_columns = {row[0] for row in result.fetchall()}
        
        # Define ALL columns that should exist (enhanced context + admin workflow)
        columns_to_add = {
            # Enhanced technical context columns
            'user_agent': 'VARCHAR',
            'viewport_size': 'VARCHAR',
            'console_errors': 'TEXT',  # JSON array can be large
            'network_errors': 'TEXT',  # JSON array can be large
            'local_storage_data': 'TEXT',  # Can contain significant data
            'reproduction_steps': 'TEXT',  # User descriptions can be long
            
            # Admin workflow columns
            'acknowledged_at': 'TIMESTAMP',
            'resolved_at': 'TIMESTAMP',
            'admin_notes': 'TEXT',  # Markdown supported, can be lengthy
            'assigned_to': 'VARCHAR',
            'priority': 'VARCHAR',
            'related_issues': 'VARCHAR',
            'fix_version': 'VARCHAR',
            'status_history': 'TEXT',  # JSON array of status changes
        }
        
        for column_name, column_type in columns_to_add.items():
            if column_name not in existing_columns:
                log.info(f"Adding column {column_name} to feedback_submission table")
                session.execute(text(f"""
                    ALTER TABLE feedback_submission 
                    ADD COLUMN {column_name} {column_type} NULL
                """))
                log.info(f"✓ Column {column_name} added successfully")
            else:
                log.info(f"Column {column_name} already exists, skipping")
        
        session.commit()
        log.info("Migration 030 completed successfully")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
