"""Debug script to check verification code storage and comparison."""
import os
from sqlalchemy import create_engine, text

# Get database URL from environment
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("ERROR: DATABASE_URL environment variable not set")
    exit(1)

engine = create_engine(db_url)

with engine.connect() as conn:
    # Get all recent verification codes with detailed info
    result = conn.execute(text("""
        SELECT 
            ev.id,
            ev.user_id,
            ev.code,
            ev.expires_at,
            ev.verified_at,
            ev.used,
            ev.created_at,
            u.email,
            LENGTH(ev.code) as code_length,
            u.is_active
        FROM emailverification ev
        JOIN "user" u ON ev.user_id = u.id
        ORDER BY ev.created_at DESC
        LIMIT 20
    """))
    
    print("\n=== VERIFICATION CODE DEBUG INFO ===\n")
    
    for row in result:
        print(f"Email: {row.email}")
        print(f"User Active: {row.is_active}")
        print(f"Code: '{row.code}'")
        print(f"Code Length: {row.code_length}")
        print(f"Code Repr: {repr(row.code)}")
        print(f"Code Bytes: {row.code.encode('utf-8')}")
        print(f"Created: {row.created_at}")
        print(f"Expires: {row.expires_at}")
        print(f"Used: {row.used}")
        print(f"Verified: {row.verified_at}")
        
        # Check for whitespace
        if row.code != row.code.strip():
            print(f"⚠️  WARNING: Code has whitespace!")
        
        # Check if code is exactly 6 digits
        if not row.code.isdigit():
            print(f"⚠️  WARNING: Code contains non-digit characters!")
        if len(row.code) != 6:
            print(f"⚠️  WARNING: Code is not exactly 6 characters!")
            
        print("-" * 80)
