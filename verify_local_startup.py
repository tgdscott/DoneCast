import sys
import os

# Add backend to sys.path
backend_path = os.path.join(os.getcwd(), 'backend')
sys.path.insert(0, backend_path)

print(f"Checking startup from: {backend_path}")

try:
    from api.main import create_app
    print("Imported create_app successfully.")
    
    app = create_app()
    print("Created app instance successfully.")
    
    # Optional: check if episodes router is attached
    routes = [route.path for route in app.routes]
    ep_routes = [r for r in routes if '/episodes' in r]
    print(f"Found {len(ep_routes)} episode routes.")
    if len(ep_routes) > 0:
        print("Episodes router is active.")
    else:
        print("WARNING: Episodes router not found in routes!")

except Exception as e:
    print(f"Startup failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
