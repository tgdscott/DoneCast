"""Check email verification codes in database."""
import os
from datetime import datetime
from sqlalchemy import create_engine, text

# Get database URL from environment
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("ERROR: DATABASE_URL environment variable not set")
    exit(1)

engine = create_engine(db_url)

with engine.connect() as conn:
    # Get all verification codes with user info
    result = conn.execute(text("""
        SELECT 
            ev.id,
            ev.user_id,
            ev.code,
            ev.expires_at,
            ev.verified_at,
            ev.used,
            ev.created_at,
            u.email
        FROM emailverification ev
        JOIN "user" u ON ev.user_id = u.id
        WHERE ev.verified_at IS NULL
        ORDER BY ev.created_at DESC
        LIMIT 10
    """))
    
    print("\n=== RECENT UNVERIFIED CODES ===\n")
    now = datetime.utcnow()
    
    for row in result:
        print(f"Email: {row.email}")
        print(f"Code: {row.code}")
        print(f"Created: {row.created_at}")
        print(f"Expires: {row.expires_at}")
        
        if row.expires_at < now:
            print(f"Status: ⚠️  EXPIRED (expired {(now - row.expires_at).total_seconds() / 60:.1f} minutes ago)")
        else:
            remaining = (row.expires_at - now).total_seconds() / 60
            print(f"Status: ✅ Valid (expires in {remaining:.1f} minutes)")
        
        print(f"Used: {row.used}")
        print(f"Verified: {row.verified_at}")
        print("-" * 60)
