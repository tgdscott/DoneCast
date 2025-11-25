import requests
import sys
import time
import os

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
EMAIL = os.getenv("TEST_EMAIL", "test@example.com")
PASSWORD = os.getenv("TEST_PASSWORD", "password")

def log(msg, success=True):
    icon = "✅" if success else "❌"
    print(f"{icon} {msg}")

def check_health():
    """Check the basic health endpoint."""
    try:
        url = f"{API_BASE_URL}/health"
        print(f"Checking {url}...")
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            log(f"Health check passed: {resp.json()}")
            return True
        else:
            log(f"Health check failed: {resp.status_code} - {resp.text}", success=False)
            return False
    except Exception as e:
        log(f"Health check exception: {e}", success=False)
        return False

def login():
    """Authenticate and return the access token."""
    try:
        url = f"{API_BASE_URL}/api/auth/token"
        print(f"Logging in as {EMAIL}...")
        resp = requests.post(
            url,
            data={"username": EMAIL, "password": PASSWORD},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10
        )
        if resp.status_code == 200:
            token = resp.json().get("access_token")
            log("Login successful")
            return token
        else:
            log(f"Login failed: {resp.status_code} - {resp.text}", success=False)
            return None
    except Exception as e:
        log(f"Login exception: {e}", success=False)
        return None

def check_podcasts(token):
    """Check the podcast list endpoint (database connectivity)."""
    try:
        url = f"{API_BASE_URL}/api/podcasts/"
        print(f"Checking {url}...")
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        if resp.status_code == 200:
            podcasts = resp.json()
            log(f"Podcast list retrieved: {len(podcasts)} podcasts found")
            return True
        else:
            log(f"Podcast list failed: {resp.status_code} - {resp.text}", success=False)
            return False
    except Exception as e:
        log(f"Podcast list exception: {e}", success=False)
        return False

def main():
    print(f"--- Starting Health Check against {API_BASE_URL} ---")
    
    # 1. Basic Health
    if not check_health():
        sys.exit(1)
        
    # 2. Authentication
    token = login()
    if not token:
        sys.exit(1)
        
    # 3. Database Connectivity (via Podcasts)
    if not check_podcasts(token):
        sys.exit(1)
        
    print("\n🎉 All systems operational!")
    sys.exit(0)

if __name__ == "__main__":
    main()
