"""
Backfill audio_file_size and duration_ms for existing episodes.

This script updates episodes that are missing these fields by:
1. Checking local files first (FINAL_DIR)
2. Downloading from GCS if local file not found
3. Getting file size and duration using pydub

Run this after deploying the schema updates to populate existing episodes.
"""

import os
import sys
from pathlib import Path
import tempfile
import logging

# Add backend to path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from sqlmodel import Session, select
from api.models.podcast import Episode
from api.core.database import engine
from api.core.paths import FINAL_DIR
from infrastructure.gcs import download_from_gcs

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def backfill_episode_metadata():
    """Backfill audio_file_size and duration_ms for existing episodes."""
    
    with Session(engine) as session:
        # Get episodes that have audio but missing metadata
        statement = (
            select(Episode)
            .where(
                (Episode.audio_file_size == None) | (Episode.duration_ms == None)
            )
            .where(Episode.final_audio_path != None)
        )
        episodes = session.exec(statement).all()
        
        if not episodes:
            log.info("No episodes need backfilling!")
            return
        
        log.info(f"Found {len(episodes)} episodes to backfill")
        
        success_count = 0
        skip_count = 0
        error_count = 0
        
        for episode in episodes:
            try:
                log.info(f"\nProcessing: {episode.title}")
                
                needs_size = not episode.audio_file_size
                needs_duration = not episode.duration_ms
                
                # Try local file first
                local_path = Path(FINAL_DIR) / episode.final_audio_path
                
                if local_path.exists():
                    log.info(f"  Found local file: {local_path}")
                    
                    if needs_size:
                        episode.audio_file_size = local_path.stat().st_size
                        log.info(f"  ✓ File size: {episode.audio_file_size:,} bytes")
                    
                    if needs_duration:
                        try:
                            from pydub import AudioSegment
                            audio = AudioSegment.from_file(str(local_path))
                            episode.duration_ms = len(audio)
                            log.info(f"  ✓ Duration: {episode.duration_ms}ms ({episode.duration_ms / 1000 / 60:.1f} min)")
                        except Exception as dur_err:
                            log.warning(f"  ✗ Could not get duration: {dur_err}")
                    
                    session.add(episode)
                    success_count += 1
                
                # Try GCS if local not available
                elif episode.gcs_audio_path:
                    log.info(f"  Local file not found, downloading from GCS...")
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                        tmp_path = tmp.name
                    
                    try:
                        # Download from GCS
                        download_from_gcs(episode.gcs_audio_path, tmp_path)
                        log.info(f"  Downloaded to temp file")
                        
                        if needs_size:
                            episode.audio_file_size = Path(tmp_path).stat().st_size
                            log.info(f"  ✓ File size: {episode.audio_file_size:,} bytes")
                        
                        if needs_duration:
                            try:
                                from pydub import AudioSegment
                                audio = AudioSegment.from_file(tmp_path)
                                episode.duration_ms = len(audio)
                                log.info(f"  ✓ Duration: {episode.duration_ms}ms ({episode.duration_ms / 1000 / 60:.1f} min)")
                            except Exception as dur_err:
                                log.warning(f"  ✗ Could not get duration: {dur_err}")
                        
                        session.add(episode)
                        success_count += 1
                    
                    finally:
                        # Clean up temp file
                        try:
                            os.unlink(tmp_path)
                        except:
                            pass
                
                else:
                    log.warning(f"  ✗ No audio file found (local or GCS)")
                    skip_count += 1
            
            except Exception as e:
                log.error(f"  ✗ Error processing episode: {e}", exc_info=True)
                error_count += 1
        
        # Commit all changes
        try:
            session.commit()
            log.info(f"\n✅ Backfill complete!")
            log.info(f"  Success: {success_count}")
            log.info(f"  Skipped: {skip_count}")
            log.info(f"  Errors: {error_count}")
        except Exception as commit_err:
            log.error(f"Failed to commit changes: {commit_err}")
            session.rollback()


if __name__ == "__main__":
    log.info("Starting episode metadata backfill...")
    log.info("This will populate audio_file_size and duration_ms for existing episodes.\n")
    
    backfill_episode_metadata()
