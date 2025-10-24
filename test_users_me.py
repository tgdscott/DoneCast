"""Test /api/users/me endpoint to verify role field is returned"""
import requests
import json

# First, login to get a token
login_url = "http://127.0.0.1:8000/api/auth/login"
login_payload = {
    "email": "scott@scottgerhardt.com",
    "password": "your_password_here"  # You'll need to provide this
}

print("Testing /api/users/me endpoint...")
print("=" * 60)

# You need to manually get a token - open browser dev tools, go to Application > Local Storage
# and copy the token value, then paste it here:
token_input = input("\nPaste your JWT token (from browser localStorage 'token' key): ").strip()

if not token_input:
    print("\n❌ No token provided. Cannot test.")
    print("\nTo get your token:")
    print("1. Open browser dev tools (F12)")
    print("2. Go to Application > Local Storage > http://127.0.0.1:5173")
    print("3. Find the 'token' key and copy its value")
    exit(1)

# Test /api/users/me
me_url = "http://127.0.0.1:8000/api/users/me"
headers = {"Authorization": f"Bearer {token_input}"}

try:
    response = requests.get(me_url, headers=headers)
    print(f"\nStatus Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print("\n✅ Response received:")
        print(json.dumps(data, indent=2, default=str))
        
        print("\n" + "=" * 60)
        print("KEY FIELDS CHECK:")
        print("=" * 60)
        print(f"Email: {data.get('email')}")
        print(f"Tier: {data.get('tier')}")
        print(f"Role: {data.get('role')}")
        print(f"is_admin: {data.get('is_admin')}")
        
        if data.get('role') == 'superadmin':
            print("\n✅ SUCCESS! Role field is 'superadmin'")
            print("   Admin Panel button should now appear after logout/login")
        elif data.get('role') is None:
            print("\n❌ PROBLEM: Role field is None (should be 'superadmin')")
        else:
            print(f"\n⚠️  UNEXPECTED: Role is '{data.get('role')}' (expected 'superadmin')")
    else:
        print(f"\n❌ Error: {response.status_code}")
        print(response.text)
        
except Exception as e:
    print(f"\n❌ Request failed: {e}")
