"""Check admin users in database"""
from sqlalchemy import create_engine, text

engine = create_engine('postgresql+psycopg://podcast:T3sting123@localhost:5433/podcast')

print("\n📋 Checking all admin users...")
print("="*80)

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT email, tier, role, is_admin 
        FROM "user" 
        WHERE tier IN ('admin', 'superadmin') OR role IN ('admin', 'superadmin') OR is_admin = TRUE
        ORDER BY email
    """))
    
    users = result.fetchall()
    
    if not users:
        print("❌ No admin users found!")
    else:
        print(f"Found {len(users)} admin user(s):\n")
        for user in users:
            email, tier, role, is_admin = user
            status = "✅" if (role in ('admin', 'superadmin') and is_admin) else "⚠️"
            print(f"{status} {email}")
            print(f"   Tier: {tier}")
            print(f"   Role: {role}")
            print(f"   is_admin: {is_admin}")
            
            # Check if it will work
            if role == 'superadmin':
                print(f"   👑 SUPERADMIN - Full access")
            elif role == 'admin' and is_admin:
                print(f"   🔑 ADMIN - Restricted access")
            else:
                print(f"   ❌ BROKEN - role and is_admin mismatch!")
            print()

print("="*80)
