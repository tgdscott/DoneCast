"""Check verification history for test5@scottgerhardt.com"""
import os
import sys
from datetime import datetime
from sqlalchemy import create_engine, text

# Get database URL from environment or use direct connection
db_url = os.environ.get("DATABASE_URL", "postgresql://podcast:T3sting123@34.11.250.121/podcast")

try:
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        # Get user info
        user_result = conn.execute(text("""
            SELECT id, email, is_active, created_at
            FROM "user"
            WHERE email = 'test5@scottgerhardt.com'
        """))
        
        user = user_result.fetchone()
        if not user:
            print("User not found!")
            sys.exit(1)
        
        print(f"\n=== USER INFO ===")
        print(f"User ID: {user.id}")
        print(f"Email: {user.email}")
        print(f"Active: {user.is_active}")
        print(f"Created: {user.created_at}")
        
        # Get ALL verification records for this user
        verif_result = conn.execute(text("""
            SELECT 
                id,
                code,
                created_at,
                expires_at,
                verified_at,
                used
            FROM emailverification
            WHERE user_id = :user_id
            ORDER BY created_at DESC
        """), {"user_id": user.id})
        
        print(f"\n=== ALL VERIFICATION CODES (newest first) ===")
        now = datetime.utcnow()
        
        for i, row in enumerate(verif_result, 1):
            print(f"\n--- Code #{i} ---")
            print(f"Code: {row.code}")
            print(f"Created: {row.created_at}")
            print(f"Expires: {row.expires_at}")
            
            if row.expires_at < now:
                expired_mins = (now - row.expires_at).total_seconds() / 60
                print(f"Status: ⚠️  EXPIRED ({expired_mins:.1f} minutes ago)")
            else:
                remaining = (row.expires_at - now).total_seconds() / 60
                print(f"Status: ✅ Valid (expires in {remaining:.1f} minutes)")
            
            print(f"Used: {row.used}")
            print(f"Verified at: {row.verified_at}")
            
            # Show what SHOULD have happened with the fix
            if row.used and not row.verified_at:
                print("⚠️  WARNING: Marked as 'used' but never verified!")
                print("   This suggests the code was invalidated by resend")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
