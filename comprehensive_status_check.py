#!/usr/bin/env python3

import sys
import os
import json
import time
sys.path.append('backend')
os.chdir('backend')

def check_production_logs():
    """Check recent production logs for the episode."""
    print("=== RECENT PRODUCTION LOGS ===")
    
    # Check for episode assembly completion
    episode_id = "62f66e9c-f04f-4550-8cdb-01fa0f2b1c9b"
    
    # Log patterns to search for
    log_commands = [
        f'gcloud logging read "jsonPayload.episode_id=\\"{episode_id}\\" OR textPayload~\\"{episode_id}\\"" --limit=10 --format="value(timestamp,severity,jsonPayload.message,textPayload)" --project=podcast612',
        
        # Check for INTRANS errors in last 30 minutes
        'gcloud logging read "severity>=WARNING AND (jsonPayload.message~\\"INTRANS\\" OR textPayload~\\"INTRANS\\")" --limit=5 --format="value(timestamp,severity,jsonPayload.message,textPayload)" --project=podcast612',
        
        # Check assembly completion status
        f'gcloud logging read "jsonPayload.message~\\"assemble.*done\\" AND (jsonPayload.episode_id=\\"{episode_id}\\" OR textPayload~\\"{episode_id}\\")" --limit=3 --format="value(timestamp,severity,jsonPayload.message)" --project=podcast612',
        
        # Check for database commit issues
        'gcloud logging read "severity>=ERROR AND jsonPayload.message~\\"commit.*failed\\"" --limit=5 --format="value(timestamp,severity,jsonPayload.message)" --project=podcast612'
    ]
    
    for i, cmd in enumerate(log_commands, 1):
        print(f"\n--- Log Query {i} ---")
        print(f"Command: {cmd}")
        print("\nTo run manually:")
        print(f"  {cmd}")
    
    print("\n" + "="*50)

def check_episode_via_api():
    """Check episode status via production API."""
    print("\n=== PRODUCTION API CHECK ===")
    
    episode_id = "62f66e9c-f04f-4550-8cdb-01fa0f2b1c9b"
    
    api_checks = [
        f"curl -s 'https://api.podcastplusplus.com/api/episodes/status/{episode_id}' | python -m json.tool",
        
        f"curl -s 'https://api.podcastplusplus.com/api/episodes/{episode_id}' -H 'Authorization: Bearer YOUR_TOKEN' | python -m json.tool",
        
        # Check if chunked processing files exist in GCS
        f"gsutil ls gs://ppp-media-us-west1/b6d5f77e699e444ba31ae1b4cb15feb4/chunks/{episode_id}/",
        
        # Check final audio in GCS
        f"gsutil ls gs://ppp-media-us-west1/b6d5f77e699e444ba31ae1b4cb15feb4/episodes/"
    ]
    
    for i, cmd in enumerate(api_checks, 1):
        print(f"\n--- API Check {i} ---")
        print(f"  {cmd}")
    
    print("\n" + "="*50)

def check_database_health():
    """Check database connection health."""
    print("\n=== DATABASE CONNECTION HEALTH ===")
    
    try:
        from api.core.database import engine
        from sqlalchemy import text
        from sqlmodel import Session
        
        print("✅ Database imports successful")
        
        # Test basic connection
        with Session(engine) as session:
            result = session.execute(text("SELECT 1")).scalar()
            print(f"✅ Basic connection test: {result}")
            
        # Check connection pool status
        pool = engine.pool
        print(f"📊 Connection Pool Status:")
        print(f"   Size: {pool.size()}")
        print(f"   Checked out: {pool.checkedout()}")
        print(f"   Overflow: {pool.overflow()}")
        
        # Check for the specific episode
        with Session(engine) as session:
            result = session.execute(text('''
                SELECT 
                    id, 
                    title, 
                    status, 
                    final_audio_path, 
                    gcs_audio_path,
                    created_at,
                    processed_at,
                    working_audio_name
                FROM episode 
                WHERE id = :episode_id
            '''), {'episode_id': '62f66e9c-f04f-4550-8cdb-01fa0f2b1c9b'}).fetchone()
            
            if result:
                print(f"\n📝 Episode Status in Database:")
                print(f"   ID: {result[0]}")
                print(f"   Title: {result[1]}")
                print(f"   Status: {result[2]} {'✅' if result[2] == 'processed' else '⏳' if result[2] == 'processing' else '❌'}")
                print(f"   Final Audio Path: {result[3] or 'None'}")
                print(f"   GCS Audio Path: {result[4] or 'None'}")
                print(f"   Created At: {result[5]}")
                print(f"   Processed At: {result[6] or 'None'}")
                print(f"   Working Audio Name: {result[7] or 'None'}")
                
                return result[2] == 'processed'
            else:
                print("❌ Episode not found in database")
                return False
            
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("\nThis suggests the INTRANS issues are still affecting connections.")
        return False

def main():
    print("🔍 COMPREHENSIVE EPISODE & SYSTEM STATUS CHECK")
    print("=" * 60)
    
    # Check database first
    is_episode_complete = check_database_health()
    
    # Show log checking commands
    check_production_logs()
    
    # Show API checking commands  
    check_episode_via_api()
    
    print(f"\n📋 SUMMARY:")
    if is_episode_complete:
        print("✅ Episode appears to be COMPLETED in database")
        print("   - The daemon fix may have worked!")
        print("   - Check GCS for final audio file")
    else:
        print("⏳ Episode is still PROCESSING or has issues")
        print("   - May still be running (check logs)")
        print("   - May be stuck due to INTRANS issues")
        print("   - Check production logs for current status")
    
    print(f"\n🚀 NEXT STEPS:")
    print("1. Run the log queries above to see real-time status")
    print("2. Check if deployment completed successfully")
    print("3. If episode is stuck, we may need to restart Cloud Run service")
    
    print("\n" + "="*60)

if __name__ == '__main__':
    main()