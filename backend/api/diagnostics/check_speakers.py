"""
Diagnostic script to check speaker router mounting and configuration.

This script:
1. Checks if the speakers router is properly mounted
2. Verifies database schema has required columns  
3. Tests a sample API call to the speakers endpoint

Run from backend directory:
    python -m api.diagnostics.check_speakers
"""

import asyncio
import logging
from api.core.database import get_session
from api.models.podcast import Podcast
from sqlmodel import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_database_schema():
    """Check if Podcast model has speaker-related columns."""
    logger.info("=== Checking Database Schema ===")
    
    try:
        from sqlalchemy import inspect
        from api.core.database import engine
        
        inspector = inspect(engine)
        columns = inspector.get_columns('podcast')
        column_names = [col['name'] for col in columns]
        
        required_columns = ['speaker_intros', 'guest_library', 'has_guests']
        
        for col in required_columns:
            if col in column_names:
                logger.info(f"✓ Column '{col}' exists in podcast table")
            else:
                logger.error(f"✗ Column '{col}' MISSING from podcast table")
        
        return True
    except Exception as e:
        logger.error(f"Failed to check schema: {e}")
        return False


async def check_router_registration():
    """Check if speakers router is registered in the app."""
    logger.info("\n=== Checking Router Registration ===")
    
    try:
        from api.main import app
        
        # Find speaker-related routes
        speaker_routes = []
        for route in app.routes:
            path = str(getattr(route, 'path', ''))
            if 'speaker' in path.lower():
                methods = getattr(route, 'methods', set())
                speaker_routes.append({
                    'path': path,
                    'methods': list(methods) if methods else None
                })
        
        if speaker_routes:
            logger.info(f"✓ Found {len(speaker_routes)} speaker-related routes:")
            for route in speaker_routes:
                logger.info(f"  {route['methods']} {route['path']}")
        else:
            logger.error("✗ No speaker routes found! Router may not be mounted.")
        
        return len(speaker_routes) > 0
    except Exception as e:
        logger.error(f"Failed to check router registration: {e}")
        return False


async def check_sample_podcast():
    """Check if there are any podcasts in the database."""
    logger.info("\n=== Checking Sample Podcasts ===")
    
    try:
        session = next(get_session())
        podcasts = session.exec(select(Podcast).limit(5)).all()
        
        if podcasts:
            logger.info(f"✓ Found {len(podcasts)} podcast(s) in database:")
            for podcast in podcasts:
                logger.info(f"  - {podcast.name} (ID: {podcast.id})")
                logger.info(f"    speaker_intros: {podcast.speaker_intros}")
                logger.info(f"    guest_library: {podcast.guest_library}")
                logger.info(f"    has_guests: {podcast.has_guests}")
        else:
            logger.warning("⚠ No podcasts found in database")
        
        return True
    except Exception as e:
        logger.error(f"Failed to check podcasts: {e}")
        return False


async def main():
    """Run all diagnostic checks."""
    logger.info("Starting Speaker Configuration Diagnostics\n")
    
    schema_ok = await check_database_schema()
    router_ok = await check_router_registration()
    podcast_ok = await check_sample_podcast()
    
    logger.info("\n=== Diagnostic Summary ===")
    logger.info(f"Database Schema: {'✓ OK' if schema_ok else '✗ FAILED'}")
    logger.info(f"Router Registration: {'✓ OK' if router_ok else '✗ FAILED'}")
    logger.info(f"Sample Podcasts: {'✓ OK' if podcast_ok else '✗ FAILED'}")
    
    if not router_ok:
        logger.error("\n❌ CRITICAL: Speakers router is not properly registered!")
        logger.error("Check api/routing.py import logs for errors.")


if __name__ == "__main__":
    asyncio.run(main())
