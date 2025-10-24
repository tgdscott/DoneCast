#!/usr/bin/env python3
"""Quick script to check user's terms acceptance status"""
import os
import sys
from pathlib import Path

# Load environment variables from backend/.env.local
env_file = Path(__file__).parent / 'backend' / '.env.local'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key, value)

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / 'backend'))

from sqlmodel import Session, select
from api.models.user import User
from api.core.database import engine
from api.core.config import settings

def check_user(email: str):
    print(f"\n🔍 Checking user: {email}")
    print(f"   TERMS_VERSION setting: {settings.TERMS_VERSION}")
    
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == email)).first()
        
        if not user:
            print(f"❌ User not found: {email}")
            return
        
        print(f"\n✅ User found in database:")
        print(f"   Email: {user.email}")
        print(f"   ID: {user.id}")
        print(f"   Created: {user.created_at}")
        print(f"   Active: {user.is_active}")
        print(f"   Admin: {user.is_admin}")
        print(f"\n📋 Terms Acceptance Status:")
        print(f"   terms_version_accepted: {repr(user.terms_version_accepted)}")
        print(f"   terms_accepted_at: {user.terms_accepted_at}")
        print(f"   terms_accepted_ip: {user.terms_accepted_ip}")
        
        # Note: terms_version_required is NOT in database, it's added dynamically
        print(f"\n📝 Note: terms_version_required is set dynamically to '{settings.TERMS_VERSION}' when UserPublic is created")
        
        # Check if there's a mismatch
        required = settings.TERMS_VERSION
        accepted = user.terms_version_accepted
        
        if not accepted:
            print(f"\n❌ ISSUE: NO TERMS ACCEPTED!")
            print(f"   Required: {required}")
            print(f"   Accepted: {accepted}")
            print(f"   → User SHOULD see TermsGate but may have bypassed it")
        elif accepted != required:
            print(f"\n⚠️  TERMS VERSION MISMATCH!")
            print(f"   Required: {required}")
            print(f"   Accepted: {accepted}")
            print(f"   → User SHOULD see TermsGate")
        else:
            print(f"\n✅ Terms acceptance is valid")
            print(f"   Accepted version: {accepted}")

if __name__ == '__main__':
    check_user('balboabliss@gmail.com')
