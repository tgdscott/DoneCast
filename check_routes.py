"""
Simple script to check if DELETE route is registered (without loading full app)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from api.routers.admin import router as admin_router

print("🔍 Checking admin router configuration...\n")
print(f"Admin router prefix: {admin_router.prefix}")
print(f"Admin router tags: {admin_router.tags}")

print("\n📋 Routes in admin router:")
for route in admin_router.routes:
    if hasattr(route, 'path') and hasattr(route, 'methods'):
        methods_str = ', '.join(route.methods)
        print(f"  {methods_str:20} {route.path}")
        if 'users' in route.path and 'DELETE' in route.methods:
            print(f"    ✅ FOUND DELETE /users/{{user_id}} route!")

# Check sub-routers
print("\n🔍 Checking included sub-routers...")
if hasattr(admin_router, 'routes'):
    for route in admin_router.routes:
        if hasattr(route, 'app') and hasattr(route.app, 'routes'):
            print(f"\n  Sub-router at: {route.path}")
            for sub_route in route.app.routes:
                if hasattr(sub_route, 'path') and hasattr(sub_route, 'methods'):
                    methods_str = ', '.join(sub_route.methods)
                    print(f"    {methods_str:20} {sub_route.path}")
                    if 'user' in sub_route.path.lower() and 'DELETE' in sub_route.methods:
                        print(f"      ✅ FOUND DELETE user route!")
