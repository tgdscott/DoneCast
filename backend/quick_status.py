import sys
sys.path.append('.')
from api.core.database import engine
from sqlmodel import Session
from sqlalchemy import text

episode_id = '62f66e9c-f04f-4550-8cdb-01fa0f2b1c9b'

try:
    with Session(engine) as session:
        result = session.execute(text('''
            SELECT status, final_audio_path, gcs_audio_path, processed_at
            FROM episode 
            WHERE id = :episode_id
        '''), {'episode_id': episode_id}).fetchone()
        
        if result:
            status, final_path, gcs_path, processed_at = result
            print(f"Episode Status: {status}")
            print(f"Final Audio Path: {final_path or 'None'}")
            print(f"GCS Audio Path: {gcs_path or 'None'}")
            print(f"Processed At: {processed_at or 'None'}")
            
            if status == 'processed':
                print("✅ EPISODE COMPLETED SUCCESSFULLY!")
            elif status == 'processing':
                print("⏳ Episode still processing...")
            elif status == 'error':
                print("❌ Episode failed with error")
            else:
                print(f"⚠️ Unknown status: {status}")
        else:
            print("Episode not found in database")
            
except Exception as e:
    print(f"Database error: {e}")
    print("This indicates INTRANS issues are still present")