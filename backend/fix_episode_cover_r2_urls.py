"""Fix episode cover image URLs by matching R2 objects with database records.

This script:
1. Scans all episodes for missing or invalid cover URLs
2. Searches R2 bucket for cover images matching episode IDs
3. Updates database with correct R2 URLs

Usage:
    python backend/fix_episode_cover_r2_urls.py [--dry-run] [--episode-id EPISODE_ID]
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional, List, Tuple
from uuid import UUID

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlmodel import Session, create_engine, select, text
from api.models.podcast import Episode
from api.routers.episodes.common import compute_cover_info
from api.core.database import session_scope, engine
from infrastructure import r2 as r2lib

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
DB_URL = os.getenv("DATABASE_URL")
R2_BUCKET = os.getenv("R2_BUCKET", "ppp-media").strip()

if not DB_URL:
    logger.error("DATABASE_URL environment variable not set")
    sys.exit(1)


def check_r2_object_exists(bucket: str, key: str) -> bool:
    """Check if an object exists in R2."""
    try:
        # r2lib.blob_exists is a function, not a method
        if hasattr(r2lib, 'blob_exists'):
            return r2lib.blob_exists(bucket, key)  # type: ignore
        return False
    except Exception as e:
        logger.debug(f"Error checking R2 object {key}: {e}")
        return False


def list_r2_objects(bucket: str, prefix: str, max_keys: int = 100) -> List[str]:
    """List objects in R2 bucket with given prefix.
    
    Uses boto3 directly since infrastructure.r2 doesn't have a list function.
    """
    try:
        import boto3
        from botocore.client import Config
        
        account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
        access_key_id = os.getenv("R2_ACCESS_KEY_ID", "").strip()
        secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
        
        if not all([account_id, access_key_id, secret_access_key]):
            logger.error("Missing R2 credentials")
            return []
        
        endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
            region_name="auto",
        )
        
        objects = []
        try:
            paginator = client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(
                Bucket=bucket,
                Prefix=prefix,
                MaxKeys=max_keys
            )
            
            for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects.append(obj['Key'])
        except Exception as e:
            logger.debug(f"Failed to list R2 objects with prefix '{prefix}': {e}")
        
        return objects
    except Exception as e:
        logger.error(f"Failed to create R2 client for listing: {e}")
        return []


def find_cover_in_r2(episode_id: str, user_id: str, r2_bucket: str, cover_path_hint: Optional[str] = None) -> Optional[str]:
    """Find cover image for episode in R2.
    
    Searches multiple possible paths:
    1. {user_id}/episodes/{episode_id}/cover/ (from orchestrator)
    2. covers/episode/{episode_id}/ (from migration script)
    3. If cover_path_hint is provided, tries to construct path from it
    
    Returns the R2 URL if found, None otherwise.
    """
    account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
    if not account_id:
        logger.error("R2_ACCOUNT_ID not set")
        return None
    
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
    
    # Try path 1: {user_id}/episodes/{episode_id}/cover/ (from orchestrator)
    prefix1 = f"{user_id}/episodes/{episode_id}/cover/"
    logger.debug(f"Searching R2 for cover with prefix: {prefix1}")
    objects1 = list_r2_objects(r2_bucket, prefix1, max_keys=20)
    
    for obj_key in objects1:
        if any(obj_key.lower().endswith(ext) for ext in image_extensions):
            url = f"https://{r2_bucket}.{account_id}.r2.cloudflarestorage.com/{obj_key}"
            logger.info(f"✅ Found cover at path 1: {url}")
            return url
    
    # Try path 2: covers/episode/{episode_id}/ (from migration)
    prefix2 = f"covers/episode/{episode_id}/"
    logger.debug(f"Searching R2 for cover with prefix: {prefix2}")
    objects2 = list_r2_objects(r2_bucket, prefix2, max_keys=20)
    
    for obj_key in objects2:
        if any(obj_key.lower().endswith(ext) for ext in image_extensions):
            url = f"https://{r2_bucket}.{account_id}.r2.cloudflarestorage.com/{obj_key}"
            logger.info(f"✅ Found cover at path 2: {url}")
            return url
    
    # Try path 3: If we have a cover_path hint, try to find it
    if cover_path_hint:
        # Extract filename from cover_path
        cover_filename = Path(cover_path_hint).name
        if any(cover_filename.lower().endswith(ext) for ext in image_extensions):
            # Try both path patterns with this filename
            key1 = f"{user_id}/episodes/{episode_id}/cover/{cover_filename}"
            key2 = f"covers/episode/{episode_id}/{cover_filename}"
            
            for key in [key1, key2]:
                if check_r2_object_exists(r2_bucket, key):
                    url = f"https://{r2_bucket}.{account_id}.r2.cloudflarestorage.com/{key}"
                    logger.info(f"✅ Found cover using hint: {url}")
                    return url
    
    logger.warning(f"❌ No cover found in R2 for episode {episode_id}")
    return None


def convert_r2_path_to_url(r2_path: str, bucket: str) -> Optional[str]:
    """Convert r2:// path to HTTPS URL.
    
    Args:
        r2_path: Path like "r2://bucket/key" or "bucket/key"
        bucket: Default bucket name
    
    Returns:
        HTTPS URL or None
    """
    account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
    if not account_id:
        return None
    
    # Remove r2:// prefix if present
    if r2_path.startswith("r2://"):
        r2_path = r2_path[5:]
    
    # Split bucket and key
    parts = r2_path.split("/", 1)
    if len(parts) == 2:
        path_bucket, key = parts
    elif len(parts) == 1:
        # Just a key, use provided bucket
        path_bucket = bucket
        key = parts[0]
    else:
        return None
    
    return f"https://{path_bucket}.{account_id}.r2.cloudflarestorage.com/{key}"


def check_cover_url_valid_simple(episode: Episode) -> Tuple[bool, Optional[str]]:
    """Simple check if episode has a valid cover URL (fast, no URL resolution).
    
    This is used for filtering - it just checks the database fields without
    doing expensive URL resolution or logging.
    
    Returns:
        (is_valid, issue_description_if_invalid)
    """
    # Check if gcs_cover_path has a valid R2 HTTPS URL
    if episode.gcs_cover_path:
        gcs_path = str(episode.gcs_cover_path).strip()
        
        # Valid R2 URL format
        if gcs_path.startswith("https://") and ".r2.cloudflarestorage.com" in gcs_path:
            if "spreaker.com" not in gcs_path.lower():
                return True, gcs_path
        
        # Needs conversion: r2:// format
        if gcs_path.startswith("r2://"):
            return False, f"r2://_format_needs_conversion"
        
        # Needs lookup: plain path (not a URL)
        if not any(gcs_path.startswith(prefix) for prefix in ("https://", "http://", "gs://", "r2://")):
            return False, f"plain_path_needs_r2_lookup"
        
        # gs:// URLs are invalid for published episodes (outside retention window)
        # But we'll let compute_cover_info handle that during actual processing
    
    # No valid gcs_cover_path
    return False, "no_valid_gcs_cover_path"


def check_cover_url_valid(episode: Episode) -> Tuple[bool, Optional[str]]:
    """Check if episode has a valid cover URL using compute_cover_info.
    
    This does full URL resolution and is used for verification after updates.
    Use check_cover_url_valid_simple() for fast filtering.
    
    Returns:
        (is_valid, current_url_or_issue_description)
    """
    # First check if gcs_cover_path is in wrong format (quick check)
    if episode.gcs_cover_path:
        gcs_path = str(episode.gcs_cover_path).strip()
        
        # Check for r2:// format that needs conversion
        if gcs_path.startswith("r2://"):
            return False, f"r2://_format_needs_conversion:{gcs_path}"
        
        # Check for plain paths (not URLs) - these are invalid and need R2 lookup
        if not any(gcs_path.startswith(prefix) for prefix in ("https://", "http://", "gs://", "r2://")):
            return False, f"plain_path_needs_r2_lookup:{gcs_path}"
    
    # Use compute_cover_info for full resolution (this will log at INFO level)
    cover_info = compute_cover_info(episode)
    cover_url = cover_info.get("cover_url")
    
    if cover_url:
        # Check if it's a valid HTTPS URL (R2 or other)
        if cover_url.startswith("https://"):
            # Verify it's not a Spreaker URL (which we reject)
            if "spreaker.com" not in cover_url.lower():
                return True, cover_url
    
    return False, cover_url


def fix_episode_cover(episode_id: str, user_id: str, r2_cover_url: str, dry_run: bool = False) -> bool:
    """Fix cover URL for a single episode by updating the database.
    
    Uses raw SQL UPDATE for reliability - avoids ORM session issues.
    
    Returns:
        True if fixed, False otherwise
    """
    if dry_run:
        logger.info(f"DRY RUN: Would update episode {episode_id}")
        logger.info(f"  gcs_cover_path -> {r2_cover_url}")
        return True
    
    # Extract filename from R2 URL for cover_path
    cover_filename = r2_cover_url.split("/")[-1].split("?")[0]
    
    # Use raw SQL UPDATE for maximum reliability
    from sqlalchemy import text
    with session_scope() as session:
        try:
            # First, get the current values to log
            result = session.execute(
                text("SELECT gcs_cover_path, cover_path FROM episode WHERE id = :episode_id"),
                {"episode_id": episode_id}
            ).first()
            
            if not result:
                logger.error(f"Episode {episode_id} not found in database")
                return False
            
            old_gcs_cover_path, old_cover_path = result
            
            # Update using raw SQL - this is more reliable than ORM
            update_sql = text("""
                UPDATE episode 
                SET gcs_cover_path = :gcs_cover_path,
                    cover_path = :cover_path
                WHERE id = :episode_id
            """)
            
            session.execute(
                update_sql,
                {
                    "episode_id": episode_id,
                    "gcs_cover_path": r2_cover_url,
                    "cover_path": cover_filename
                }
            )
            
            # Commit the change
            session.commit()
            
            logger.info(f"✅ Committed update for episode {episode_id}")
            logger.info(f"   Old gcs_cover_path: {old_gcs_cover_path}")
            logger.info(f"   New gcs_cover_path: {r2_cover_url[:80]}...")
            
            # Verify in a completely separate session to ensure we see committed data
            # (same session might see uncommitted changes due to transaction isolation)
            from api.core.database import engine
            verify_session = Session(engine)
            try:
                verify_result = verify_session.execute(
                    text("SELECT gcs_cover_path FROM episode WHERE id = :episode_id"),
                    {"episode_id": episode_id}
                ).first()
                
                if verify_result and verify_result[0] == r2_cover_url:
                    logger.info(f"✅ Verified: Episode {episode_id} gcs_cover_path={verify_result[0][:80]}...")
                    return True
                else:
                    logger.error(f"❌ Verification failed: Episode {episode_id}")
                    logger.error(f"   Expected: {r2_cover_url[:80]}...")
                    logger.error(f"   Got: {verify_result[0][:80] if verify_result and verify_result[0] else 'None'}...")
                    return False
            finally:
                verify_session.close()
            
        except Exception as e:
            logger.error(f"Failed to update episode {episode_id}: {e}", exc_info=True)
            session.rollback()
            return False


def main():
    import argparse
    from sqlalchemy import or_, and_, text as sa_text
    
    parser = argparse.ArgumentParser(description="Fix episode cover image URLs in R2")
    parser.add_argument("--dry-run", action="store_true", help="Don't make changes, just report")
    parser.add_argument("--episode-id", type=str, help="Fix specific episode ID only")
    parser.add_argument("--limit", type=int, default=1000, help="Maximum episodes to process")
    parser.add_argument("--fix-all", action="store_true", help="Process all episodes (ignore limit)")
    parser.add_argument("--only-broken", action="store_true", help="Only process episodes with invalid cover URLs")
    args = parser.parse_args()
    
    if args.dry_run:
        logger.info("=" * 80)
        logger.info("DRY RUN MODE - No changes will be made")
        logger.info("=" * 80)
    
    if not DB_URL:
        logger.error("DATABASE_URL environment variable not set")
        return
    
    # Use session_scope for proper transaction management
    with session_scope() as session:
        # Build query - prioritize episodes with broken covers
        query = select(Episode)
        
        if args.episode_id:
            try:
                episode_uuid = UUID(args.episode_id)
                query = query.where(Episode.id == episode_uuid)
            except ValueError:
                logger.error(f"Invalid episode ID: {args.episode_id}")
                return
        else:
            # For --only-broken, we'll filter in Python after loading
            # This is simpler and more reliable than complex SQL queries
            # Order by most recent first
            from sqlalchemy import desc
            query = query.order_by(Episode.created_at.desc())  # type: ignore
            
            if not args.fix_all:
                query = query.limit(args.limit * 2 if args.only_broken else args.limit)  # Load more if filtering
        
        all_episodes = session.exec(query).all()
        
        # Filter for broken episodes if requested
        if args.only_broken:
            episodes = []
            for ep in all_episodes:
                # Use simple check for filtering (fast, no logging, no URL resolution)
                is_valid, _ = check_cover_url_valid_simple(ep)
                if not is_valid:
                    episodes.append(ep)
            logger.info(f"Filtered to {len(episodes)} episodes with broken covers (from {len(all_episodes)} total)")
        else:
            episodes = all_episodes[:args.limit] if not args.fix_all else all_episodes
        
        logger.info(f"Processing {len(episodes)} episodes")
        
        if len(episodes) == 0:
            logger.info("No episodes to process")
            return
        
        fixed_count = 0
        skipped_count = 0
        error_count = 0
        not_found_count = 0
        
        # Process episodes - use separate session for each to ensure commits persist
        batch_size = 20
        for i in range(0, len(episodes), batch_size):
            batch = episodes[i:i+batch_size]
            batch_num = i//batch_size + 1
            total_batches = (len(episodes) + batch_size - 1)//batch_size
            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} episodes)")
            
            for episode in batch:
                try:
                    episode_id = str(episode.id)
                    user_id = str(episode.user_id)
                    
                    # Check if cover URL is already valid (using simple check first)
                    is_valid, current_url = check_cover_url_valid_simple(episode)
                    if is_valid:
                        url_str = str(current_url)[:80] if current_url else "None"
                        logger.debug(f"Episode {episode_id} already has valid cover URL: {url_str}...")
                        skipped_count += 1
                        continue
                    
                    url_str = str(current_url) if current_url else "None"
                    logger.info(f"Episode {episode_id} needs cover URL fix. Current: {url_str}")
                    logger.info(f"  cover_path: {episode.cover_path}")
                    logger.info(f"  gcs_cover_path: {episode.gcs_cover_path}")
                    
                    r2_cover_url = None
                    
                    # Check if gcs_cover_path just needs format conversion (r2:// -> https://)
                    if episode.gcs_cover_path:
                        gcs_path_str = str(episode.gcs_cover_path).strip()
                        
                        if gcs_path_str.startswith("r2://"):
                            # Convert r2:// to https://
                            r2_cover_url = convert_r2_path_to_url(gcs_path_str, R2_BUCKET)
                            if r2_cover_url:
                                # Verify the object exists
                                account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
                                if account_id and f".{account_id}.r2.cloudflarestorage.com/" in r2_cover_url:
                                    key = r2_cover_url.split(f".{account_id}.r2.cloudflarestorage.com/", 1)[1]
                                    if check_r2_object_exists(R2_BUCKET, key):
                                        logger.info(f"✅ Converting r2:// path to HTTPS URL for episode {episode_id}")
                                    else:
                                        logger.warning(f"⚠️ r2:// path exists but object not found in R2, will search for cover")
                                        r2_cover_url = None
                                else:
                                    logger.warning(f"⚠️ Could not parse R2 URL, will search for cover")
                                    r2_cover_url = None
                    
                    # If we don't have a URL yet, try to find cover in R2
                    if not r2_cover_url:
                        # Check if cover_path has a gs:// URL that might need migration
                        cover_path_hint = None
                        if episode.cover_path:
                            cover_path_str = str(episode.cover_path)
                            # If cover_path is a gs:// URL, try to find it in R2 by migrating
                            if cover_path_str.startswith("gs://"):
                                # This is a GCS path - try to find the migrated version in R2
                                # Extract the filename from the gs:// path
                                gs_filename = cover_path_str.split("/")[-1]
                                # Try to find it in R2 using the episode ID
                                cover_path_hint = gs_filename
                            elif cover_path_str.startswith("r2://"):
                                cover_path_hint = cover_path_str
                            else:
                                # Use cover_path as hint for filename
                                cover_path_hint = cover_path_str
                        
                        r2_cover_url = find_cover_in_r2(episode_id, user_id, R2_BUCKET, cover_path_hint=cover_path_hint)
                    
                    if not r2_cover_url:
                        logger.warning(f"Could not find cover in R2 for episode {episode_id}")
                        not_found_count += 1
                        continue
                    
                    # Update database using a fresh session
                    result = fix_episode_cover(episode_id, user_id, r2_cover_url, dry_run=args.dry_run)
                    if result:
                        fixed_count += 1
                    else:
                        # If we couldn't find the cover, it was already logged as a warning
                        not_found_count += 1
                        
                except Exception as e:
                    logger.error(f"Error processing episode {episode.id}: {e}", exc_info=True)
                    error_count += 1
        
        logger.info("=" * 80)
        logger.info(f"SUMMARY:")
        logger.info(f"  ✅ Fixed: {fixed_count}")
        logger.info(f"  ⏭️  Skipped (already valid): {skipped_count}")
        logger.info(f"  ❌ Not found in R2: {not_found_count}")
        logger.info(f"  💥 Errors: {error_count}")
        logger.info(f"  📊 Total processed: {len(episodes)}")
        logger.info("=" * 80)
        
        if not_found_count > 0:
            logger.warning(f"⚠️  {not_found_count} episodes had covers that couldn't be found in R2")
            logger.warning("   These covers may need to be re-uploaded or the paths may be incorrect")
        
        if fixed_count == 0 and not_found_count == 0 and error_count == 0:
            logger.info("✅ All episodes already have valid cover URLs!")


if __name__ == "__main__":
    main()

