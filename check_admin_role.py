"""Quick script to check admin user role in database"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from api.core.database import SessionLocal
from api.models.user import User
from api.core.config import settings

def check_admin_role():
    db = SessionLocal()
    try:
        admin_email = settings.ADMIN_EMAIL
        print(f"\n🔍 Checking admin user: {admin_email}")
        print("-" * 60)
        
        user = db.query(User).filter(User.email == admin_email).first()
        
        if not user:
            print(f"❌ User {admin_email} not found in database!")
            return
        
        print(f"✅ Found user:")
        print(f"   Email: {user.email}")
        print(f"   ID: {user.id}")
        print(f"   Name: {user.name}")
        print(f"   Tier: {user.tier}")
        print(f"   Role: {user.role}")
        print(f"   is_admin: {user.is_admin}")
        print(f"   is_active: {user.is_active}")
        print("-" * 60)
        
        # Check what should be shown
        is_admin_flag = user.is_admin
        role_is_admin = user.role in ('admin', 'superadmin')
        
        print(f"\n🎯 Admin Panel Button Should Show: {is_admin_flag or role_is_admin}")
        print(f"   - is_admin flag: {is_admin_flag}")
        print(f"   - role is admin/superadmin: {role_is_admin}")
        
        if not (is_admin_flag or role_is_admin):
            print(f"\n⚠️  PROBLEM: User should have role='superadmin' and is_admin=True")
            print(f"   Current values:")
            print(f"     role: {user.role}")
            print(f"     is_admin: {user.is_admin}")
            print(f"\n💡 Solution: Check backend startup logs for migration errors")
        else:
            print(f"\n✅ SUCCESS: User has correct admin configuration!")
            print(f"   Next step: Log out and log back in on the frontend")
        
    except Exception as e:
        print(f"\n❌ Error checking admin role: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == '__main__':
    check_admin_role()
