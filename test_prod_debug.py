import requests
import json
import sys

url_precheck = "https://podcast-api-kge7snpz7a-uw.a.run.app/api/episodes/precheck/minutes"
url_debug = "https://podcast-api-kge7snpz7a-uw.a.run.app/api/debug/routes"

print(f"--- Fetching Debug Routes ---")
try:
    resp = requests.get(url_debug, timeout=10)
    print(f"Debug Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print("Availability:", json.dumps(data.get("availability"), indent=2))
        routes = data.get("routes", [])
        # Filter for relevant routes
        relevant = [r for r in routes if "precheck" in r["path"] or "minutes" in r["path"]]
        print("\nRelevant Routes:")
        for r in relevant:
            print(f"  {r['path']} {r['methods']}")
    else:
        print(f"Debug Body: {resp.text[:500]}")
except Exception as e:
    print(f"Debug request failed: {e}")

print(f"\n--- Retrying Precheck (just in case) ---")
payload = {"template_id": "test", "main_content_filename": "test.mp3"}
try:
    resp = requests.post(url_precheck, json=payload, timeout=10)
    print(f"Precheck Status: {resp.status_code}")
    # print(resp.text)
except Exception as e:
    print(f"Precheck failed: {e}")
