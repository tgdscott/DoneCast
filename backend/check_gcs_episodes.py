"""Quick check for episodes needing migration."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(".env.local")

engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    # Count GCS episodes
    result = conn.execute(text("SELECT COUNT(*) FROM episode WHERE gcs_audio_path LIKE 'gs://%'"))
    gcs_count = result.scalar()
    
    # Count R2 episodes
    result = conn.execute(text("SELECT COUNT(*) FROM episode WHERE gcs_audio_path LIKE 'r2://%'"))
    r2_count = result.scalar()
    
    # Count Spreaker episodes
    result = conn.execute(text("SELECT COUNT(*) FROM episode WHERE spreaker_episode_id IS NOT NULL"))
    spreaker_count = result.scalar()
    
    print(f"GCS episodes (need migration): {gcs_count}")
    print(f"R2 episodes (already migrated): {r2_count}")
    print(f"Spreaker episodes (no migration): {spreaker_count}")
