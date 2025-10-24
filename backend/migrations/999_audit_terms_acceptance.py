"""
Migration: Audit users without terms acceptance (Oct 17, 2025)

This migration identifies users who registered before the Oct 13 fix
and haven't accepted the current Terms of Use version.
"""
import logging
from sqlmodel import Session, select
from api.models.user import User
from api.core.config import settings

log = logging.getLogger(__name__)


def audit_users_without_terms(session: Session) -> None:
    """
    Audit users who haven't accepted the current Terms of Use.
    
    This is a read-only audit - we don't force acceptance, just log for monitoring.
    Users will be prompted via TermsGate on next login.
    """
    required_version = getattr(settings, "TERMS_VERSION", "2025-09-19")
    
    try:
        # Find all active users without proper terms acceptance
        users = session.exec(
            select(User).where(
                User.is_active == True,  # noqa: E712
                (User.terms_version_accepted == None) | (User.terms_version_accepted != required_version)  # noqa: E711
            )
        ).all()
        
        if not users:
            log.info("[Terms Audit] ✅ All active users have accepted current terms (%s)", required_version)
            return
        
        log.warning(
            "[Terms Audit] Found %d active users without current terms acceptance (required: %s)",
            len(users),
            required_version
        )
        
        for user in users:
            log.info(
                "[Terms Audit]   - %s (created: %s, accepted: %s)",
                user.email,
                user.created_at.strftime("%Y-%m-%d") if user.created_at else "unknown",
                user.terms_version_accepted or "None"
            )
    
    except Exception as exc:
        log.warning("[Terms Audit] Failed to audit users: %s", exc)


def run_migration(session: Session) -> None:
    """Run the migration - in this case, just audit."""
    audit_users_without_terms(session)
