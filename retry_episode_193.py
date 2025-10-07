#!/usr/bin/env python3
"""
Emergency script to retry episode 193 on production
Usage: python retry_episode_193.py
"""
import requests
import sys
import json

def retry_episode(episode_id=193):
    """Retry a stuck episode via production API"""
    
    print(f"🔄 Attempting to retry episode {episode_id}...")
    print("="*60)
    
    # You'll need to get your auth token from the browser
    print("\n📋 INSTRUCTIONS:")
    print("1. Open https://app.podcastplusplus.com in your browser")
    print("2. Open Developer Tools (F12)")
    print("3. Go to Application > Local Storage > app.podcastplusplus.com")
    print("4. Find 'ppp_token' and copy its value")
    print("\nOr check Console > Network tab > any API request > Headers > Authorization")
    print("="*60)
    
    token = input("\n🔑 Paste your auth token here: ").strip()
    
    if not token:
        print("❌ No token provided. Exiting.")
        return False
    
    # Remove "Bearer " prefix if present
    if token.lower().startswith('bearer '):
        token = token[7:].strip()
    
    api_base = "https://app.podcastplusplus.com/api"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        print(f"\n🚀 Sending retry request to {api_base}/episodes/{episode_id}/retry...")
        response = requests.post(
            f"{api_base}/episodes/{episode_id}/retry",
            headers=headers,
            json={},
            timeout=30
        )
        
        if response.status_code == 200:
            print("✅ SUCCESS! Episode retry triggered.")
            try:
                data = response.json()
                print(f"\n📦 Response:")
                print(json.dumps(data, indent=2))
                if 'job_id' in data:
                    print(f"\n🆔 Job ID: {data['job_id']}")
                    print("   Check Episode History for progress!")
            except:
                print(response.text)
            return True
            
        elif response.status_code == 401:
            print("❌ Authentication failed. Token might be expired.")
            print("   Log out and log back in, then try again.")
            return False
            
        elif response.status_code == 404:
            print(f"❌ Episode {episode_id} not found.")
            return False
            
        else:
            print(f"❌ Error: HTTP {response.status_code}")
            print(response.text[:500])
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Request timed out. Server might be slow.")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ Connection error. Check your internet connection.")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = retry_episode(193)
    sys.exit(0 if success else 1)
