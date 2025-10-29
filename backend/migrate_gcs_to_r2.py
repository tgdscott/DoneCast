"""Migrate episode audio files from GCS to R2.

This script:
1. Finds all episodes with gs:// audio paths
2. Downloads from GCS
3. Uploads to R2
4. Updates episode.gcs_audio_path to r2:// format
5. Keeps Spreaker episodes on Spreaker (no migration needed)

Usage:
    python migrate_gcs_to_r2.py --dry-run  # Preview what will be migrated
    python migrate_gcs_to_r2.py            # Actually migrate
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from api.models.podcast import Episode
from infrastructure import gcs, r2

# Load environment from backend directory
backend_dir = Path(__file__).parent
load_dotenv(backend_dir / ".env.local")

logger = logging.getLogger(__name__)


def migrate_episode_audio(episode: Episode, session: Session, dry_run: bool = False) -> bool:
    """Migrate a single episode's audio from GCS to R2.
    
    Args:
        episode: Episode to migrate
        session: Database session
        dry_run: If True, don't actually migrate, just log what would happen
    
    Returns:
        True if successful (or would be successful in dry-run), False otherwise
    """
    gcs_path = episode.gcs_audio_path
    if not gcs_path or not gcs_path.startswith("gs://"):
        logger.debug(f"Episode {episode.id} has no GCS audio, skipping")
        return False
    
    # Parse GCS path: gs://bucket/key
    gcs_str = gcs_path[5:]  # Remove "gs://"
    parts = gcs_str.split("/", 1)
    if len(parts) != 2:
        logger.error(f"Invalid GCS path format for episode {episode.id}: {gcs_path}")
        return False
    
    gcs_bucket, gcs_key = parts
    
    # Build R2 path (keep same key structure)
    r2_bucket = os.getenv("R2_BUCKET", "ppp-media")
    r2_key = gcs_key  # Same key structure
    r2_path = f"r2://{r2_bucket}/{r2_key}"
    
    logger.info(f"Episode {episode.episode_number} '{episode.title}':")
    logger.info(f"  FROM: {gcs_path}")
    logger.info(f"  TO:   {r2_path}")
    
    if dry_run:
        logger.info("  [DRY RUN] Would migrate this episode")
        return True
    
    # Step 1: Download from GCS
    logger.info("  Downloading from GCS...")
    audio_bytes = gcs.download_bytes(gcs_bucket, gcs_key)
    if not audio_bytes:
        logger.error(f"  FAILED: Could not download from GCS")
        return False
    
    logger.info(f"  Downloaded {len(audio_bytes):,} bytes")
    
    # Step 2: Upload to R2
    logger.info("  Uploading to R2...")
    r2_url = r2.upload_bytes(r2_bucket, r2_key, audio_bytes, content_type="audio/mpeg")
    if not r2_url:
        logger.error(f"  FAILED: Could not upload to R2")
        return False
    
    logger.info(f"  Uploaded to R2: {r2_url}")
    
    # Step 3: Update database
    logger.info("  Updating database...")
    episode.gcs_audio_path = r2_path  # Store as r2://bucket/key
    session.commit()
    
    logger.info("  ✅ Migration successful")
    return True


def main():
    parser = argparse.ArgumentParser(description="Migrate episode audio from GCS to R2")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what will be migrated without actually doing it",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of episodes to migrate (for testing)",
    )
    args = parser.parse_args()
    
    # Connect to database
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set in environment")
        sys.exit(1)
    
    engine = create_engine(database_url)
    
    with Session(engine) as session:
        # Find all episodes with GCS audio
        stmt = (
            select(Episode)
            .where(Episode.gcs_audio_path.like("gs://%"))
            .order_by(Episode.created_at.desc())
        )
        
        if args.limit:
            stmt = stmt.limit(args.limit)
        
        episodes = session.scalars(stmt).all()
        
        total = len(episodes)
        logger.info(f"Found {total} episodes with GCS audio to migrate")
        
        if total == 0:
            logger.info("Nothing to migrate!")
            return
        
        if args.dry_run:
            logger.info("\n🔍 DRY RUN MODE - No actual changes will be made\n")
        
        # Migrate each episode
        success_count = 0
        failure_count = 0
        
        for i, episode in enumerate(episodes, 1):
            logger.info(f"\n[{i}/{total}] Processing episode...")
            
            try:
                if migrate_episode_audio(episode, session, dry_run=args.dry_run):
                    success_count += 1
                else:
                    failure_count += 1
            except Exception as e:
                logger.error(f"  EXCEPTION: {e}", exc_info=True)
                failure_count += 1
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total episodes:     {total}")
        logger.info(f"Successful:         {success_count}")
        logger.info(f"Failed:             {failure_count}")
        
        if args.dry_run:
            logger.info("\nℹ️  This was a DRY RUN - run without --dry-run to actually migrate")
        else:
            logger.info("\n✅ Migration complete!")
            if failure_count > 0:
                logger.warning(f"⚠️  {failure_count} episodes failed - check logs above")


if __name__ == "__main__":
    main()
