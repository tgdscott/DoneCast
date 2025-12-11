import sys
import os

# Add backend to path
sys.path.append(os.getcwd())

def test_import(module_name):
    try:
        print(f"Attempting to import {module_name}...")
        __import__(module_name)
        print(f"SUCCESS: {module_name} imported.")
    except ImportError as e:
        print(f"FAILURE: {module_name} failed: {e}")
        import traceback
        traceback.print_exc()
        # We want to fail fast for this script
        sys.exit(1)
    except Exception as e:
        print(f"FAILURE: {module_name} crashed on import: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

# List of admin modules to verify
modules_to_verify = [
    "api.routers.admin.users",
    "api.routers.admin.deletions",
    "api.routers.admin.promo_codes",
]

for mod in modules_to_verify:
    test_import(mod)

print("All verifications passed.")
