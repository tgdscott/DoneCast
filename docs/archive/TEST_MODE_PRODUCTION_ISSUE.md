# TEST MODE ENABLED IN PRODUCTION - CRITICAL ISSUE

## Problem
All episode filenames in production are prefixed with "test":
- `test110803---e200---the-long-walk---what-would-you-do.mp3`
- `test110608---e199---twinless---what-would-you-do.mp3`
- `test110346---e195----e195---the-roses---what-would-you-do.mp3`

## Root Cause
**Line 547 in `backend/api/services/episodes/assembler.py`:**
```python
try:
    admin_rec = session.get(AppSetting, 'admin_settings')
    import json as _json
    adm = _json.loads(admin_rec.value_json or '{}') if admin_rec else {}
    test_mode = bool(adm.get('test_mode'))  # ← Reading from database
except Exception:
    test_mode = False
```

**Lines 575 in `assembler.py`:**
```python
if test_mode:
    # ... code to generate test filename ...
    output_filename = f"test{sn_input}{en_input}---{slug}"  # ← Adds "test" prefix
```

## Database State
The `appsetting` table in production database has a record:
- **key**: `admin_settings`
- **value_json**: `{"test_mode": true}` ← **THIS IS THE PROBLEM**

## Impact
1. ❌ All episode filenames get "test" prefix
2. ❌ Files can't be played (wrong paths)
3. ❌ RSS feeds have wrong file URLs
4. ❌ Downloaded episodes have unprofessional filenames
5. ❌ SEO impact (test in production URLs)

## Solutions

### Option 1: SQL Update (FASTEST - DO THIS NOW)
```sql
-- Connect to production database
UPDATE appsetting 
SET value_json = '{"test_mode": false}' 
WHERE key = 'admin_settings';

-- Verify
SELECT key, value_json FROM appsetting WHERE key = 'admin_settings';
```

### Option 2: Cloud Run SQL Query
```bash
gcloud sql connect podcast-prod --user=podcast --database=podcast --project=podcast612
# Then run the UPDATE query above
```

### Option 3: Create Admin API Endpoint (For Future)
Add endpoint to toggle test_mode without SQL access:
```python
@router.post("/admin/toggle-test-mode")
def toggle_test_mode(
    enabled: bool,
    current_user: User = Depends(require_admin)
):
    admin_rec = session.get(AppSetting, 'admin_settings') or AppSetting(key='admin_settings')
    settings = json.loads(admin_rec.value_json or '{}')
    settings['test_mode'] = enabled
    admin_rec.value_json = json.dumps(settings)
    session.add(admin_rec)
    session.commit()
    return {"test_mode": enabled}
```

## Why This Happened
Likely scenarios:
1. Test mode was enabled for testing
2. Never got disabled before going to production
3. Database migrated from dev → production with test_mode=true
4. Someone enabled it accidentally via SQL or admin interface

## Immediate Action Required
**DISABLE TEST MODE IN PRODUCTION DATABASE NOW!**

After disabling:
1. Create new episode to verify "test" prefix is gone
2. Check filename format is correct
3. Verify files are playable
4. Consider renaming existing "test" files (breaking change - requires RSS feed update)

## Prevention
1. Add environment check:
   ```python
   if test_mode and os.getenv("ENV") == "production":
       logger.warning("test_mode enabled in production - ignoring!")
       test_mode = False
   ```

2. Add admin UI toggle with warning:
   - "⚠️ WARNING: Test mode prefixes all filenames with 'test'. Only use in development!"

3. Default test_mode to False in production deployments

## Files Affected
All episodes created since test_mode was enabled have the "test" prefix in:
- `Episode.final_audio_path` in database
- Files in GCS bucket: `gs://ppp-media-us-west1/.../final/test*.mp3`
- RSS feed URLs
- Playback URLs

To fix existing episodes, you'll need to:
1. Rename files in GCS (remove "test" prefix)
2. Update Episode.final_audio_path in database
3. Regenerate RSS feed

**Or**: Leave existing episodes as-is and just fix future ones after disabling test_mode.
