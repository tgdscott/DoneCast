# Database Schema Updates for RSS Feed

## Required Fields for Proper RSS Feed Generation

The RSS 2.0 spec and iTunes require certain metadata that we should add to the Episode model.

## 1. Audio File Size (REQUIRED for RSS)

RSS `<enclosure>` tags require the `length` attribute (file size in bytes).

### Schema Change

```python
# Add to backend/api/models/podcast.py - Episode model
audio_file_size: Optional[int] = Field(
    default=None, 
    description="Audio file size in bytes (required for RSS enclosure tag)"
)
```

### Migration SQL

```sql
-- Add column to existing database
ALTER TABLE episode ADD COLUMN audio_file_size INTEGER;
```

### Populate During Assembly

```python
# In backend/worker/tasks/assembly/orchestrator.py
# After uploading to GCS, before saving episode:

import os

# Get local file size
local_audio_path = Path(FINAL_DIR) / episode.final_audio_path
if local_audio_path.exists():
    episode.audio_file_size = os.path.getsize(local_audio_path)
    logger.info(f"Episode {episode.id} audio size: {episode.audio_file_size} bytes")
```

### Backfill Existing Episodes

```python
# Script: backfill_audio_sizes.py

from pathlib import Path
from sqlmodel import Session, select
from api.models.podcast import Episode
from api.core.database import get_session
from api.core.paths import FINAL_DIR
from infrastructure.gcs import download_from_gcs
import tempfile
import os

def backfill_audio_sizes():
    """Backfill audio_file_size for existing episodes."""
    session = next(get_session())
    
    # Get episodes without file size
    episodes = session.exec(
        select(Episode)
        .where(Episode.audio_file_size == None)
        .where(Episode.final_audio_path != None)
    ).all()
    
    print(f"Found {len(episodes)} episodes to backfill")
    
    for episode in episodes:
        try:
            # Try local file first
            local_path = Path(FINAL_DIR) / episode.final_audio_path
            if local_path.exists():
                episode.audio_file_size = os.path.getsize(local_path)
                session.add(episode)
                print(f"✓ {episode.title}: {episode.audio_file_size} bytes (local)")
            
            # Try GCS if local not available
            elif episode.gcs_audio_path:
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    download_from_gcs(episode.gcs_audio_path, tmp.name)
                    episode.audio_file_size = os.path.getsize(tmp.name)
                    os.unlink(tmp.name)
                    session.add(episode)
                    print(f"✓ {episode.title}: {episode.audio_file_size} bytes (GCS)")
            
            else:
                print(f"✗ {episode.title}: No audio file found")
        
        except Exception as e:
            print(f"✗ {episode.title}: Error - {e}")
    
    session.commit()
    print(f"\nBackfill complete!")

if __name__ == "__main__":
    backfill_audio_sizes()
```

## 2. Duration (Recommended for Better UX)

iTunes feeds show duration prominently. Currently stored in `meta_json`, should be promoted to column.

### Schema Change

```python
# Add to backend/api/models/podcast.py - Episode model
duration_ms: Optional[int] = Field(
    default=None,
    description="Episode duration in milliseconds"
)
```

### Migration SQL

```sql
-- Add column
ALTER TABLE episode ADD COLUMN duration_ms INTEGER;

-- Backfill from existing data if available
-- (Your current code may already compute this during assembly)
```

### Update Assembly Code

```python
# In backend/worker/tasks/assembly/orchestrator.py
# After generating final audio:

from pydub import AudioSegment

# Get duration
audio = AudioSegment.from_file(final_audio_path)
episode.duration_ms = len(audio)
logger.info(f"Episode {episode.id} duration: {episode.duration_ms}ms ({episode.duration_ms / 1000 / 60:.1f} minutes)")
```

## 3. Migration Script

Run this in `backend/api/startup_tasks.py` to handle migrations automatically:

```python
def _ensure_rss_feed_columns() -> None:
    """Add columns needed for self-hosted RSS feed generation."""
    from sqlalchemy import inspect, text
    from api.core.database import engine

    with Session(engine) as conn:
        inspector = inspect(conn)
        cols = {c["name"] for c in inspector.get_columns("episode")}

        # Add audio_file_size column
        if "audio_file_size" not in cols:
            try:
                conn.exec_driver_sql("ALTER TABLE episode ADD COLUMN audio_file_size INTEGER")
                log.info("[migrate] Added episode.audio_file_size for RSS enclosures")
            except Exception as e:
                log.warning(f"[migrate] Could not add audio_file_size: {e}")

        # Add duration_ms column (may already exist)
        if "duration_ms" not in cols:
            try:
                conn.exec_driver_sql("ALTER TABLE episode ADD COLUMN duration_ms INTEGER")
                log.info("[migrate] Added episode.duration_ms for iTunes duration tag")
            except Exception as e:
                log.warning(f"[migrate] Could not add duration_ms: {e}")

        conn.commit()
```

## 4. RSS Feed Updates

Once columns are added, update `backend/api/routers/rss_feed.py`:

### File Size in Enclosure

```python
# Replace:
ET.SubElement(item, "enclosure", {
    "url": audio_url,
    "type": "audio/mpeg",
    "length": "0",  # TODO: Add actual file size
})

# With:
file_size = episode.audio_file_size or 0
ET.SubElement(item, "enclosure", {
    "url": audio_url,
    "type": "audio/mpeg",
    "length": str(file_size),
})
```

### Duration Tag

```python
# Already handled with getattr(), just ensure column exists:
duration_ms = getattr(episode, "duration_ms", None)
if duration_ms:
    ET.SubElement(item, "itunes:duration").text = _format_duration(duration_ms)
```

## 5. Checklist

- [ ] Add `audio_file_size` column to Episode model
- [ ] Add `duration_ms` column to Episode model (if not already present)
- [ ] Add migration script to `startup_tasks.py`
- [ ] Update assembly orchestrator to populate these fields
- [ ] Run backfill script for existing episodes
- [ ] Update RSS feed to use actual file sizes
- [ ] Test feed with validator - should show proper file sizes and durations
- [ ] Deploy to production

## 6. Testing

After adding these fields:

```powershell
# Test locally
# 1. Start API
python -m uvicorn api.main:app --reload

# 2. Check an episode in database
sqlite3 database.db
SELECT title, audio_file_size, duration_ms FROM episode WHERE id = 'YOUR_EPISODE_ID';

# 3. Check RSS feed
# Visit: http://localhost:8000/api/rss/{podcast_id}/feed.xml
# Look for: <enclosure ... length="12345678" />
# Look for: <itunes:duration>45:32</itunes:duration>

# 4. Validate
# Use https://castfeedvalidator.com/
# Should pass validation without "missing length" errors
```

## Priority

### Must Have (Before Production Launch)
- ✅ audio_file_size - RSS spec requires it
- ✅ Populate during assembly for new episodes

### Should Have (Better UX)
- ✅ duration_ms - Better user experience, most apps show it
- ⚠️ Backfill existing episodes (can be done post-launch)

### Nice to Have
- Audio codec info (mp3, aac, etc.)
- Bitrate
- Sample rate

## Estimated Effort

- Schema changes: 15 minutes
- Assembly updates: 15 minutes
- Backfill script: 30 minutes
- Testing: 30 minutes

**Total: ~1.5 hours**

## Notes

- These changes are backward compatible
- Existing episodes won't break
- RSS feed will use 0 for file size if not available (valid, but not ideal)
- Most podcast apps will still work without file size, but it's best practice to include it
