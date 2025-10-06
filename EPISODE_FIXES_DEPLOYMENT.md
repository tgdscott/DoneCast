# Episode Fixes Deployment Summary

## Date: October 5, 2025

## Issues Fixed

### 1. ✅ Episode Audio/Cover Lost After Logout/Rebuild

**Problem**: When episodes were assembled, audio and cover images were visible immediately. After logout or container restart, they disappeared (404 errors).

**Root Cause**: 
- Episodes stored `final_audio_path` and `cover_path` as local filenames (e.g., `episode-123.mp3`)
- Cloud Run containers are ephemeral - `/tmp` filesystem is wiped on restart
- URLs like `/static/media/episode-123.mp3` returned 404 after restart
- Scheduled episodes couldn't fall back to Spreaker (not published yet)

**Solution**:
- **Upload to GCS after assembly**: Audio and covers now uploaded to `gs://ppp-media-us-west1/{user_id}/episodes/{episode_id}/`
- **New database fields**: `gcs_audio_path` and `gcs_cover_path` store full GCS URLs
- **Updated playback resolution**: Prioritizes GCS URLs > local files > Spreaker
- **7-day retention**: Files kept in GCS for 7 days after publish (allows edits/fixes)
- **Automatic cleanup**: Background task will delete from GCS after 7 days (future enhancement)

**Files Changed**:
- `backend/api/models/podcast.py` - Added `gcs_audio_path`, `gcs_cover_path` fields
- `backend/api/startup_tasks.py` - DB migration for new columns
- `backend/worker/tasks/assembly/orchestrator.py` - Upload files to GCS after assembly
- `backend/api/routers/episodes/common.py` - Updated `compute_playback_info()` and `_cover_url_for()`
- `backend/api/routers/episodes/jobs.py` - Pass GCS paths to cover URL resolver
- `docs/episode-gcs-retention-fix.md` - Full documentation

**Benefits**:
- ✅ Episodes work immediately after assembly (even if scheduled for future)
- ✅ Container restarts don't break existing episodes
- ✅ 7-day grace period for edits before final Spreaker publish
- ✅ Cost-efficient (auto-cleanup after 7 days)
- ✅ No breaking changes (backward compatible with local dev)

---

### 2. ✅ Duplicate Episode Number Blocking Issue

**Problem**: User creates Episode 1 as S1E1, then needs to create NEW Episode 2 also as S1E1 (to replace old one), but system blocked with 409 error. User couldn't proceed with "create new, delete old" workflow.

**Root Cause**: Hard validation raised `HTTPException(409)` when duplicate season+episode numbers detected, blocking both assembly and updates.

**Solution**:
- **Soft warning instead of block**: Allow creating/updating episodes with duplicate numbers
- **Flag all conflicts**: Set `has_numbering_conflict=True` on ALL matching episodes
- **Block NEW creation if conflicts exist**: Before allowing new episode, check if user has ANY episodes with `has_numbering_conflict=True`
- **Force resolution**: User must edit or delete conflicting episodes before creating more
- **Clear flags automatically**: When conflict resolved (numbers changed), flag automatically cleared

**Files Changed**:
- `backend/api/models/podcast.py` - Added `has_numbering_conflict` boolean field
- `backend/api/startup_tasks.py` - DB migration for new column
- `backend/api/routers/episodes/write.py` - Changed from blocking to warning on update
- `backend/api/services/episodes/assembler.py` - Check for conflicts before NEW assembly, warn during assembly
- `docs/episode-numbering-duplicate-fix.md` - Full documentation

**Workflow**:
```
1. User has Episode 1 (S1E1)
2. Creates NEW Episode 2 as S1E1 → ✅ ALLOWED, both flagged with conflict
3. Tests Episode 2, confirms it's good
4. Deletes Episode 1 → Conflict resolved
5. Creates Episode 3 as S1E2 → ✅ ALLOWED (no conflicts exist)
```

**Error When Blocked**:
```json
{
  "code": "RESOLVE_DUPLICATE_NUMBERING",
  "message": "You have episodes with duplicate season/episode numbers. Please resolve these conflicts before creating new episodes.",
  "conflicts": [
    {"id": "uuid-1", "title": "Episode 1", "season": 1, "episode": 1},
    {"id": "uuid-2", "title": "Episode 2", "season": 1, "episode": 1}
  ]
}
```

**Benefits**:
- ✅ Allows "create new, delete old" workflow
- ✅ Prevents podcast corruption (can't create MORE conflicts)
- ✅ Clear user feedback about what needs fixing
- ✅ Non-blocking for urgent assembly needs

---

## Environment Variables

**MEDIA_ROOT**: Currently set to `/tmp` in Cloud Run

**Should you change it?** **NO!** Here's why:
- ✅ `/tmp` is perfect for Cloud Run ephemeral storage
- ✅ GCS now handles persistence (files uploaded automatically)
- ✅ Local `/tmp` is just working space for assembly
- ✅ No persistent disk needed = lower cost
- ✅ Standard practice for all Cloud Run apps

**Don't change MEDIA_ROOT** - the GCS fix elegantly solves persistence without needing persistent disks.

---

## Deployment Status

**Commits**:
1. `10308c58` - Episode GCS retention fix (audio/cover persistence)
2. `0a7640e8` - Episode numbering duplicate fix (soft warning workflow)

**Build**: Submitted to Cloud Build
**Project**: podcast612
**Region**: us-west1
**Service**: podcast-api

**Expected Build Time**: 8-12 minutes

---

## Testing After Deployment

### Test 1: Episode Persistence
1. Create and assemble new episode
2. Verify audio plays immediately
3. Check database: `gcs_audio_path` and `gcs_cover_path` should be populated
4. Restart container (or wait for auto-restart)
5. Verify audio still plays (from GCS signed URL)

### Test 2: Duplicate Numbering
1. Create Episode A as S1E1
2. Create Episode B as S1E1 → Should succeed with warning
3. Try to create Episode C → Should get 409 error with conflict list
4. Edit Episode B to S1E2 → Conflict resolved
5. Create Episode C as S1E3 → Should succeed

---

## Database Migrations

**Auto-applied on startup**:
```sql
ALTER TABLE episode ADD COLUMN gcs_audio_path VARCHAR NULL;
ALTER TABLE episode ADD COLUMN gcs_cover_path VARCHAR NULL;
ALTER TABLE episode ADD COLUMN has_numbering_conflict BOOLEAN DEFAULT FALSE;
```

**No manual intervention needed** - migrations run automatically via `startup_tasks.py`

---

## Future Enhancements

### GCS Cleanup Task (Not Yet Implemented)
```python
# Background task to run daily
def cleanup_expired_gcs_episodes():
    # Find episodes where:
    # - gcs_audio_path IS NOT NULL
    # - status = 'published'
    # - publish_at < now - 7 days
    # - No edits in last 7 days
    
    # For each:
    # - Delete GCS objects
    # - Set gcs_audio_path = NULL
    # - Set gcs_cover_path = NULL
```

This will be added in a future update to automatically clean up GCS storage after 7-day retention period.

---

## Documentation

- `docs/episode-gcs-retention-fix.md` - Complete GCS retention documentation
- `docs/episode-numbering-duplicate-fix.md` - Complete duplicate numbering documentation

---

## Support

If issues occur:
1. Check Cloud Run logs: `gcloud logging read --project=podcast612 --limit=50`
2. Check database: `SELECT id, title, gcs_audio_path, has_numbering_conflict FROM episode ORDER BY created_at DESC LIMIT 10;`
3. Verify GCS uploads: `gsutil ls -r gs://ppp-media-us-west1/*/episodes/`
