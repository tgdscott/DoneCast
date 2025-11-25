"""Guest library migration script."""
import sys
import os

# Add the backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../..'))

from sqlmodel import create_engine, Session, text
from backend.api.core.config import settings

def run_migration():
    """Add guest_library column to podcast table."""
    engine = create_engine(settings.DATABASE_URL)
    with Session(engine) as session:
        try:
            # Check if column exists
            session.exec(text("SELECT guest_library FROM podcast LIMIT 1"))
            print("guest_library column already exists.")
        except Exception:
            session.rollback() # Rollback the failed transaction (SELECT that failed)
            print("Adding guest_library column to podcast table...")
            session.exec(text("ALTER TABLE podcast ADD COLUMN guest_library JSONB DEFAULT '[]'"))
            session.commit()
            print("Added guest_library column.")

if __name__ == "__main__":
    run_migration()

