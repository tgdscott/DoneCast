import requests
import os
import sys
import traceback
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env.local')
load_dotenv('.env')

BASE_URL = "http://localhost:8000"
EMAIL = "test@example.com"
PASSWORD = "password123"

def get_token(f):
    # Try to login or register
    f.write(f"Attempting to login as {EMAIL}...\n")
    try:
        resp = requests.post(f"{BASE_URL}/api/auth/token", data={"username": EMAIL, "password": PASSWORD})
        
        if resp.status_code == 200:
            f.write("Login successful\n")
            return resp.json()["access_token"]
        
        f.write(f"Login failed: {resp.status_code} {resp.text}\n")
        
        # Try to register if login failed
        f.write("Attempting to register...\n")
        resp = requests.post(f"{BASE_URL}/api/auth/register", json={"email": EMAIL, "password": PASSWORD, "full_name": "Test User"})
        if resp.status_code == 201:
            f.write("Registration successful\n")
            # Login again
            resp = requests.post(f"{BASE_URL}/api/auth/token", data={"username": EMAIL, "password": PASSWORD})
            if resp.status_code == 200:
                return resp.json()["access_token"]
                
        f.write(f"Registration failed: {resp.status_code} {resp.text}\n")
        return None
    except Exception as e:
        f.write(f"Exception during auth: {e}\n")
        traceback.print_exc(file=f)
        return None

def reproduce():
    with open('reproduce_api_output.txt', 'w') as f:
        try:
            token = get_token(f)
            if not token:
                f.write("Could not get token, aborting\n")
                return

            f.write("Hitting /api/podcasts/...\n")
            headers = {"Authorization": f"Bearer {token}"}
            resp = requests.get(f"{BASE_URL}/api/podcasts/", headers=headers)
            
            f.write(f"Response Status: {resp.status_code}\n")
            f.write(f"Response Body: {resp.text}\n")
        except Exception as e:
            f.write(f"Exception during reproduction: {e}\n")
            traceback.print_exc(file=f)

if __name__ == "__main__":
    reproduce()
