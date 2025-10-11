# Production Deployment Checklist - RSS Feed

**Date**: October 8, 2025  
**Target**: Cloud Run + PostgreSQL

## ✅ Pre-Deployment Checklist

### 1. Configuration
- [x] RSS feed domain fixed: Uses `podcastplusplus.com` via `settings.PODCAST_WEBSITE_BASE_DOMAIN`
- [ ] Set `APP_BASE_URL` environment variable in Cloud Run (e.g., `https://app.podcastplusplus.com`)
- [ ] Verify GCS credentials are configured for signed URL generation
- [ ] Check GCS bucket permissions for audio/cover files

### 2. Database Migrations
The startup_tasks.py has migrations for PostgreSQL, but we need to ensure ALL columns exist:

**RSS Feed Columns** (already in startup_tasks.py):
- ✅ `episode.audio_file_size` 
- ✅ `episode.duration_ms`
- ✅ `podcast.slug`

**Other Required Columns** (need to add to startup_tasks.py):
- [ ] `episode.gcs_audio_path`
- [ ] `episode.gcs_cover_path`
- [ ] `episode.has_numbering_conflict`
- [ ] `episode.original_guid`
- [ ] `episode.source_media_url`
- [ ] `episode.source_published_at`
- [ ] `episode.source_checksum`

### 3. Code Changes Needed

**A. Add missing column migrations to startup_tasks.py**
```python
def _ensure_episode_gcs_columns() -> None:
    """Add GCS and import-related columns to episode table."""
    backend = engine.url.get_backend_name()
    
    statements = [
        'ALTER TABLE episode ADD COLUMN IF NOT EXISTS gcs_audio_path VARCHAR',
        'ALTER TABLE episode ADD COLUMN IF NOT EXISTS gcs_cover_path VARCHAR',
        'ALTER TABLE episode ADD COLUMN IF NOT EXISTS has_numbering_conflict BOOLEAN DEFAULT FALSE',
        'ALTER TABLE episode ADD COLUMN IF NOT EXISTS original_guid VARCHAR',
        'ALTER TABLE episode ADD COLUMN IF NOT EXISTS source_media_url VARCHAR',
        'ALTER TABLE episode ADD COLUMN IF NOT EXISTS source_published_at TIMESTAMP',
        'ALTER TABLE episode ADD COLUMN IF NOT EXISTS source_checksum VARCHAR',
    ]
    
    try:
        with engine.connect() as conn:
            for stmt in statements:
                if backend == "postgresql":
                    conn.exec_driver_sql(stmt)
                elif backend == "sqlite":
                    # Remove IF NOT EXISTS for SQLite
                    stmt_clean = stmt.replace(" IF NOT EXISTS", "")
                    conn.exec_driver_sql(stmt_clean)
            log.info("[migrate] Ensured episode GCS columns exist")
    except Exception as exc:
        log.warning("[migrate] Unable to ensure episode GCS columns: %s", exc)
```

**B. Register new migration in startup sequence**
Add to the list around line 663:
```python
_ensure_episode_gcs_columns()
```

### 4. Deployment Steps

#### Option 1: Using gcloud (Recommended)
```bash
# From project root
cd /d/PodWebDeploy

# Build and deploy
gcloud run deploy ppp-api \
  --source . \
  --region us-west1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars APP_BASE_URL=https://app.podcastplusplus.com

# Check logs
gcloud run services logs read ppp-api --region us-west1 --limit 50
```

#### Option 2: Using Cloud Build
```bash
# Trigger cloud build
gcloud builds submit --config cloudbuild.yaml

# Or use the local cloudbuild
gcloud builds submit --config cloudbuild-local.yaml
```

### 5. Post-Deployment Testing

**A. Check migrations ran**
```bash
# View startup logs
gcloud run services logs read ppp-api --region us-west1 --limit 100 | grep migrate
```

Should see:
```
[migrate] Added episode.audio_file_size for RSS enclosures
[migrate] Added episode.duration_ms for iTunes duration tag
[migrate] Added podcast.slug for friendly RSS URLs
[migrate] Auto-generated slugs for X existing podcast(s)
[migrate] Ensured episode GCS columns exist
```

