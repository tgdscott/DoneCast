import sys
import os
import asyncio
from fastapi import FastAPI

# Add backend directory to python path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(current_dir, 'backend')
sys.path.append(backend_dir)

async def check_routes():
    # 1. Try importing the router module directly
    print("--- Attempting import of api.routers.speakers ---")
    try:
        from api.routers import speakers
        print("✅ Successfully imported api.routers.speakers")
    except Exception as e:
        print(f"❌ Failed to import api.routers.speakers: {e}")
        return

    # 2. Try importing the main app (which loads routing.py)
    print("\n--- Attempting to load main FastAPI app ---")
    try:
        from api.main import app
        # Inspect routes
        print(f"✅ App loaded. Total routes: {len(app.routes)}")
        
        found = False
        print("\n--- Searching for speaker routes ---")
        for route in app.routes:
            if hasattr(route, 'path') and 'speakers' in route.path:
                print(f"✅ Found route: {route.methods} {route.path}")
                found = True
        
        if not found:
            print("❌ No routes containing 'speakers' found in the app!")
            
            # 3. Check availability map if possible
            try:
                from api.routing import attach_routers
                availability = attach_routers(app)
                print(f"\nRouter availability report: {availability.get('speakers_router')}")
            except Exception as e:
                print(f"Could not check availability: {e}")
                
    except Exception as e:
        print(f"❌ Failed to load api.main: {e}")

if __name__ == "__main__":
    asyncio.run(check_routes())
