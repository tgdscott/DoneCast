"""Manually update admin users with role field"""
import os
os.environ['DATABASE_URL'] = 'postgresql+psycopg://podcast:T3sting123@localhost:5433/podcast'

from sqlalchemy import create_engine, text

engine = create_engine('postgresql+psycopg://podcast:T3sting123@localhost:5433/podcast')

print("\n🔧 Fixing admin role in production database...")
print("-" * 60)

# First, check if role column exists
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'user' AND column_name = 'role'
    """))
    role_col_exists = result.fetchone() is not None
    print(f"Role column exists: {role_col_exists}")

# Add role column if it doesn't exist
if not role_col_exists:
    print("\n➕ Adding role column to user table...")
    try:
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE "user" ADD COLUMN role VARCHAR(50) DEFAULT NULL'))
        print("✅ Role column added successfully")
    except Exception as e:
        print(f"❌ Error adding role column: {e}")
        exit(1)

# Update scott@scottgerhardt.com
print("\n🔄 Updating scott@scottgerhardt.com account...")
try:
    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE "user" 
            SET role = 'superadmin', tier = 'superadmin', is_admin = TRUE 
            WHERE LOWER(email) = 'scott@scottgerhardt.com'
        """))
        print(f"✅ Updated scott@scottgerhardt.com (rows affected: {result.rowcount})")
except Exception as e:
    print(f"❌ Error updating superadmin: {e}")
    exit(1)

# Verify the change
print("\n🔍 Verifying changes...")
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT email, tier, role, is_admin 
        FROM "user" 
        WHERE LOWER(email) = 'scott@scottgerhardt.com'
    """))
    user = result.fetchone()
    if user:
        print(f"Email: {user[0]}")
        print(f"Tier: {user[1]}")
        print(f"Role: {user[2]}")
        print(f"is_admin: {user[3]}")
        print("\n✅ SUCCESS! Admin account configured correctly")
        print("\n📝 Next steps:")
        print("1. Refresh your browser (Ctrl+F5)")
        print("2. Log out and log back in if refresh doesn't work")
        print("3. You should see the Admin Panel button in Quick Tools")
    else:
        print("❌ User not found!")

print("-" * 60)
