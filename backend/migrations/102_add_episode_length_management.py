"""
Migration 102: Add Episode Length Management Settings

Adds length management fields to PodcastTemplate table and speed adjustment
settings to User table to enable automatic episode length targeting.

Template fields:
- soft_min_length_seconds: Soft minimum episode length target
- soft_max_length_seconds: Soft maximum episode length target
- hard_min_length_seconds: Hard minimum episode length limit
- hard_max_length_seconds: Hard maximum episode length limit
- length_management_enabled: Enable automatic length management

User fields:
- speed_up_factor: Speed factor for lengthening episodes (1.0-1.25)
- slow_down_factor: Speed factor for shortening episodes (0.75-1.0)
"""

from sqlalchemy import text
from sqlmodel import Session


def migrate(session: Session) -> None:
    """Add episode length management fields to podcasttemplate and user tables."""
    
    # Add length management fields to podcasttemplate table
    session.exec(text("""
        ALTER TABLE podcasttemplate
        ADD COLUMN IF NOT EXISTS soft_min_length_seconds INTEGER,
        ADD COLUMN IF NOT EXISTS soft_max_length_seconds INTEGER,
        ADD COLUMN IF NOT EXISTS hard_min_length_seconds INTEGER,
        ADD COLUMN IF NOT EXISTS hard_max_length_seconds INTEGER,
        ADD COLUMN IF NOT EXISTS length_management_enabled BOOLEAN DEFAULT FALSE NOT NULL;
    """))
    
    # Add speed adjustment fields to user table
    session.exec(text("""
        ALTER TABLE "user"
        ADD COLUMN IF NOT EXISTS speed_up_factor DOUBLE PRECISION DEFAULT 1.05 NOT NULL,
        ADD COLUMN IF NOT EXISTS slow_down_factor DOUBLE PRECISION DEFAULT 0.95 NOT NULL;
    """))
    
    # Add check constraints to ensure valid ranges
    session.exec(text("""
        ALTER TABLE "user"
        ADD CONSTRAINT IF NOT EXISTS check_speed_up_factor_range 
        CHECK (speed_up_factor >= 1.0 AND speed_up_factor <= 1.25);
    """))
    
    session.exec(text("""
        ALTER TABLE "user"
        ADD CONSTRAINT IF NOT EXISTS check_slow_down_factor_range 
        CHECK (slow_down_factor >= 0.75 AND slow_down_factor < 1.0);
    """))
    
    session.commit()
    print("✅ Migration 102: Added episode length management fields")


def rollback(session: Session) -> None:
    """Remove episode length management fields."""
    
    # Drop constraints first
    session.exec(text("""
        ALTER TABLE "user"
        DROP CONSTRAINT IF EXISTS check_speed_up_factor_range,
        DROP CONSTRAINT IF EXISTS check_slow_down_factor_range;
    """))
    
    # Drop columns from user table
    session.exec(text("""
        ALTER TABLE "user"
        DROP COLUMN IF EXISTS speed_up_factor,
        DROP COLUMN IF EXISTS slow_down_factor;
    """))
    
    # Drop columns from podcasttemplate table
    session.exec(text("""
        ALTER TABLE podcasttemplate
        DROP COLUMN IF EXISTS soft_min_length_seconds,
        DROP COLUMN IF EXISTS soft_max_length_seconds,
        DROP COLUMN IF EXISTS hard_min_length_seconds,
        DROP COLUMN IF EXISTS hard_max_length_seconds,
        DROP COLUMN IF EXISTS length_management_enabled;
    """))
    
    session.commit()
    print("✅ Migration 102 rollback: Removed episode length management fields")
