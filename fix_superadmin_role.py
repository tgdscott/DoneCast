"""
Fix superadmin role for scott@scottgerhardt.com
Run this once to update the role from 'admin' to 'superadmin'
"""
import sys
import os

# Add backend to path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_path)

# Load environment variables first
from dotenv import load_dotenv
env_path = os.path.join(backend_path, '.env.local')
load_dotenv(env_path)

from api.core.database import engine
from sqlalchemy import text

def fix_superadmin_role():
    admin_email = 'scott@scottgerhardt.com'
    
    with engine.begin() as conn:
        # Just verify current state
        verify_stmt = 'SELECT email, role, tier, is_admin FROM "user" WHERE lower(email) = :email'
        result = conn.execute(text(verify_stmt), {'email': admin_email.lower()})
        row = result.fetchone()
        
        if row:
            print(f"✅ Current Database State:")
            print(f"   Email: {row[0]}")
            print(f"   Role: {row[1]}")
            print(f"   Tier: {row[2]}")
            print(f"   Is Admin: {row[3]}")
        else:
            print(f"❌ User {admin_email} not found in database")

if __name__ == '__main__':
    fix_superadmin_role()
