import sys
import os
from uuid import uuid4

# Add backend to path
sys.path.append(os.getcwd())

from fastapi import APIRouter
# We need to import the router from where it is defined
from api.routers.media_read import router as media_read_router

print(f"Media Read Router Prefix: {media_read_router.prefix}")

found_media_id_get = False
for route in media_read_router.routes:
    # We are looking for GET /{media_id}
    if hasattr(route, "path") and hasattr(route, "methods"):
        if route.path == "/{media_id}" and "GET" in route.methods:
            found_media_id_get = True
            print(f"Found route: {route.path} {route.methods}")
            break

if found_media_id_get:
    print("SUCCESS: GET /media/{media_id} route found in media_read router.")
else:
    print("FAILURE: GET /media/{media_id} route NOT found in media_read router.")
    print("Available routes:")
    for route in media_read_router.routes:
        if hasattr(route, "path"):
            print(f" - {route.path} {getattr(route, 'methods', '')}")
    sys.exit(1)
