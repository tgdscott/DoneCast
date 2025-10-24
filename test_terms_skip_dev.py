"""
Quick test to verify terms are skipped in dev mode
"""
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

from api.core.config import settings

def test_terms_check():
    env = (settings.APP_ENV or "dev").strip().lower()
    print(f"\n=== Terms Skip Test ===")
    print(f"APP_ENV: {settings.APP_ENV}")
    print(f"Normalized env: {env}")
    print(f"Is dev environment: {env in {'dev', 'development', 'local', 'test', 'testing'}}")
    print(f"TERMS_VERSION in settings: {settings.TERMS_VERSION}")
    
    if env in {"dev", "development", "local", "test", "testing"}:
        print("\n✅ TERMS WILL BE SKIPPED (terms_version_required = None)")
    else:
        print(f"\n❌ TERMS WILL BE ENFORCED (terms_version_required = {settings.TERMS_VERSION})")
    
    print("\n=== Test Complete ===\n")

if __name__ == "__main__":
    test_terms_check()
