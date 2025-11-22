# Episode Database Issues - Diagnosis & Fix

## Issues Found

### 1. Published Status Issue (Episodes >200)

**Problem**: 20 episodes have `spreaker_episode_id` but `status != 'published'`. 5 of them have `publish_at` in the past but still show as `processed`.

**Root Cause**: Episodes were published to Spreaker but the database `status` field was never updated to `published`. The `is_published_to_spreaker` flag is also `False` for most, suggesting the publish workflow didn't complete properly.

**Affected Episodes**: 20 episodes (IDs listed in diagnosis output)

**Fix**: Run `fix_episode_status_and_covers.py --fix-status` to update status for episodes that should be published.

### 2. Cover Upload 422 Error

**Problem**: Cover image uploads from Episode History editor are failing with 422 Unprocessable Entity.

**Root Cause**: The backend endpoint `/api/media/upload/cover_art` is rejecting the request. Possible causes:
- FormData field name mismatch
- File validation failing
- Content-Type header issues

**Fix**: 
1. Frontend now tries both endpoints (`/api/media/upload/episode_cover` then `/api/media/upload/cover_art`)
2. Improved error message extraction to show actual backend error
3. Backend already handles `cover_image_path` correctly in PATCH endpoint

## Diagnosis Results

### Episodes Under 200
- ✅ All 200 episodes have `status == 'published'`
- ✅ All have covers (cover_path, gcs_cover_path, remote_cover_url)
- ✅ All have `publish_at` and `spreaker_episode_id`

### Episodes Over 200 (33 total)
- ⚠️ Only 12 have `status == 'published'`
- ⚠️ 20 have `spreaker_episode_id` but `status != 'published'`
- ⚠️ 5 have `publish_at` in past but `status != 'published'`
- ✅ All have covers

## Fix Commands

```bash
# Diagnose issues
python backend/diagnose_episode_issues.py

# Fix published status (dry run first)
python backend/fix_episode_status_and_covers.py --fix-status --dry-run

# Apply fixes
python backend/fix_episode_status_and_covers.py --fix-status

# Fix cover path inconsistencies (if any)
python backend/fix_episode_status_and_covers.py --fix-covers

# Fix everything
python backend/fix_episode_status_and_covers.py --fix-all
```

## Next Steps

1. Run the fix script to update episode statuses
2. Test cover upload again - check browser console for detailed error message
3. If 422 persists, check backend logs for validation error details





