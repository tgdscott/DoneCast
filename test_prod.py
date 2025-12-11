import requests
import json
import sys

# Add venv site-packages to path just in case, though executing with venv python is safer
# but we will rely on calling with venv python.

url = "https://podcast-api-kge7snpz7a-uw.a.run.app/api/episodes/precheck/minutes"
payload = {"template_id": "test_template_id_123", "main_content_filename": "test_file.mp3"}
headers = {"Content-Type": "application/json"}

print(f"--- Testing Production Endpoint ---")
print(f"URL: {url}")
try:
    response = requests.post(url, json=payload, headers=headers, timeout=10)
    print(f"Status Code: {response.status_code}")
    print(f"Response Body: {response.text}")
except Exception as e:
    print(f"Request failed: {e}")
