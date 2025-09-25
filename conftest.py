# Ensures `from api...` works when package lives under `backend/api` (renamed from podcast-pro-plus)
import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent
PKG_DIR = ROOT / "backend"  # Updated after directory rename
if str(PKG_DIR) not in sys.path:
    sys.path.insert(0, str(PKG_DIR))

# Default to test env; tests should mock vendors
os.environ.setdefault("PPP_ENV", "test")

# Disable rate limits early so routers using SlowAPI decorators won't error during import
os.environ.setdefault("DISABLE_RATE_LIMITS", "1")
