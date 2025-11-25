"""Add guest_ids to media_item.

Adds guest_ids JSON array column to MediaItem table to associate guests with an upload.
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../..'))

from sqlmodel import Session, text
from backend.api.core.config import settings
from sqlmodel import create_engine

def run_migration():
    engine = create_engine(settings.DATABASE_URL)
    with Session(engine) as session:
        try:
            # check if column exists
            session.exec(text("SELECT guest_ids FROM mediaitem LIMIT 1"))
            print("guest_ids column already exists.")
        except Exception:
            session.rollback()
            print("Adding guest_ids column to mediaitem table...")
            session.exec(text("ALTER TABLE mediaitem ADD COLUMN guest_ids JSONB DEFAULT '[]'"))
            session.commit()
            print("Added guest_ids column.")

if __name__ == "__main__":
    run_migration()

