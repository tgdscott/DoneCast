#!/usr/bin/env python
"""Quick script to run phone verification table migration."""
import sys
import os
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# Load environment
from dotenv import load_dotenv
env_path = backend_dir.parent / ".env.local"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    print(f"Loaded environment from {env_path}")
else:
    print("Warning: .env.local not found, using system environment")

from sqlmodel import Session
from api.core.database import engine
import importlib.util

if __name__ == "__main__":
    print("Running phone verification table migration...")
    print("=" * 60)
    
    try:
        # Import and run the migration directly
        migration_path = backend_dir / "migrations" / "036_add_phone_verification_table.py"
        spec = importlib.util.spec_from_file_location('migration_036', migration_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            print("Executing migration...")
            with Session(engine) as session:
                module.run_migration(session)
            print("\n[SUCCESS] Migration completed successfully!")
            print("The phone verification table has been created.")
        else:
            print("[ERROR] Could not load migration module")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n[ERROR] Error running migration: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)



