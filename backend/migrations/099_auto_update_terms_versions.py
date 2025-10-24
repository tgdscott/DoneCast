"""Migration 099: Auto-update terms versions for existing users.

This migration automatically updates users who have old terms versions to the current
version WITHOUT requiring them to re-accept. This is safe when terms content hasn't
materially changed and you just need to update the version identifier.

CRITICAL: This runs automatically on startup. If you DON'T want auto-migration (because
terms content DID change and you need explicit re-acceptance), delete this file.
"""

import logging
from sqlmodel import Session, select
from sqlalchemy import and_

log = logging.getLogger(__name__)


def migrate_terms_versions_auto(session: Session, current_version: str) -> None:
    """Auto-migrate users with old terms versions to current version.
    
    Args:
        session: Database session
        current_version: The current TERMS_VERSION from settings
    """
    from api.models.user import User
    
    # Find users with old versions
    try:
        stmt = select(User).where(
            User.is_active,
            User.terms_version_accepted != None,  # noqa: E711
            User.terms_version_accepted != current_version
        )
        users_to_update = list(session.exec(stmt).all())
        
        if not users_to_update:
            log.info("[migrate:099] No users need terms version update")
            return
        
        log.warning(
            f"[migrate:099] Auto-updating {len(users_to_update)} users from old terms versions to {current_version}"
        )
        
        updated_count = 0
        for user in users_to_update:
            old_version = user.terms_version_accepted
            user.terms_version_accepted = current_version
            # Keep original acceptance timestamp - just updating version ID
            session.add(user)
            updated_count += 1
            log.info(f"[migrate:099] Updated {user.email}: {old_version} → {current_version}")
        
        session.commit()
        log.info(f"[migrate:099] Successfully auto-updated {updated_count} user(s) to version {current_version}")
        
    except Exception as e:
        log.error(f"[migrate:099] Error during auto-migration: {e}")
        session.rollback()
        # Don't crash startup - just log the error
        raise


def migrate(session: Session) -> None:
    """Migration entry point called by startup_tasks.py"""
    from api.core.config import settings
    
    current_version = getattr(settings, "TERMS_VERSION", None)
    if not current_version:
        log.warning("[migrate:099] TERMS_VERSION not set - skipping auto-migration")
        return
    
    migrate_terms_versions_auto(session, current_version)
