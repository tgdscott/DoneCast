"""Guest library migration.

Adds guest_library JSON column to Podcast model to store reusable guest profiles.
"""
from typing import List, Optional
from uuid import UUID
from sqlmodel import Session, select, text
from api.models.podcast import Podcast
from api.models.podcast_models import PodcastBase

def run_migration(session: Session):
    """Add guest_library column to podcast table."""
    # check if column exists
    try:
        session.exec(text("SELECT guest_library FROM podcast LIMIT 1"))
    except Exception:
        print("Adding guest_library column to podcast table...")
        session.exec(text("ALTER TABLE podcast ADD COLUMN guest_library JSONB DEFAULT '[]'"))
        session.commit()
        print("Added guest_library column.")

