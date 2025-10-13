"""
Connect to production database and get episode UUIDs for episodes 195-201
Then check GCS and generate UPDATE SQL statements
"""
import os

# Set your production DATABASE_URL
# Get it from: gcloud run services describe podcast-api --region=us-west1 --format="value(spec.template.spec.containers[0].env[?name=='DATABASE_URL'].value)"

DATABASE_URL = os.getenv("DATABASE_URL") or input("Enter your DATABASE_URL: ").strip()

if not DATABASE_URL:
    print("❌ DATABASE_URL not set!")
    exit(1)

print("Connecting to database...")
print(f"URL: {DATABASE_URL[:30]}...") 

try:
    from sqlalchemy import create_engine, text
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT e.id, e.episode_number, e.title, e.gcs_audio_path
            FROM episode e
            JOIN podcast p ON e.podcast_id = p.id
            WHERE p.slug = 'cinema-irl'
              AND e.episode_number BETWEEN 195 AND 201
            ORDER BY e.episode_number
        """))
        
        episodes = list(result)
        
        if not episodes:
            print("❌ No episodes found!")
            exit(1)
        
        print(f"\n✅ Found {len(episodes)} episodes:\n")
        
        import subprocess
        bucket = "ppp-media-us-west1"
        base_path = "podcasts/cinema-irl/episodes"
        
        fix_statements = []
        
        for row in episodes:
            ep_id, ep_num, title, gcs_path = row
            print(f"Episode {ep_num}: {title[:50]}")
            print(f"  UUID: {ep_id}")
            print(f"  Current gcs_audio_path: {gcs_path or '(none)'}")
            
            # Check GCS
            gcs_folder = f"gs://{bucket}/{base_path}/{ep_id}/"
            result = subprocess.run(
                ["gcloud", "storage", "ls", gcs_folder],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                files = result.stdout.strip().split('\n')
                audio_file = None
                for f in files:
                    if f.endswith('.mp3') or f.endswith('.m4a') or f.endswith('.wav'):
                        audio_file = f
                        break
                
                if audio_file:
                    print(f"  ✅ Found audio: {audio_file}")
                    if not gcs_path or gcs_path != audio_file:
                        sql = f"UPDATE episode SET gcs_audio_path = '{audio_file}' WHERE id = '{ep_id}';"
                        fix_statements.append(sql)
                        print(f"  🔧 NEEDS FIX")
                    else:
                        print(f"  ✓ Already set correctly")
                else:
                    print(f"  ⚠️  No audio file found in GCS folder")
            else:
                print(f"  ❌ GCS folder not found: {gcs_folder}")
            
            print()
        
        if fix_statements:
            print("\n" + "="*70)
            print("🔧 SQL STATEMENTS TO FIX THE AUDIO PATHS:")
            print("="*70)
            print()
            for sql in fix_statements:
                print(sql)
            print()
            print("Run these in your database to fix the audio playback!")
        else:
            print("✅ All episodes already have correct GCS paths!")
            
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
