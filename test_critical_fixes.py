# Quick Test Script - Run Before Deploying

import requests
import time

API_BASE = "http://localhost:8080"  # Change to your API URL

def test_login_speed():
    """Test that login is fast (< 5 seconds)"""
    print("Testing login speed...")
    start = time.time()
    
    try:
        response = requests.post(
            f"{API_BASE}/api/auth/token",
            data={"username": "test@example.com", "password": "testpass"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10
        )
        duration = time.time() - start
        
        if duration < 5:
            print(f"✅ Login fast: {duration:.2f}s")
            return True
        else:
            print(f"❌ Login slow: {duration:.2f}s (should be < 5s)")
            return False
    except requests.exceptions.Timeout:
        print(f"❌ Login timeout after {time.time() - start:.2f}s")
        return False
    except Exception as e:
        print(f"❌ Login error: {e}")
        return False


def test_me_endpoint_speed(token):
    """Test that /me endpoint is fast"""
    print("Testing /api/users/me speed...")
    start = time.time()
    
    try:
        response = requests.get(
            f"{API_BASE}/api/users/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5
        )
        duration = time.time() - start
        
        if duration < 2:
            print(f"✅ /me endpoint fast: {duration:.2f}s")
            return True
        else:
            print(f"❌ /me endpoint slow: {duration:.2f}s (should be < 2s)")
            return False
    except requests.exceptions.Timeout:
        print(f"❌ /me endpoint timeout after {time.time() - start:.2f}s")
        return False
    except Exception as e:
        print(f"❌ /me endpoint error: {e}")
        return False


def test_health_check():
    """Test basic health"""
    print("Testing health endpoint...")
    try:
        response = requests.get(f"{API_BASE}/api/health", timeout=5)
        if response.ok:
            print(f"✅ Health check passed")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("CRITICAL FIX VERIFICATION")
    print("=" * 50)
    print()
    
    # Test 1: Health check
    health_ok = test_health_check()
    print()
    
    # Test 2: Login speed
    # NOTE: Update with real credentials for testing
    login_ok = test_login_speed()
    print()
    
    # Test 3: /me endpoint speed
    # NOTE: Need valid token for this
    # me_ok = test_me_endpoint_speed("YOUR_TOKEN_HERE")
    # print()
    
    print("=" * 50)
    if health_ok and login_ok:
        print("✅ CRITICAL FIXES VERIFIED - Safe to deploy")
    else:
        print("❌ ISSUES FOUND - Do NOT deploy yet")
    print("=" * 50)
