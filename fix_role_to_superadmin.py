"""Fix scott@scottgerhardt.com role to superadmin"""
from sqlalchemy import create_engine, text

engine = create_engine('postgresql+psycopg://podcast:T3sting123@localhost:5433/podcast')

print("\n🔧 Fixing scott@scottgerhardt.com role...")

with engine.begin() as conn:
    # First check current value
    result = conn.execute(text("""
        SELECT email, tier, role, is_admin 
        FROM "user" 
        WHERE LOWER(email) = 'scott@scottgerhardt.com'
    """))
    user = result.fetchone()
    
    if user:
        print(f"\n📋 BEFORE:")
        print(f"   Email: {user[0]}")
        print(f"   Tier: {user[1]}")
        print(f"   Role: {user[2]}")
        print(f"   is_admin: {user[3]}")
    
    # Update to superadmin
    result = conn.execute(text("""
        UPDATE "user" 
        SET role = 'superadmin', tier = 'superadmin', is_admin = TRUE 
        WHERE LOWER(email) = 'scott@scottgerhardt.com'
    """))
    
    print(f"\n✅ Updated {result.rowcount} row(s)")
    
    # Verify
    result = conn.execute(text("""
        SELECT email, tier, role, is_admin 
        FROM "user" 
        WHERE LOWER(email) = 'scott@scottgerhardt.com'
    """))
    user = result.fetchone()
    
    if user:
        print(f"\n📋 AFTER:")
        print(f"   Email: {user[0]}")
        print(f"   Tier: {user[1]}")
        print(f"   Role: {user[2]}")
        print(f"   is_admin: {user[3]}")
        
        if user[2] == 'superadmin' and user[1] == 'superadmin' and user[3]:
            print(f"\n✅ SUCCESS! Now refresh the page in your browser.")
        else:
            print(f"\n❌ FAILED! Values still wrong.")

print("\n" + "="*60)
