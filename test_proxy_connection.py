"""Quick test to verify Cloud SQL Proxy connection

Run this after starting the proxy to verify everything works.
"""
import sys
import os
from pathlib import Path

# Add backend to path and change to backend directory for .env.local loading
backend_path = Path(__file__).parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

# Change to backend directory so pydantic-settings finds .env.local
os.chdir(backend_path)

from api.core.database import engine
from api.core.config import settings
from sqlalchemy import text

def test_connection():
    """Test database connection through Cloud SQL Proxy"""
    print("🔍 Testing Cloud SQL Proxy Connection")
    print("=" * 50)
    print(f"Environment: {settings.APP_ENV}")
    print(f"Database URL: {settings.DATABASE_URL}")
    print(f"Dev Mode: {settings.is_dev_mode}")
    print(f"Read-Only: {settings.DEV_READ_ONLY}")
    print()
    
    try:
        with engine.connect() as conn:
            # Test basic connection
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"✅ Connection successful!")
            print(f"   PostgreSQL version: {version[:50]}...")
            print()
            
            # Count users
            result = conn.execute(text("SELECT COUNT(*) FROM \"user\""))
            user_count = result.scalar()
            print(f"✅ User table accessible")
            print(f"   Total users: {user_count}")
            print()
            
            # Count podcasts
            result = conn.execute(text("SELECT COUNT(*) FROM podcast"))
            podcast_count = result.scalar()
            print(f"✅ Podcast table accessible")
            print(f"   Total podcasts: {podcast_count}")
            print()
            
            # Count episodes
            result = conn.execute(text("SELECT COUNT(*) FROM episode"))
            episode_count = result.scalar()
            print(f"✅ Episode table accessible")
            print(f"   Total episodes: {episode_count}")
            print()
            
            print("=" * 50)
            print("🎉 All tests passed!")
            print()
            print("⚠️  REMINDER: You are connected to PRODUCTION database")
            print(f"   Only modify test user data: {settings.DEV_TEST_USER_EMAILS}")
            
    except Exception as e:
        print(f"❌ Connection failed!")
        print(f"   Error: {e}")
        print()
        print("Troubleshooting:")
        print("1. Is Cloud SQL Proxy running? (Check for cloud-sql-proxy.exe process)")
        print("2. Is it listening on port 5433?")
        print("3. Is DATABASE_URL correct in .env.local?")
        print("4. Are your Application Default Credentials set?")
        print("   Run: gcloud auth application-default login")
        sys.exit(1)

if __name__ == "__main__":
    test_connection()
