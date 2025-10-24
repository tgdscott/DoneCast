"""
Quick test script to verify the DELETE /api/admin/users/{user_id} endpoint exists
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from fastapi.testclient import TestClient
from api.app import app

client = TestClient(app)

# Test that the endpoint exists (without auth, should get 401/403, not 405)
response = client.delete("/api/admin/users/test-user-id", json={"confirm_email": "test@example.com"})

print(f"Status Code: {response.status_code}")
print(f"Response: {response.json()}")

if response.status_code == 405:
    print("\n❌ ERROR: 405 Method Not Allowed - DELETE route is NOT registered!")
elif response.status_code in [401, 403]:
    print("\n✅ SUCCESS: DELETE route EXISTS (got expected auth error)")
elif response.status_code == 422:
    print("\n✅ SUCCESS: DELETE route EXISTS (got validation error - wrong ID format)")
else:
    print(f"\n⚠️  Unexpected status code: {response.status_code}")

# List all routes
print("\n📋 Checking registered routes...")
for route in app.routes:
    if hasattr(route, 'path') and hasattr(route, 'methods') and 'admin' in route.path.lower():
        print(f"  {route.methods} {route.path}")
