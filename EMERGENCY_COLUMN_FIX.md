# Emergency Column Addition Script

## Problem

Deployment failed because new columns (`gcs_audio_path`, `gcs_cover_path`, `has_numbering_conflict`) were added to the Episode model but the database migration didn't complete before queries tried to use them.

Error:
```
psycopg.errors.UndefinedColumn: column episode.gcs_audio_path does not exist
```

## Root Cause

The migration in `startup_tasks.py` runs during container startup, but:
1. SQLModel metadata might be cached
2. First request hits before migration completes
3. Database transaction might not be committed immediately

## Solution

### Option 1: Add Columns Manually (RECOMMENDED - FASTEST)

Connect to Cloud SQL and run:
```sql
ALTER TABLE episode ADD COLUMN IF NOT EXISTS gcs_audio_path VARCHAR;
ALTER TABLE episode ADD COLUMN IF NOT EXISTS gcs_cover_path VARCHAR;  
ALTER TABLE episode ADD COLUMN IF NOT EXISTS has_numbering_conflict BOOLEAN DEFAULT FALSE;
```

Then redeploy the broken revision.

### Option 2: Fix Migration Order (PROPER FIX)

The issue is that `startup_tasks.py` runs migrations, but the SQLModel metadata is already loaded with the new columns. We need to:

1. Separate schema changes into a "pre-deploy" migration script
2. Run schema changes BEFORE deploying code that uses them
3. Add a startup health check that verifies columns exist

### Option 3: Make Code Handle Missing Columns

Wrap column access in try/except and gracefully degrade if columns don't exist yet. But this is messy.

## Immediate Action

**I've rolled back to revision `podcast-api-00446-g5f` so the site works now.**

To proceed with the fixes:

1. **Add columns manually** via Cloud SQL console or gcloud
2. **Redeploy** the latest code (it will work once columns exist)
3. **Future**: Add column existence checks before querying them

## Commands to Fix

```bash
# Option A: Via gcloud SQL proxy
gcloud sql connect podcast-db --user=postgres --database=podcast_db --project=podcast612

# Then in psql:
ALTER TABLE episode ADD COLUMN IF NOT EXISTS gcs_audio_path VARCHAR;
ALTER TABLE episode ADD COLUMN IF NOT EXISTS gcs_cover_path VARCHAR;
ALTER TABLE episode ADD COLUMN IF NOT EXISTS has_numbering_conflict BOOLEAN DEFAULT FALSE;

# Option B: Via Cloud SQL console
# 1. Go to: https://console.cloud.google.com/sql/instances/podcast-db?project=podcast612
# 2. Click "Open Cloud Shell"
# 3. Run the ALTER TABLE commands above

# After columns are added:
gcloud run services update-traffic podcast-api --to-revisions=podcast-api-00447-qvb=100 --region=us-west1 --project=podcast612
```

## Prevention for Future

Add this to `startup_tasks.py` BEFORE any migrations:
```python
def _verify_and_wait_for_migration(session, table_name, column_name, max_retries=10):
    """Wait for column to exist after migration."""
    for i in range(max_retries):
        try:
            session.execute(f"SELECT {column_name} FROM {table_name} LIMIT 1")
            return True
        except:
            if i < max_retries - 1:
                time.sleep(1)
    return False
```

Then call it after each migration:
```python
conn.exec_driver_sql("ALTER TABLE episode ADD COLUMN gcs_audio_path VARCHAR NULL")
_verify_and_wait_for_migration(session, "episode", "gcs_audio_path")
```
