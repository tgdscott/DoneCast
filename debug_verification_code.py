"""Debug verification code storage and retrieval."""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from sqlmodel import Session, select
from api.models.verification import EmailVerification
from api.models.user import User
from api.core.database import engine

def main():
    
    with Session(engine) as session:
        # Get the most recent verification for test20@scottgerhardt.com
        user = session.exec(
            select(User).where(User.email == "test20@scottgerhardt.com")
        ).first()
        
        if not user:
            print("❌ User test20@scottgerhardt.com not found")
            return
        
        print(f"✅ Found user: {user.email} (id={user.id}, active={user.is_active})")
        print()
        
        # Get all verifications for this user
        verifications = session.exec(
            select(EmailVerification)
            .where(EmailVerification.user_id == user.id)
            .order_by(EmailVerification.created_at.desc())  # type: ignore
        ).all()
        
        print(f"Found {len(verifications)} verification record(s):")
        print()
        
        for i, ev in enumerate(verifications, 1):
            print(f"--- Record #{i} ---")
            print(f"  Code: '{ev.code}' (type={type(ev.code).__name__}, len={len(ev.code)})")
            print(f"  Code repr: {repr(ev.code)}")
            print(f"  Code bytes: {ev.code.encode('utf-8')}")
            print(f"  Used: {ev.used}")
            print(f"  Verified at: {ev.verified_at}")
            print(f"  Expires at: {ev.expires_at}")
            print(f"  Created at: {ev.created_at}")
            print()
            
            # Test exact match
            test_code = "921853"
            matches = ev.code == test_code
            print(f"  Does '{ev.code}' == '{test_code}'? {matches}")
            print(f"  ev.code.strip() == test_code.strip()? {ev.code.strip() == test_code.strip()}")
            print()

if __name__ == "__main__":
    main()
