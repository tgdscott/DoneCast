"""Check and fix superadmin role for ADMIN_EMAIL user."""
import sys
import os
from pathlib import Path

# Load environment from backend/.env.local
from dotenv import load_dotenv
env_path = Path(__file__).parent / "backend" / ".env.local"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded environment from {env_path}")
else:
    print(f"⚠️  No .env.local found at {env_path}")

# Add backend to path
backend_path = os.path.join(os.path.dirname(__file__), "backend")
sys.path.insert(0, backend_path)

from sqlmodel import Session, select
from api.core.database import engine
from api.models.user import User
from api.core.config import settings

def main():
    admin_email = settings.ADMIN_EMAIL
    if not admin_email:
        print("❌ ADMIN_EMAIL not set in environment")
        return
    
    print(f"🔍 Checking superadmin role for: {admin_email}")
    
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == admin_email)).first()
        
        if not user:
            print(f"❌ User not found: {admin_email}")
            return
        
        print(f"\n📋 Current user status:")
        print(f"   Email: {user.email}")
        print(f"   Tier: {user.tier}")
        print(f"   Role: {user.role}")
        print(f"   is_admin: {user.is_admin}")
        
        needs_fix = False
        if user.role != "superadmin":
            print(f"\n⚠️  Role should be 'superadmin', currently: {user.role}")
            needs_fix = True
        
        if user.tier != "superadmin":
            print(f"⚠️  Tier should be 'superadmin', currently: {user.tier}")
            needs_fix = True
        
        if not user.is_admin:
            print(f"⚠️  is_admin should be True, currently: {user.is_admin}")
            needs_fix = True
        
        if needs_fix:
            print(f"\n🔧 Fixing superadmin status...")
            user.role = "superadmin"
            user.tier = "superadmin"
            user.is_admin = True
            session.add(user)
            session.commit()
            session.refresh(user)
            print("✅ Fixed!")
            print(f"\n📋 Updated status:")
            print(f"   Email: {user.email}")
            print(f"   Tier: {user.tier}")
            print(f"   Role: {user.role}")
            print(f"   is_admin: {user.is_admin}")
        else:
            print(f"\n✅ Superadmin status is correct!")

if __name__ == "__main__":
    main()
