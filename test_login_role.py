"""Test login and check if role field is returned"""
import requests
import json
import sys

# Get password from command line or prompt
if len(sys.argv) > 1:
    password = sys.argv[1]
else:
    password = input("Enter password for scott@scottgerhardt.com: ")

# Login
print("🔐 Logging in as scott@scottgerhardt.com...")
try:
    login_response = requests.post(
        "http://127.0.0.1:8000/api/auth/login",
        json={
            "email": "scott@scottgerhardt.com",
            "password": password
        },
        timeout=5
    )
except Exception as e:
    print(f"❌ Connection failed: {e}")
    exit(1)

if login_response.status_code != 200:
    print(f"❌ Login failed: {login_response.status_code}")
    print(login_response.text)
    exit(1)

login_data = login_response.json()
token = login_data.get("access_token")
print(f"✅ Login successful, got token")

# Get user data
print("\n📡 Fetching /api/users/me...")
me_response = requests.get(
    "http://127.0.0.1:8000/api/users/me",
    headers={"Authorization": f"Bearer {token}"}
)

if me_response.status_code != 200:
    print(f"❌ /users/me failed: {me_response.status_code}")
    print(me_response.text)
    exit(1)

user_data = me_response.json()
print(f"\n✅ Got user data:")
print(json.dumps(user_data, indent=2))

# Check role field
role = user_data.get("role")
tier = user_data.get("tier")
is_admin = user_data.get("is_admin")

print(f"\n🎯 KEY FIELDS:")
print(f"   role: {role}")
print(f"   tier: {tier}")
print(f"   is_admin: {is_admin}")

if role == "superadmin":
    print(f"\n✅ SUCCESS! Role is 'superadmin' - admin features should work")
else:
    print(f"\n❌ PROBLEM! Role is '{role}' (expected 'superadmin')")
    print(f"   Frontend won't show admin features without role='superadmin'")
