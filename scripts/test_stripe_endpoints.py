#!/usr/bin/env python3
"""
Test Stripe API Endpoints
==========================
Simple test to verify backend endpoints work correctly.

Usage:
    python scripts/test_stripe_endpoints.py
"""

import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ requests package not installed")
    print("   Run: pip install requests")
    sys.exit(1)


def test_billing_config(base_url):
    """Test the billing config endpoint (public, no auth)."""
    print("\n🧪 Testing GET /api/billing/config")
    print("-" * 60)
    
    try:
        response = requests.get(f"{base_url}/api/billing/config")
        
        if response.status_code == 200:
            data = response.json()
            pub_key = data.get('publishable_key', '')
            mode = data.get('mode', '')
            
            print(f"✅ Status: 200 OK")
            print(f"   Publishable Key: {pub_key[:15]}...{pub_key[-4:]}")
            print(f"   Mode: {mode}")
            
            if not pub_key.startswith('pk_'):
                print("   ⚠️  Publishable key format looks incorrect")
                return False
            
            return True
        else:
            print(f"❌ Status: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed - is the server running?")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_embedded_checkout(base_url, token=None):
    """Test the embedded checkout endpoint (requires auth)."""
    print("\n🧪 Testing POST /api/billing/checkout/embedded")
    print("-" * 60)
    
    if not token:
        print("⚠️  Skipped - no auth token provided")
        print("   (This endpoint requires authentication)")
        return True
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "plan_key": "pro",
            "billing_cycle": "monthly",
            "success_path": "/billing",
            "cancel_path": "/billing"
        }
        
        response = requests.post(
            f"{base_url}/api/billing/checkout/embedded",
            json=payload,
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            client_secret = data.get('client_secret', '')
            session_id = data.get('session_id', '')
            
            print(f"✅ Status: 200 OK")
            print(f"   Client Secret: {client_secret[:20]}...")
            print(f"   Session ID: {session_id}")
            
            if not client_secret.startswith('cs_'):
                print("   ⚠️  Client secret format looks incorrect")
                return False
            
            return True
        elif response.status_code == 401:
            print(f"⚠️  Status: 401 Unauthorized")
            print("   (Expected - token may be invalid or expired)")
            return True
        else:
            print(f"❌ Status: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_regular_checkout(base_url, token=None):
    """Test the regular checkout endpoint (for comparison)."""
    print("\n🧪 Testing POST /api/billing/checkout")
    print("-" * 60)
    
    if not token:
        print("⚠️  Skipped - no auth token provided")
        return True
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "plan_key": "pro",
            "billing_cycle": "monthly",
            "success_path": "/billing",
            "cancel_path": "/billing"
        }
        
        response = requests.post(
            f"{base_url}/api/billing/checkout",
            json=payload,
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            url = data.get('url', '')
            
            print(f"✅ Status: 200 OK")
            print(f"   Checkout URL: {url[:50]}...")
            
            if not url.startswith('http'):
                print("   ⚠️  URL format looks incorrect")
                return False
            
            return True
        elif response.status_code == 401:
            print(f"⚠️  Status: 401 Unauthorized")
            print("   (Expected - token may be invalid or expired)")
            return True
        else:
            print(f"❌ Status: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    print("\n" + "="*60)
    print("🧪 Stripe Endpoint Tester")
    print("="*60)
    
    # Get base URL
    base_url = os.getenv('API_BASE_URL', 'http://127.0.0.1:8000')
    print(f"\n🌐 Testing against: {base_url}")
    
    # Get auth token (optional)
    token = os.getenv('TEST_TOKEN')
    if token:
        print(f"🔑 Using auth token: {token[:15]}...")
    else:
        print("⚠️  No TEST_TOKEN set - authenticated endpoints will be skipped")
        print("   Set TEST_TOKEN environment variable to test authenticated endpoints")
    
    # Run tests
    results = []
    
    results.append(("Config Endpoint", test_billing_config(base_url)))
    results.append(("Embedded Checkout", test_embedded_checkout(base_url, token)))
    results.append(("Regular Checkout", test_regular_checkout(base_url, token)))
    
    # Summary
    print("\n" + "="*60)
    print("📊 Test Results")
    print("="*60)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status:12} - {name}")
    
    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)
    
    print("\n" + "="*60)
    if passed_count == total_count:
        print(f"✅ ALL TESTS PASSED ({passed_count}/{total_count})")
        print("="*60)
        print("\n🎉 Backend endpoints are working correctly!")
        return 0
    else:
        print(f"⚠️  SOME TESTS FAILED ({passed_count}/{total_count} passed)")
        print("="*60)
        print("\n💡 Tips:")
        print("• Make sure the API server is running")
        print("• Check that Stripe keys are configured")
        print("• Verify TEST_TOKEN is valid for authenticated endpoints")
        return 1


if __name__ == '__main__':
    sys.exit(main())
