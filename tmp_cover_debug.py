from sqlalchemy import create_engine, text
from api.core.config import settings

engine = create_engine(settings.DATABASE_URL)
with engine.connect() as conn:
    result = conn.execute(text(
        "SELECT id, title, gcs_cover_path, cover_path, remote_cover_url "
        "FROM episodes "
        "WHERE gcs_cover_path IS NOT NULL "
        "ORDER BY created_at DESC LIMIT 5"
    ))
    for r in result:
        print(f"ID: {r[0]}")
        print(f"Title: {r[1]}")
        print(f"GCS: {r[2]}")
        print(f"Cover: {r[3]}")
        print(f"Remote: {r[4]}")
        print()
