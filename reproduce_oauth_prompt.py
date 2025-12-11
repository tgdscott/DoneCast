import sys
import os
import unittest.mock
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

# Add backend to sys.path
sys.path.insert(0, os.path.abspath("backend"))

# Mock redis before any imports
sys.modules['redis'] = unittest.mock.MagicMock()


# Set env vars to avoid startup errors if possible
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

def log(msg):
    with open("reproduce_log.txt", "a") as f:
        f.write(msg + "\n")
    print(msg)

log("Script started")

def reproduce():
    log("Starting reproduce function")
    
    # We mock api.routers.auth.oauth.build_oauth_client
    target = "api.routers.auth.oauth.build_oauth_client"
    
    try:
        # Patch the build_oauth_client used in the router
        # Note: We must patch it BEFORE importing the router if the router uses it at module level (it doesn't, it uses it in function)
        # But we need to make sure we patch the one that `api.routers.auth.oauth` sees.
        
        # Explicitly import the module to ensure it exists for patching
        import api.routers.auth.oauth

        
        with unittest.mock.patch(target) as mock_build:
            mock_oauth_client = MagicMock()
            mock_google_client = MagicMock()
            mock_oauth_client.google = mock_google_client
            
            # Mock authorize_redirect
            mock_google_client.authorize_redirect = AsyncMock()
            
            from fastapi.responses import RedirectResponse
            mock_google_client.authorize_redirect.return_value = RedirectResponse("http://google.com/auth?prompt=none")

            mock_build.return_value = (mock_oauth_client, "mock_oauth_server")

            # Create minimal app
            try:
                from fastapi import FastAPI
                from api.routers.auth.oauth import router
                app = FastAPI()
                app.include_router(router, prefix="/api/auth")
                client = TestClient(app)
                log("Created TestClient from fresh FastAPI with router")
            except Exception as e:
                log(f"Failed to create app/client: {e}")
                import traceback
                log(traceback.format_exc())
                return

            log("Testing GET /api/auth/login/google...")
            try:
                response = client.get("/api/auth/login/google", follow_redirects=False)
                log(f"Response status: {response.status_code}")
            except Exception as e:
                log(f"Request failed: {e}")
                # It might fail due to dependency injection (db_session) if get_session is not mocked or if it tries to connect
                # login_google does not depend on db_session! verify_google_callback does.
                # login_google signature: async def login_google(request: Request):
                pass

            # Check call args
            if mock_google_client.authorize_redirect.called:
                args, kwargs = mock_google_client.authorize_redirect.call_args
                log(f"Called authorize_redirect with kwargs: {kwargs}")
                
                has_prompt = False
                if 'prompt' in kwargs and kwargs['prompt'] == 'select_account':
                    has_prompt = True
                
                if has_prompt:
                    log("SUCCESS: prompt='select_account' found in kwargs.")
                else:
                    log("FAILURE: prompt='select_account' NOT found in kwargs.")
            else:
                log("FAILURE: authorize_redirect was not called.")
            
    except Exception as e:
        log(f"Exception during reproduction: {e}")
        import traceback
        log(traceback.format_exc())

if __name__ == "__main__":
    reproduce()
