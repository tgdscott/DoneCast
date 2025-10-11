"""Check if OP3 prefix is in RSS feed."""
import requests
import xml.etree.ElementTree as ET

r = requests.get('https://www.podcastplusplus.com/v1/rss/cinema-irl/feed.xml')
print(f"RSS Status: {r.status_code}")

if 'op3.dev' in r.text:
    print("✓ OP3 prefix found in feed!")
else:
    print("✗ OP3 prefix NOT found in feed")

# Parse feed and check first enclosure URL
try:
    root = ET.fromstring(r.content)
    enclosures = root.findall('.//enclosure')
    if enclosures:
        first_url = enclosures[0].get('url', '')
        print(f"\nFirst enclosure URL (truncated):")
        print(first_url[:120] + "...")
        
        if 'op3.dev' in first_url:
            print("\n✓ OP3 prefix is active in audio URLs")
        else:
            print("\n✗ OP3 prefix not in audio URLs")
except Exception as e:
    print(f"Error parsing: {e}")
