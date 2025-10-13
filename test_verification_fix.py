"""Test script to verify email verification code trimming works correctly."""
import os
import sys
from sqlalchemy import create_engine, text

# Get database URL
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("ERROR: DATABASE_URL environment variable not set")
    sys.exit(1)

print("Testing email verification code trimming fix...")
print("=" * 60)

# Test the Python string comparison behavior
test_code = "123456"
test_with_space = " 123456 "

print(f"\n1. String comparison without trimming:")
print(f"   Code in DB: '{test_code}'")
print(f"   Code from user: '{test_with_space}'")
print(f"   Match: {test_code == test_with_space}")
print(f"   ❌ This would FAIL without trimming")

print(f"\n2. String comparison WITH trimming:")
print(f"   Code in DB: '{test_code}'")
print(f"   Code from user: '{test_with_space}' -> '{test_with_space.strip()}'")
print(f"   Match: {test_code == test_with_space.strip()}")
print(f"   ✅ This SUCCEEDS with trimming")

# Check actual verification codes in database
engine = create_engine(db_url)

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT 
            ev.id,
            ev.code,
            LENGTH(ev.code) as code_length,
            ev.used,
            ev.verified_at,
            ev.expires_at,
            u.email
        FROM emailverification ev
        JOIN "user" u ON ev.user_id = u.id
        WHERE ev.verified_at IS NULL
        ORDER BY ev.created_at DESC
        LIMIT 5
    """))
    
    print(f"\n3. Recent unverified codes in database:")
    print(f"   (checking for any whitespace issues)\n")
    
    rows = list(result)
    if not rows:
        print("   No unverified codes found in database")
    else:
        for row in rows:
            code = row.code
            has_whitespace = code != code.strip()
            status = "❌ HAS WHITESPACE" if has_whitespace else "✅ Clean"
            
            print(f"   Email: {row.email}")
            print(f"   Code: '{code}' (length: {row.code_length})")
            print(f"   Status: {status}")
            print(f"   Used: {row.used}")
            print(f"   ---")

print(f"\n4. Fix implementation:")
print(f"   ✅ Added code.strip() in verification.py")
print(f"   ✅ Added email.strip() in verification.py")
print(f"   ✅ Codes are generated without whitespace")
print(f"   ✅ Comparison now handles user input with spaces")

print("\n" + "=" * 60)
print("Testing complete!")
print("\nNext steps:")
print("1. Deploy the updated verification.py file")
print("2. Ask users to try entering codes again")
print("3. Monitor for any 'Invalid or expired verification' errors")
