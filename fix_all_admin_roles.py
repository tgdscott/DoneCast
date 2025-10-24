"""Set role='admin' for all users with tier='admin'"""
from sqlalchemy import create_engine, text

engine = create_engine('postgresql+psycopg://podcast:T3sting123@localhost:5433/podcast')

print("\n🔧 Fixing admin users...")

with engine.begin() as conn:
    # Find users with tier='admin' but role is NULL
    result = conn.execute(text("""
        SELECT email, tier, role 
        FROM "user" 
        WHERE LOWER(tier) = 'admin' AND (role IS NULL OR role != 'admin')
    """))
    
    users = result.fetchall()
    print(f"\n📋 Found {len(users)} users with tier='admin' but wrong role:")
    for user in users:
        print(f"   - {user[0]} (tier={user[1]}, role={user[2]})")
    
    # Fix them
    result = conn.execute(text("""
        UPDATE "user" 
        SET role = 'admin', is_admin = TRUE 
        WHERE LOWER(tier) = 'admin'
    """))
    
    print(f"\n✅ Updated {result.rowcount} user(s)")
    
    # Verify
    result = conn.execute(text("""
        SELECT email, tier, role, is_admin 
        FROM "user" 
        WHERE LOWER(tier) = 'admin'
    """))
    
    users = result.fetchall()
    if users:
        print(f"\n📋 Admin users after fix:")
        for user in users:
            print(f"   - {user[0]}: tier={user[1]}, role={user[2]}, is_admin={user[3]}")
    
    print("\n✅ Done! Tell users to log out and log back in.")

print("="*60)
