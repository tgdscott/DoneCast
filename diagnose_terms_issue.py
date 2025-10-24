#!/usr/bin/env python3
"""Diagnose terms acceptance issue - check actual database values."""

import sys
import os

# Add backend to path so we can import api modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from api.core.database import engine
from api.core.config import settings
from sqlmodel import Session, select
from api.models.user import User
import json

def diagnose():
    print(f"\n{'='*80}")
    print(f"TERMS ACCEPTANCE DIAGNOSTIC")
    print(f"{'='*80}\n")
    
    print(f"1. Settings Configuration:")
    print(f"   TERMS_VERSION = {repr(settings.TERMS_VERSION)} (type: {type(settings.TERMS_VERSION).__name__})")
    print()
    
    with Session(engine) as session:
        # Get all users (not just active)
        stmt = select(User).order_by(User.email)
        users = list(session.exec(stmt).all())
        
        print(f"2. All Users: {len(users)}")
        print()
        
        issues_found = []
        
        for user in users:
            accepted = user.terms_version_accepted
            required = settings.TERMS_VERSION
            
            # Check if they match
            match = (accepted == required)
            
            print(f"   User: {user.email}")
            print(f"      terms_version_accepted = {repr(accepted)} (type: {type(accepted).__name__})")
            print(f"      terms_version_required = {repr(required)} (type: {type(required).__name__})")
            print(f"      Match: {match}")
            print(f"      Would see TermsGate: {not match and required}")
            
            # Additional checks
            if accepted is not None:
                print(f"      String comparison: '{accepted}' == '{required}' → {str(accepted) == str(required)}")
                print(f"      Lengths: accepted={len(str(accepted))}, required={len(str(required))}")
                print(f"      Repr comparison: {repr(accepted)} == {repr(required)} → {repr(accepted) == repr(required)}")
                
                # Check for whitespace issues
                if str(accepted).strip() != str(accepted):
                    print(f"      ⚠️  WARNING: accepted has whitespace!")
                    issues_found.append(f"{user.email}: whitespace in accepted value")
                
                # Check for invisible characters
                if accepted != required:
                    accepted_bytes = str(accepted).encode('utf-8')
                    required_bytes = str(required).encode('utf-8')
                    print(f"      Bytes: accepted={accepted_bytes}, required={required_bytes}")
                    if accepted_bytes != required_bytes:
                        issues_found.append(f"{user.email}: byte mismatch (accepted={accepted_bytes}, required={required_bytes})")
            
            print()
        
        print(f"\n3. Summary:")
        print(f"   Total active users: {len(users)}")
        users_with_terms = [u for u in users if u.terms_version_accepted is not None]
        users_matching = [u for u in users if u.terms_version_accepted == required]
        users_not_matching = [u for u in users if u.terms_version_accepted is not None and u.terms_version_accepted != required]
        users_null = [u for u in users if u.terms_version_accepted is None]
        
        print(f"   Users with terms accepted: {len(users_with_terms)}")
        print(f"   Users matching required version: {len(users_matching)}")
        print(f"   Users NOT matching (would see TermsGate): {len(users_not_matching)}")
        print(f"   Users with NULL terms_version_accepted: {len(users_null)}")
        
        if issues_found:
            print(f"\n4. Issues Found:")
            for issue in issues_found:
                print(f"   - {issue}")
        else:
            print(f"\n4. No obvious data issues found.")
            
        print(f"\n5. Recommendations:")
        if users_not_matching:
            print(f"   - {len(users_not_matching)} users have old/mismatched versions")
            print(f"   - Consider running migration to update to current version")
        if users_null:
            print(f"   - {len(users_null)} users never accepted terms")
            print(f"   - This is expected for new users")
        
        print(f"\n{'='*80}\n")

if __name__ == "__main__":
    diagnose()
