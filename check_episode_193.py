#!/usr/bin/env python3
"""Quick script to check episode 193 status on production"""
import requests
import json

# Check episode 193 status
episode_id = 193
api_base = "https://app.podcastplusplus.com/api"

try:
    # Try to get episode details (public endpoint)
    print(f"Checking episode {episode_id}...")
    
    # Check job status if we have a job_id
    # First, let's see if we can query the episode
    response = requests.get(f"{api_base}/episodes/{episode_id}/status")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ Episode {episode_id} Status:")
        print(json.dumps(data, indent=2))
    elif response.status_code == 401:
        print(f"\n⚠️  Authentication required. Cannot check episode status without token.")
        print(f"The episode might be stuck in processing on the server.")
    else:
        print(f"\n❌ Error: HTTP {response.status_code}")
        print(response.text[:500])
        
except Exception as e:
    print(f"\n❌ Error checking episode: {e}")
    
print("\n" + "="*60)
print("RECOMMENDATION:")
print("="*60)
print("""
If episode is stuck in 'processing' status for 34+ minutes:

1. Check Cloud Run logs for worker errors
2. Check if Cloud Tasks queue is backed up
3. Consider triggering a retry:
   - Use the Episode History UI "Retry" button
   - Or manually trigger via API

The episode assembly likely:
a) Failed silently in the worker
b) Is stuck in Cloud Tasks queue
c) Timed out during transcription/assembly

Next steps:
1. Log into production UI
2. Click the episode actions menu
3. Look for "Retry" or "Check Status" option
""")
