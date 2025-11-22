#!/usr/bin/env python3
"""Test database connection and display configuration diagnostics.

This script helps diagnose database connection issues by:
1. Showing what database configuration is detected
2. Testing the connection
3. Providing troubleshooting steps
"""
import os
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

def test_db_connection():
    """Test database connection and display diagnostics."""
    print("=" * 70)
    print("Database Connection Diagnostic Tool")
    print("=" * 70)
    print()
    
    # Check environment variables
    print("1. Checking environment variables...")
    database_url = os.getenv("DATABASE_URL")
    instance_connection_name = os.getenv("INSTANCE_CONNECTION_NAME")
    db_user = os.getenv("DB_USER")
    db_pass = os.getenv("DB_PASS")
    db_name = os.getenv("DB_NAME")
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT", "5432")
    
    print(f"   DATABASE_URL: {'set' if database_url else 'not set'}")
    if database_url:
        # Mask password in output
        try:
            from sqlalchemy.engine import make_url
            parsed = make_url(database_url)
            safe_url = str(parsed).replace(parsed.password or "", "***", 1) if parsed.password else str(parsed)
            print(f"   DATABASE_URL value: {safe_url}")
            print(f"   Host: {parsed.host or 'unknown'}")
            print(f"   Port: {parsed.port or 'unknown'}")
            print(f"   Database: {parsed.database or 'unknown'}")
            print(f"   User: {parsed.username or 'unknown'}")
        except Exception as e:
            print(f"   ⚠️  Could not parse DATABASE_URL: {e}")
    
    print(f"   INSTANCE_CONNECTION_NAME: {'set' if instance_connection_name else 'not set'}")
    if instance_connection_name:
        print(f"   Value: {instance_connection_name}")
    print(f"   DB_USER: {'set' if db_user else 'not set'}")
    print(f"   DB_PASS: {'set' if db_pass else 'not set'}")
    print(f"   DB_NAME: {'set' if db_name else 'not set'}")
    print(f"   DB_HOST: {db_host if db_host else 'not set'}")
    print(f"   DB_PORT: {db_port}")
    print()
    
    # Check .env.local file
    print("2. Checking for .env.local file...")
    env_file = backend_dir / ".env.local"
    if env_file.exists():
        print(f"   ✓ Found: {env_file}")
        # Check if DATABASE_URL is in file
        try:
            content = env_file.read_text()
            if "DATABASE_URL" in content:
                print("   ✓ DATABASE_URL found in .env.local")
            else:
                print("   ⚠️  DATABASE_URL not found in .env.local")
        except Exception as e:
            print(f"   ⚠️  Could not read .env.local: {e}")
    else:
        print(f"   ⚠️  Not found: {env_file}")
    print()
    
    # Try to import and test connection
    print("3. Testing database connection...")
    try:
        from api.core.database import engine, _DATABASE_URL, _INSTANCE_CONNECTION_NAME, _HAS_DISCRETE_DB_CONFIG, DB_HOST
        from api.core.config import settings
        
        print(f"   Engine created: {'yes' if engine else 'no'}")
        print(f"   Configuration detected:")
        print(f"     - DATABASE_URL: {'set' if _DATABASE_URL else 'not set'}")
        print(f"     - INSTANCE_CONNECTION_NAME: {'set' if _INSTANCE_CONNECTION_NAME else 'not set'}")
        print(f"     - Discrete config (DB_USER/DB_PASS/DB_NAME): {'yes' if _HAS_DISCRETE_DB_CONFIG else 'no'}")
        print(f"     - DB_HOST: {DB_HOST if DB_HOST else 'not set'}")
        print()
        
        # Try to connect
        print("   Attempting to connect...")
        try:
            with engine.connect() as conn:
                result = conn.execute("SELECT 1 as test")
                row = result.fetchone()
                if row and row[0] == 1:
                    print("   ✓ Connection successful!")
                    print("   ✓ Database is reachable")
                    return True
        except Exception as conn_exc:
            print(f"   ✗ Connection failed: {conn_exc}")
            print()
            print("   Troubleshooting steps:")
            error_str = str(conn_exc).lower()
            
            if "timeout" in error_str or "connection timeout" in error_str:
                print("   1. Connection timeout detected")
                if _DATABASE_URL:
                    try:
                        from sqlalchemy.engine import make_url
                        parsed = make_url(_DATABASE_URL)
                        host = parsed.host or "unknown"
                        port = parsed.port or "unknown"
                        print(f"   2. Check if database is running at {host}:{port}")
                        if host in ("localhost", "127.0.0.1"):
                            print("   3. For local development with Cloud SQL:")
                            print("      - Start Cloud SQL Proxy: scripts/start_sql_proxy.ps1")
                            print("      - Verify proxy is running on the correct port")
                        else:
                            print("   3. Check firewall/network settings")
                            print("   4. Verify database is accessible from this machine")
                    except Exception:
                        pass
                elif _INSTANCE_CONNECTION_NAME:
                    print("   2. For Cloud SQL, ensure DB_HOST is set correctly")
                    if DB_HOST:
                        print(f"   3. Check if database is reachable at {DB_HOST}:{db_port}")
                        if DB_HOST.startswith("localhost") or DB_HOST.startswith("127.0.0.1"):
                            print("   4. For local development, ensure Cloud SQL Proxy is running")
                    else:
                        print("   3. Set DB_HOST environment variable (e.g., localhost:5433 for Cloud SQL Proxy)")
            elif "connection refused" in error_str or "could not connect" in error_str:
                print("   1. Connection refused - database may not be running")
                print("   2. Verify database service is started")
                if _DATABASE_URL:
                    try:
                        from sqlalchemy.engine import make_url
                        parsed = make_url(_DATABASE_URL)
                        if (parsed.host or "").startswith("localhost"):
                            print("   3. For local development, ensure Cloud SQL Proxy is running")
                    except Exception:
                        pass
            else:
                print("   1. Check DATABASE_URL format")
                print("   2. Verify database credentials")
                print("   3. Check database server logs")
            
            return False
            
    except Exception as e:
        print(f"   ✗ Failed to test connection: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_db_connection()
    sys.exit(0 if success else 1)










