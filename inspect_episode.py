from sqlmodel import Session, select
from api.core.database import engine
from api.models.podcast import Episode

episode_id = "da01838f-3b31-4924-be24-4b796f5915fb"

with Session(engine) as session:
    ep = session.exec(select(Episode).where(Episode.id == episode_id)).first()
    if ep:
        print(f"Episode found: {ep.title}")
        print(f"Status: {ep.status}")
        print(f"GCS Audio Path: {ep.gcs_audio_path}")
        print(f"Publish At: {ep.publish_at}")
        print(f"Processed At: {ep.processed_at}")
    else:
        print("Episode not found")
