"""
Test production RSS feed and show the actual error.
"""
import requests

url = "https://app.podcastplusplus.com/api/rss/cinema-irl/feed.xml"

print(f"Testing: {url}\n")

try:
    response = requests.get(url, timeout=10)
    print(f"Status Code: {response.status_code}")
    print(f"Content Type: {response.headers.get('content-type')}")
    print(f"\nResponse:\n{response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
