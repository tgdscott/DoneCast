import sys
sys.path.insert(0, 'backend')

from api.core.database import get_session
from api.models.podcast import Episode
from sqlmodel import select
import json

session = next(get_session())
ep = session.exec(select(Episode).where(Episode.id == 215)).first()

if not ep:
    print("Episode 215 not found!")
else:
    print(f"Episode 215: {ep.title}")
    print(f"  status: {ep.status}")
    print(f"  working_audio_name: {ep.working_audio_name}")
    
    meta = json.loads(ep.meta_json or '{}')
    ai_features = meta.get('ai_features', {})
    
    print(f"\nAI Features:")
    print(f"  intern_enabled: {ai_features.get('intern_enabled')}")
    print(f"  intents: {ai_features.get('intents', [])}")
    
    intern_overrides = meta.get('intern_overrides', {})
    print(f"\nIntern Overrides:")
    if intern_overrides:
        for key, value in intern_overrides.items():
            print(f"  {key}: {value}")
    else:
        print("  NONE")
    
    # Check for Intern-related data
    print(f"\nTranscript data:")
    transcripts = meta.get('transcripts', {})
    print(f"  transcripts keys: {list(transcripts.keys())}")
    
    print(f"\nCleaned audio:")
    print(f"  cleaned_audio: {meta.get('cleaned_audio')}")
    print(f"  cleaned_audio_gcs_uri: {meta.get('cleaned_audio_gcs_uri')}")
