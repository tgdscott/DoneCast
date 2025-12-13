import sys
import os
import asyncio
from fastapi import FastAPI

# Add backend directory to python path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(current_dir, 'backend')
# Ensure we add the backend dir to path so imports work as if running from root
if backend_dir not in sys.path:
    sys.path.append(backend_dir)
sys.path.append(os.getcwd()) # Add root as well

def main():
    with open("check_routes_result.txt", "w", encoding='utf-8') as f:
        f.write("--- Starting Route Check ---\n")
        
        # 1. Try importing the router module directly
        try:
            from api.routers import speakers
            f.write("✅ Successfully imported api.routers.speakers\n")
        except Exception as e:
            f.write(f"❌ Failed to import api.routers.speakers: {e}\n")
            return

        # 2. Try importing the main app
        try:
            from api.main import app
            f.write(f"✅ App loaded. Total routes: {len(app.routes)}\n")
            
            found = False
            speakers_routes = []
            for route in app.routes:
                if hasattr(route, 'path') and 'speakers' in route.path:
                    speakers_routes.append(f"{route.methods} {route.path}")
                    found = True
            
            if found:
                f.write(f"✅ Found {len(speakers_routes)} speaker routes:\n")
                for r in speakers_routes:
                    f.write(f"  - {r}\n")
            else:
                f.write("❌ No routes containing 'speakers' found in the app!\n")

        except Exception as e:
            f.write(f"❌ Failed to load api.main: {e}\n")
            import traceback
            f.write(traceback.format_exc())

if __name__ == "__main__":
    main()
