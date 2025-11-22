#!/usr/bin/env python3
"""
Run the trial columns migration independently.
"""
import os
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# Load environment variables
from dotenv import load_dotenv
env_path = backend_dir / ".env.local"
if env_path.exists():
    print(f"Loading environment from {env_path}...")
    load_dotenv(dotenv_path=env_path)
else:
    print("Warning: .env.local not found, using system environment")

# Now import after environment is loaded
from migrations.one_time_migrations import _ensure_user_trial_columns
from migrations.migration_tracker import run_migration_once

if __name__ == "__main__":
    print("Running trial columns migration...")
    print("-" * 50)
    
    result = run_migration_once("ensure_user_trial_columns", _ensure_user_trial_columns)
    
    print("-" * 50)
    if result:
        print("[SUCCESS] Migration completed successfully!")
    else:
        print("[FAILED] Migration failed or was skipped")
        sys.exit(1)

