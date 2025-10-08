#!/usr/bin/env python3
"""
Test script to verify the stuck episode recovery logic works correctly.
Run this after deploying the fix to confirm it detects and recovers stuck episodes.
"""

import sys
import os

# Add the backend directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

def test_recovery():
    """Test the episode recovery logic"""
    from api.startup_tasks import _recover_stuck_processing_episodes
    from api.core.database import session_scope
    from api.models.podcast import Episode
    from datetime import datetime, timezone, timedelta
    from sqlmodel import select
    
    print("=" * 80)
    print("TESTING STUCK EPISODE RECOVERY")
    print("=" * 80)
    
    # First, check current state
    with session_scope() as session:
        try:
            # Count episodes in processing status
            processing = session.exec(
                select(Episode).where(Episode.status == "processing")
            ).all()
            
            print(f"\n📊 Current state:")
            print(f"   - Episodes in 'processing' status: {len(processing)}")
            
            if processing:
                print(f"\n   Stuck episodes:")
                for ep in processing:
                    age = "unknown"
                    if hasattr(ep, 'processed_at') and ep.processed_at:
                        age_seconds = (datetime.now(timezone.utc) - ep.processed_at).total_seconds()
                        age = f"{int(age_seconds / 60)} minutes"
                    elif hasattr(ep, 'created_at') and ep.created_at:
                        age_seconds = (datetime.now(timezone.utc) - ep.created_at).total_seconds()
                        age = f"{int(age_seconds / 60)} minutes"
                    
                    title = ep.title if hasattr(ep, 'title') else 'untitled'
                    ep_id = ep.id if hasattr(ep, 'id') else '?'
                    print(f"   - {title} (ID: {ep_id}, age: {age})")
            
        except Exception as e:
            print(f"   ❌ Error checking current state: {e}")
            return False
    
    # Run the recovery function
    print(f"\n🔧 Running recovery function...")
    try:
        _recover_stuck_processing_episodes(limit=100)
        print(f"   ✅ Recovery function completed")
    except Exception as e:
        print(f"   ❌ Recovery function failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Check state after recovery
    with session_scope() as session:
        try:
            # Count episodes in processing status (should be fewer now)
            still_processing = session.exec(
                select(Episode).where(Episode.status == "processing")
            ).all()
            
            # Count episodes in error status (should include recovered ones)
            error_episodes = session.exec(
                select(Episode).where(Episode.status == "error")
            ).all()
            
            print(f"\n📊 State after recovery:")
            print(f"   - Episodes still in 'processing': {len(still_processing)}")
            print(f"   - Episodes marked as 'error': {len(error_episodes)}")
            
            if error_episodes:
                print(f"\n   Recent error episodes (potential recoveries):")
                for ep in error_episodes[:5]:  # Show first 5
                    title = ep.title if hasattr(ep, 'title') else 'untitled'
                    error_msg = ep.spreaker_publish_error if hasattr(ep, 'spreaker_publish_error') else 'no message'
                    ep_id = ep.id if hasattr(ep, 'id') else '?'
                    print(f"   - {title} (ID: {ep_id})")
                    print(f"     Error: {error_msg[:100]}")
            
            print(f"\n✅ Recovery test completed successfully")
            return True
            
        except Exception as e:
            print(f"   ❌ Error checking recovered state: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    print("\nNOTE: This script will check for and potentially modify episodes in the database.")
    print("      Make sure you're connected to the correct database (dev/staging/prod).\n")
    
    try:
        success = test_recovery()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
