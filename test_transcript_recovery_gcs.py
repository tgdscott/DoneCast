"""Test script to verify transcript recovery from GCS after deployments.

This script simulates the user's issue:
1. Upload and transcribe a file
2. Simulate deployment (wipe local transcripts)
3. Verify transcript is recovered from GCS automatically

Run this after deployment to verify the fix works.
"""

import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

def test_transcript_recovery():
    """Test that transcripts are recovered from GCS after deployment."""
    from api.core.paths import TRANSCRIPTS_DIR
    from api.core.database import get_session
    from api.models.transcription import MediaTranscript
    from api.routers.media_read import _resolve_transcript_path
    import json
    
    print("=" * 80)
    print("TRANSCRIPT RECOVERY TEST")
    print("=" * 80)
    
    # Get database session
    session_gen = get_session()
    session = next(session_gen)
    
    try:
        # 1. Find a MediaTranscript record with GCS metadata
        print("\n1. Checking for MediaTranscript records with GCS metadata...")
        
        all_transcripts = session.query(MediaTranscript).all()
        print(f"   Found {len(all_transcripts)} total transcript records")
        
        gcs_transcripts = []
        for record in all_transcripts:
            try:
                meta = json.loads(record.transcript_meta_json or "{}")
                if meta.get("gcs_json") or meta.get("gcs_uri"):
                    gcs_transcripts.append((record, meta))
            except:
                pass
        
        print(f"   Found {len(gcs_transcripts)} records with GCS backup")
        
        if not gcs_transcripts:
            print("   ⚠️  No transcript records with GCS metadata found")
            print("   Upload and transcribe a file first, then run this test")
            return False
        
        # 2. Test recovery for each record
        print("\n2. Testing transcript recovery...")
        
        success_count = 0
        fail_count = 0
        
        for record, meta in gcs_transcripts[:5]:  # Test first 5
            filename = record.filename
            stem = Path(filename).stem
            
            print(f"\n   Testing: {filename}")
            print(f"     Stem: {stem}")
            print(f"     GCS URI: {meta.get('gcs_json', 'N/A')}")
            
            # Simulate post-deployment state (remove local file)
            local_path = TRANSCRIPTS_DIR / f"{stem}.json"
            had_local = local_path.exists()
            if had_local:
                print(f"     Local file exists: {local_path}")
                # Backup and remove to simulate deployment
                backup_content = local_path.read_bytes()
                local_path.unlink()
                print(f"     ✓ Removed local file to simulate deployment")
            else:
                print(f"     Local file missing (already simulates deployment)")
                backup_content = None
            
            # Test recovery
            try:
                recovered_path = _resolve_transcript_path(filename, session=session)
                
                if recovered_path.exists():
                    print(f"     ✅ SUCCESS: Transcript recovered to {recovered_path}")
                    success_count += 1
                    
                    # Verify content
                    content = recovered_path.read_text()
                    words = json.loads(content)
                    print(f"        Transcript has {len(words)} words")
                else:
                    print(f"     ❌ FAIL: Recovery returned path but file doesn't exist")
                    fail_count += 1
                
                # Restore backup if we had one
                if backup_content and not recovered_path.exists():
                    recovered_path.write_bytes(backup_content)
                    print(f"     Restored backup")
            
            except Exception as e:
                print(f"     ❌ EXCEPTION: {e}")
                fail_count += 1
                
                # Restore backup
                if backup_content:
                    local_path.write_bytes(backup_content)
                    print(f"     Restored backup after error")
        
        # 3. Summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        print(f"✅ Successful recoveries: {success_count}")
        print(f"❌ Failed recoveries: {fail_count}")
        
        if fail_count == 0 and success_count > 0:
            print("\n🎉 ALL TESTS PASSED! Transcripts are successfully recovered from GCS.")
            return True
        elif success_count > 0:
            print("\n⚠️  PARTIAL SUCCESS: Some transcripts recovered, some failed.")
            return False
        else:
            print("\n❌ ALL TESTS FAILED: Transcripts are NOT being recovered from GCS.")
            return False
    
    finally:
        session.close()


def check_environment():
    """Check that environment is properly configured."""
    print("\n" + "=" * 80)
    print("ENVIRONMENT CHECK")
    print("=" * 80)
    
    # Check TRANSCRIPTS_BUCKET
    bucket = os.getenv("TRANSCRIPTS_BUCKET")
    if bucket:
        print(f"✅ TRANSCRIPTS_BUCKET: {bucket}")
    else:
        print(f"❌ TRANSCRIPTS_BUCKET not set!")
        return False
    
    # Check TRANSCRIPTS_DIR
    from api.core.paths import TRANSCRIPTS_DIR
    print(f"✅ TRANSCRIPTS_DIR: {TRANSCRIPTS_DIR}")
    if TRANSCRIPTS_DIR.exists():
        print(f"   Directory exists with {len(list(TRANSCRIPTS_DIR.glob('*')))} files")
    else:
        print(f"   Directory doesn't exist (will be created on demand)")
    
    # Check database connection
    try:
        from api.core.database import get_session
        session_gen = get_session()
        session = next(session_gen)
        session.close()
        print(f"✅ Database connection working")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False
    
    # Check GCS client
    try:
        from infrastructure.gcs import download_bytes
        print(f"✅ GCS client available")
    except Exception as e:
        print(f"❌ GCS client not available: {e}")
        return False
    
    return True


if __name__ == "__main__":
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + " " * 20 + "TRANSCRIPT RECOVERY TEST SCRIPT" + " " * 27 + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "=" * 78 + "╝")
    
    # Check environment
    if not check_environment():
        print("\n❌ Environment check failed. Fix configuration and try again.")
        sys.exit(1)
    
    # Run test
    try:
        success = test_transcript_recovery()
        
        if success:
            print("\n✅ TEST PASSED: Fix is working correctly!")
            sys.exit(0)
        else:
            print("\n❌ TEST FAILED: Fix is not working as expected.")
            sys.exit(1)
    
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
