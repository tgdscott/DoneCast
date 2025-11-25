
import sys
import os
import logging

# Add current directory to path so we can import api modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

try:
    print("Attempting to import api.routers.podcasts...")
    import api.routers.podcasts
    print("Successfully imported api.routers.podcasts")
    
    print("Attempting to import api.routers.podcasts.crud...")
    import api.routers.podcasts.crud
    print("Successfully imported api.routers.podcasts.crud")

    print("Attempting to import api.services.podcast_websites...")
    import api.services.podcast_websites
    print("Successfully imported api.services.podcast_websites")

    print("Attempting to import api.services.publisher...")
    import api.services.publisher
    print("Successfully imported api.services.publisher")

    print("Attempting to import api.services.podcasts.utils...")
    import api.services.podcasts.utils
    print("Successfully imported api.services.podcasts.utils")
    
except Exception as e:
    print(f"Import failed: {e}")
    import traceback
    traceback.print_exc()

