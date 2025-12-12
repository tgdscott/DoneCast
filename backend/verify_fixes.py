import sys
import os

# Add backend to path
sys.path.append(os.getcwd())

def verify_media_route():
    try:
        from api.routers import media
        found = False
        for route in media.router.routes:
            if getattr(route, 'path', '') == '/{media_id}' and 'GET' in getattr(route, 'methods', []):
                found = True
                break
        
        if found:
            print("[PASS] Media Route: GET /api/media/{media_id} is registered in media.py")
        else:
            print("[FAIL] Media Route: GET /api/media/{media_id} is MISSING in media.py")
            # Print available routes
            # for r in media.router.routes:
            #     print(f" - {r.path} {r.methods}")
            return False
        return True
    except Exception as e:
        print(f"[FAIL] Media Route Check crashed: {e}")
        return False

def verify_system_templates():
    UUID = "bfd659d9-8088-4019-aefb-c41ad1f4b58a"
    
    # Check templates.py
    try:
        from api.routers import templates
        if hasattr(templates, 'SYSTEM_TEMPLATES') and UUID in templates.SYSTEM_TEMPLATES:
            print("[PASS] Templates: System Template UUID is whitelisted in templates.py")
        else:
            print(f"[FAIL] Templates: System Template UUID NOT found in templates.py")
            return False
    except Exception as e:
        print(f"[FAIL] Templates Check crashed: {e}")
        return False

    # Check recurring.py
    try:
        from api.routers import recurring
        if hasattr(recurring, 'SYSTEM_TEMPLATES') and UUID in recurring.SYSTEM_TEMPLATES:
            print("[PASS] Recurring: System Template UUID is whitelisted in recurring.py")
        else:
            print(f"[FAIL] Recurring: System Template UUID NOT found in recurring.py")
            return False
    except Exception as e:
        print(f"[FAIL] Recurring Check crashed: {e}")
        return False
        
    return True

if __name__ == "__main__":
    passed_media = verify_media_route()
    passed_templates = verify_system_templates()
    
    if passed_media and passed_templates:
        print("\nALL CHECKS PASSED. Ready for deployment.")
        sys.exit(0)
    else:
        print("\nSOME CHECKS FAILED.")
        sys.exit(1)
