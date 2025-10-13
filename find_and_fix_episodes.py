"""
Get episode UUIDs for Cinema IRL episodes 195-201 and check/fix their GCS paths
"""
import os
import subprocess

# Get the episode IDs from your production database
# You'll need to run this SQL query first
print("="*70)
print("STEP 1: Get Episode UUIDs")
print("="*70)
print("\nRun this SQL query in your Cloud SQL console:")
print()
print("""
SELECT id, episode_number, title, gcs_audio_path
FROM episode
WHERE podcast_id = (SELECT id FROM podcast WHERE slug = 'cinema-irl')
  AND episode_number BETWEEN 195 AND 201
ORDER BY episode_number;
""")
print()
print("Copy the output and paste the UUIDs below, then we'll check GCS and fix the paths.")
print()

# Manual entry for now - you'll paste the UUIDs here after running the SQL
episodes_to_fix = {
    # Paste like this:
    # 195: "uuid-here",
    # 196: "uuid-here",
    # etc.
}

if not episodes_to_fix:
    print("⚠️  No episode UUIDs entered yet.")
    print("   Run the SQL query above, then update this script with the UUIDs.")
    print()
    print("BUCKET: gs://ppp-media-us-west1/podcasts/cinema-irl/episodes/")
else:
    print("\n" + "="*70)
    print("STEP 2: Check GCS and Generate Fix SQL")
    print("="*70)
    
    bucket = "ppp-media-us-west1"
    base_path = "podcasts/cinema-irl/episodes"
    
    for ep_num, uuid in episodes_to_fix.items():
        gcs_path = f"gs://{bucket}/{base_path}/{uuid}/"
        print(f"\nEpisode {ep_num} (UUID: {uuid}):")
        
        # Check if folder exists
        result = subprocess.run(
            ["gcloud", "storage", "ls", gcs_path],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            files = result.stdout.strip().split('\n')
            audio_file = None
            for f in files:
                if f.endswith('.mp3') or f.endswith('.m4a'):
                    audio_file = f
                    break
            
            if audio_file:
                print(f"  ✅ Found audio: {audio_file}")
                print(f"  SQL: UPDATE episode SET gcs_audio_path = '{audio_file}' WHERE id = '{uuid}';")
            else:
                print(f"  ⚠️  Folder exists but no audio file found")
                print(f"     Files: {files}")
        else:
            print(f"  ❌ GCS folder not found!")
