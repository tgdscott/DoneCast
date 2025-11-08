#!/usr/bin/env python3
"""Quick test to verify USE_WORKER_IN_DEV configuration"""

import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

# Load .env.local
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env.local"
    if env_path.exists():
        load_dotenv(env_path, override=False)
        print(f"[OK] Loaded .env.local from {env_path}")
    else:
        print(f"[ERROR] .env.local not found at {env_path}")
except ImportError:
    print("[WARNING] python-dotenv not installed")
except Exception as e:
    print(f"[ERROR] Error loading .env.local: {e}")

# Check environment variables
print("\n" + "=" * 80)
print("ENVIRONMENT VARIABLE CHECK")
print("=" * 80)

use_worker_raw = os.getenv("USE_WORKER_IN_DEV", "NOT SET")
use_worker = use_worker_raw and use_worker_raw.lower().strip() in {"true", "1", "yes", "on"}
worker_url = os.getenv("WORKER_URL_BASE", "NOT SET")
tasks_auth = os.getenv("TASKS_AUTH", "NOT SET")

print(f"USE_WORKER_IN_DEV: {use_worker_raw} → {use_worker}")
print(f"WORKER_URL_BASE: {worker_url}")
print(f"TASKS_AUTH: {'SET' if tasks_auth != 'NOT SET' else 'NOT SET'} ({len(tasks_auth) if tasks_auth != 'NOT SET' else 0} chars)")

print("\n" + "=" * 80)
print("CONFIGURATION CHECK")
print("=" * 80)

path = "/api/tasks/assemble"
is_worker_task = "/assemble" in path or "/process-chunk" in path

condition_met = use_worker and worker_url and is_worker_task

print(f"Path: {path}")
print(f"Is worker task: {is_worker_task}")
print(f"\nCondition check:")
print(f"  use_worker_in_dev: {use_worker}")
print(f"  worker_url_base: {bool(worker_url and worker_url != 'NOT SET')}")
print(f"  is_worker_task: {is_worker_task}")
print(f"\n[RESULT] Will use worker server: {condition_met}")

if not condition_met:
    print("\n[ISSUES] CONFIGURATION PROBLEMS:")
    if not use_worker:
        print("  - USE_WORKER_IN_DEV is not set to 'true'")
    if not worker_url or worker_url == "NOT SET":
        print("  - WORKER_URL_BASE is not set")
    if not is_worker_task:
        print("  - Path doesn't match worker task pattern")
else:
    print("\n[OK] Configuration looks good! Worker server should be used.")

print("=" * 80)

