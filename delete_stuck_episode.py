#!/usr/bin/env python3
"""Delete stuck episode 49fafa89-9e06-4128-a773-e9cc4b20104d from database."""
import os
import sys
from pathlib import Path

# Load environment variables from backend/.env.local
from dotenv import load_dotenv
env_path = Path(__file__).parent / "backend" / ".env.local"
load_dotenv(env_path)

# Add backend to path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from sqlmodel import Session, select, delete
from api.core.database import engine
from api.models.podcast import Episode

STUCK_EPISODE_ID = "49fafa89-9e06-4128-a773-e9cc4b20104d"

def main():
    print(f"Deleting stuck episode: {STUCK_EPISODE_ID}")
    
    with Session(engine) as session:
        # Find the episode
        episode = session.get(Episode, STUCK_EPISODE_ID)
        
        if not episode:
            print(f"❌ Episode {STUCK_EPISODE_ID} not found in database")
            return 1
        
        print(f"✅ Found episode: '{episode.title}' (status: {episode.status})")
        
        # Delete it
        session.delete(episode)
        session.commit()
        
        print(f"✅ Episode deleted successfully")
        
        # Verify deletion
        check = session.get(Episode, STUCK_EPISODE_ID)
        if check is None:
            print(f"✅ Verified: Episode no longer exists in database")
            return 0
        else:
            print(f"❌ Error: Episode still exists after deletion")
            return 1

if __name__ == "__main__":
    sys.exit(main())