**B. Test RSS feed endpoint**
```bash
# Get your production podcast slug from database
# Then test the feed
curl https://app.podcastplusplus.com/api/rss/cinema-irl/feed.xml | head -50

# Or test with a specific podcast
curl https://app.podcastplusplus.com/api/rss/the-von-murder-show/feed.xml
```

**C. Validate feed**
1. Copy RSS feed URL: `https://app.podcastplusplus.com/api/rss/cinema-irl/feed.xml`
2. Go to https://castfeedvalidator.com/
3. Paste URL and validate
4. Fix any errors (missing required fields, invalid XML, etc.)

**D. Test in podcast app**
1. Copy RSS feed URL
2. Open podcast app (Apple Podcasts, Pocket Casts, etc.)
3. Add podcast by URL
4. Verify:
   - Podcast details load correctly
   - Episodes appear in order
   - Audio files play (signed URLs work)
   - Cover images display

### 6. Environment Variables for Production

**Required in Cloud Run**:
```bash
# Core
APP_ENV=production
APP_BASE_URL=https://app.podcastplusplus.com

# Database (Cloud SQL)
DB_USER=your_db_user
DB_PASS=your_db_password
DB_NAME=your_db_name
INSTANCE_CONNECTION_NAME=project:region:instance

# GCS (for signed URLs)
# Should be automatically available via Cloud Run service account
# Or set GOOGLE_APPLICATION_CREDENTIALS if needed

# If using secret manager:
gcloud run services update ppp-api \
  --update-secrets DATABASE_URL=database-url:latest \
  --region us-west1
```

### 7. Monitoring

**Check for errors**:
```bash
# Recent errors
gcloud run services logs read ppp-api --region us-west1 --limit 100 | grep ERROR

# RSS feed specific logs
gcloud run services logs read ppp-api --region us-west1 --limit 100 | grep rss

# GCS signed URL errors
gcloud run services logs read ppp-api --region us-west1 --limit 100 | grep "signed URL"
```

### 8. Rollback Plan

If RSS feed has issues on production:

1. **Quick fix**: RSS endpoint returns error, normal operation unaffected
2. **Comment out router registration** in `routing.py`:
   ```python
   # rss_feed_router,  # Temporarily disabled
   ```
3. **Redeploy** with commented line
4. **Fix issues locally** and test thoroughly
5. **Re-enable and redeploy**

## 📋 Quick Deploy Commands

```powershell
# Activate virtual environment
& D:\PodWebDeploy\.venv\Scripts\Activate.ps1

# Run local tests first
python -m pytest tests/

# Deploy to production
cd D:\PodWebDeploy
gcloud run deploy ppp-api --source . --region us-west1

# Monitor deployment
gcloud run services logs tail ppp-api --region us-west1

# Test production RSS feed
curl https://app.podcastplusplus.com/api/rss/cinema-irl/feed.xml
```

## 🚨 Critical Notes

1. **PostgreSQL UNIQUE constraint**: The `podcast.slug` column has UNIQUE constraint in PostgreSQL migration. This may fail if duplicates exist. Handle with:
   ```sql
   -- Check for duplicates first
   SELECT slug, COUNT(*) FROM podcast GROUP BY slug HAVING COUNT(*) > 1;
   ```

2. **GCS Signed URLs**: Require proper service account permissions:
   - `storage.objects.get`
   - `iam.serviceAccounts.signBlob`

3. **Backfill Episode Metadata**: After migrations, you need to backfill:
   ```bash
   # Run backfill script on production (connect to Cloud SQL)
   python backfill_episode_metadata.py
   ```

4. **Don't delete sentinel file on production**: The `/tmp/ppp_startup_done` is good - prevents re-running migrations on every scale-up.

## Next Steps

1. ✅ Fix domain in RSS feed (DONE)
2. ⬜ Add missing column migrations to startup_tasks.py
3. ⬜ Test locally one more time
4. ⬜ Deploy to production
5. ⬜ Test production RSS feed
6. ⬜ Validate with online tools
7. ⬜ Test in podcast app

---

**Status**: Ready for migration code updates, then production deployment 🚀
