#!/usr/bin/env python3
"""Migration: Update all users from old terms version to current.

This fixes the issue where TERMS_VERSION was bumped from 2025-09-01 to 2025-09-19
but existing users still have the old version recorded, causing them to see
the TermsGate repeatedly.

CRITICAL: Only run this if the terms content HASN'T actually changed and you
just want to update the version number for existing users.
"""

import sys
import os
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from api.core.database import engine
from api.core.config import settings
from sqlmodel import Session, select
from api.models.user import User

def migrate_terms_versions():
    """Update all users with old terms versions to current version."""
    
    current_version = settings.TERMS_VERSION
    print(f"\n{'='*80}")
    print(f"TERMS VERSION MIGRATION")
    print(f"{'='*80}\n")
    print(f"Current TERMS_VERSION: {current_version}\n")
    
    with Session(engine) as session:
        # Find all users who have accepted an old version
        from sqlalchemy import and_
        stmt = select(User).where(
            and_(
                User.is_active == True,
                User.terms_version_accepted.isnot(None),
                User.terms_version_accepted != current_version
            )
        )
        users_to_update = list(session.exec(stmt).all())
        
        print(f"Found {len(users_to_update)} users with outdated terms versions:\n")
        
        for user in users_to_update:
            print(f"  - {user.email}: {user.terms_version_accepted} → {current_version}")
        
        if not users_to_update:
            print("No users need updating. All users are current!\n")
            return
        
        # Ask for confirmation
        print(f"\n⚠️  This will update {len(users_to_update)} user(s) to version {current_version}")
        print("Only proceed if the terms content hasn't materially changed.")
        confirm = input("\nType 'yes' to proceed: ").strip().lower()
        
        if confirm != 'yes':
            print("\n❌ Migration cancelled.")
            return
        
        # Update all users
        updated_count = 0
        for user in users_to_update:
            old_version = user.terms_version_accepted
            user.terms_version_accepted = current_version
            # Keep the original acceptance timestamp - we're just updating the version ID
            # user.terms_accepted_at stays the same
            session.add(user)
            updated_count += 1
        
        # Commit all changes
        session.commit()
        
        print(f"\n✅ Successfully updated {updated_count} user(s) to version {current_version}")
        print(f"\nUsers will no longer see the TermsGate on next login.\n")
        print(f"{'='*80}\n")

if __name__ == "__main__":
    try:
        migrate_terms_versions()
    except KeyboardInterrupt:
        print("\n\n❌ Migration cancelled by user.\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error during migration: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
