"""Check RSS feed URLs."""
import requests

urls_to_try = [
    'https://podcast-api-533915058549.us-west1.run.app/rss/cinema-irl/feed.xml',
    'https://podcast-api-533915058549.us-west1.run.app/v1/rss/cinema-irl/feed.xml',
    'https://www.podcastplusplus.com/rss/cinema-irl/feed.xml',
    'https://www.podcastplusplus.com/v1/rss/cinema-irl/feed.xml',
]

for url in urls_to_try:
    try:
        r = requests.get(url, timeout=5)
        is_xml = r.text.strip().startswith('<?xml')
        has_op3 = 'op3.dev' in r.text
        print(f"\n{url}")
        print(f"  Status: {r.status_code}")
        print(f"  Is XML: {is_xml}")
        print(f"  Has OP3: {has_op3}")
        if is_xml:
            print(f"  ✓ Valid RSS feed")
            if has_op3:
                print(f"  ✓ OP3 prefix found!")
    except Exception as e:
        print(f"\n{url}")
        print(f"  Error: {e}")
