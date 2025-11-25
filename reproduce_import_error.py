import sys
import os
import traceback

# Add backend to sys.path so we can import 'api'
sys.path.append(os.path.join(os.getcwd(), 'backend'))

with open('reproduce_output.txt', 'w') as f:
    try:
        f.write("Attempting to import api.routers.podcasts.crud...\n")
        import api.routers.podcasts.crud
        f.write("Successfully imported api.routers.podcasts.crud\n")
    except Exception:
        f.write("Failed to import api.routers.podcasts.crud\n")
        traceback.print_exc(file=f)
