import sys
import os

# Add backend to path
sys.path.append(os.getcwd())

from fastapi import APIRouter
from api.routers.admin import router as admin_router

print(f"Admin Router Prefix: {admin_router.prefix}")

found_users_full = False
for route in admin_router.routes:
    # route.path in the router should be relative to the router's includes
    # Since admin_router has prefix="/admin", that is usually applied when included in App.
    # But include_router(users, prefix="/users") modifies the route path added to admin_router.
    
    # We expect "/users/full" inside admin_router
    if hasattr(route, "path") and route.path == "/users/full":
        found_users_full = True
        print(f"Found route: {route.path}")
        break

if found_users_full:
    print("SUCCESS: /users/full route found in admin router.")
else:
    print("FAILURE: /users/full route NOT found in admin router.")
    print("Available routes:")
    for route in admin_router.routes:
        if hasattr(route, "path"):
            print(f" - {route.path}")
    sys.exit(1)
