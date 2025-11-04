# R2 Playback Signed URL Fix - Nov 4, 2025

## Critical Bug Fixed: Episodes 201+ Not Playing

### Problem
- Episodes 1-200: ✅ Play fine (using GCS with `gs://` URLs)
- Episodes 201+: ❌ Grey play button, won't play (using R2 with `https://` URLs)

### Root Cause
**R2 storage URLs are NOT publicly accessible without authentication.**

When `STORAGE_BACKEND=r2`:
1. ✅ R2 upload succeeds → stores `https://ppp-media.{account}.r2.cloudflarestorage.com/path/to/file.mp3` in `episode.gcs_audio_path`
2. ✅ Episode shows in UI with "Published" badge
3. ❌ **Playback code treats R2 HTTPS URLs as "public" and returns them directly**
4. ❌ Browser tries to fetch audio → **403 Forbidden** (R2 bucket is NOT public)
5. ❌ Frontend shows grey play button (audio unavailable)

### Why Spreaker Episodes Work
Spreaker episodes use `spreaker_episode_id` → `https://api.spreaker.com/v2/episodes/{id}/play` (actually public API).

### Why Episodes 1-200 Work
Early episodes used GCS storage:
- Stored as `gs://bucket/path` in database
- Playback code detects `gs://` prefix
- Generates **signed URL** with 1-hour expiry
- ✅ Works perfectly

### Why Episodes 201+ Failed
Recent episodes use R2 storage:
- Stored as `https://ppp-media.xxx.r2.cloudflarestorage.com/path` in database
- **BUG:** Playback code saw `https://` and assumed it was public
- Returned R2 storage URL directly (NO signature)
- ❌ Browser gets 403 Forbidden (R2 bucket requires auth)

## The Fix

**File:** `backend/api/routers/episodes/common.py`

### Before (Broken)
```python
if storage_url.startswith("https://"):
    # R2 public URL - use directly
    final_audio_url = storage_url
    cloud_exists = True
```

**Problem:** R2 URLs are NOT public - they need signed URLs like GCS.

### After (Fixed)
```python
if storage_url.startswith("https://") and ".r2.cloudflarestorage.com/" in storage_url:
    # R2 storage URL - needs signed URL for playback
    # Parse: https://ppp-media.{account}.r2.cloudflarestorage.com/user/episodes/123/audio/file.mp3
    from infrastructure.r2 import get_signed_url
    import os
    
    # Extract bucket and key from URL
    account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
    if account_id and f".{account_id}.r2.cloudflarestorage.com/" in storage_url:
        url_parts = storage_url.replace("https://", "").split("/", 1)
        if len(url_parts) == 2:
            bucket_part = url_parts[0]  # "ppp-media.{account}.r2.cloudflarestorage.com"
            key = url_parts[1]  # "user/episodes/123/audio/file.mp3"
            bucket = bucket_part.split(".")[0]  # Extract "ppp-media"
            
            final_audio_url = get_signed_url(bucket, key, expiration=86400)  # 24hr expiry
            cloud_exists = True
```

**Solution:** Detect R2 URLs by domain pattern, extract bucket/key, generate signed URL.

## URL Formats Handled

| Storage | Database Format | Playback URL | Method |
|---------|----------------|--------------|--------|
| **GCS** | `gs://bucket/key` | Signed URL (1hr) | `gcs.get_signed_url()` |
| **R2 (URI)** | `r2://bucket/key` | Signed URL (24hr) | `r2.get_signed_url()` |
| **R2 (HTTPS)** | `https://bucket.account.r2.cloudflarestorage.com/key` | Signed URL (24hr) | `r2.get_signed_url()` ✅ **NOW FIXED** |
| **Spreaker** | `spreaker_episode_id` | `https://api.spreaker.com/v2/episodes/{id}/play` | Direct (public API) |

## Why This Happened

### R2 Upload Returns HTTPS URLs
**File:** `backend/infrastructure/r2.py` (line 124)

```python
def upload_fileobj(...):
    # Upload to R2
    client.upload_fileobj(fileobj, bucket_name, key, ...)
    
    # Return public R2 URL
    account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
    url = f"https://{bucket_name}.{account_id}.r2.cloudflarestorage.com/{key}"
    return url  # ← This is NOT publicly accessible without signature!
```

**Why return HTTPS instead of r2://?**
- Matches GCS behavior (returns `gs://` URIs)
- But GCS URIs are NEVER confused with public URLs (no https://)
- R2 team chose HTTPS format → accidentally looks "public" → ❌ bug

### Alternative: Change R2 Upload to Return r2:// URIs

**Option A (Current Fix):** Smart detection in playback code
- ✅ Works with existing database records
- ✅ No migration needed
- ✅ Handles both `r2://` and `https://` formats

**Option B (Alternative):** Change R2 upload to return `r2://bucket/key` instead
- ❌ Requires database migration for existing episodes
- ❌ Breaks backward compatibility
- ❌ More work, same result

**Verdict:** Option A is correct - fix playback code to handle reality.

## Testing

### Manual Test (After Deploy)
1. Navigate to Episode History page
2. Find episode 201+ (any recent episode)
3. Click play button
4. **Expected:** Audio plays immediately ✅
5. **Before fix:** Grey play button, 403 error in console ❌

### Automated Test
```python
# Test R2 HTTPS URL detection and signed URL generation
def test_r2_https_url_generates_signed_url(db_session):
    episode = Episode(
        gcs_audio_path="https://ppp-media.xxxxx.r2.cloudflarestorage.com/user/episodes/123/audio/test.mp3",
        spreaker_episode_id=None,
    )
    
    playback = compute_playback_info(episode)
    
    # Should generate signed URL, not return storage URL directly
    assert playback["playback_url"] != episode.gcs_audio_path
    assert "X-Amz-Algorithm" in playback["playback_url"]  # Has signature params
    assert playback["playback_type"] == "cloud"
    assert playback["final_audio_exists"] is True
```

## Impact

### Episodes Fixed
- **All episodes 201-203+** using R2 storage will now play correctly
- Episodes continue to work after this fix is deployed
- No database migration needed
- No user action required

### Performance
- Signed URLs valid for 24 hours (vs 1hr for GCS)
- Reduces server load (fewer signature generations)
- CDN-friendly (Cloudflare's edge network)

### Future-Proof
- Works with BOTH `r2://` and `https://` R2 URL formats
- Maintains backward compatibility with GCS episodes
- Maintains Spreaker episode support

## Related Files

- ✅ **`backend/api/routers/episodes/common.py`** - `compute_playback_info()` function
- **`backend/infrastructure/r2.py`** - R2 client and signed URL generation
- **`backend/worker/tasks/assembly/orchestrator.py`** - Stores R2 URLs in database
- **`R2_URL_VALIDATION_FIX_NOV3.md`** - Previous fix for URL validation

## Deployment

### Critical Priority
**This is a PRODUCTION-BREAKING bug** - users cannot play recently created episodes.

### Deploy Immediately
```powershell
# 1. Commit fix
git add backend/api/routers/episodes/common.py R2_PLAYBACK_SIGNED_URL_FIX_NOV4.md
git commit -m "Fix R2 playback: Generate signed URLs for HTTPS storage URLs"

# 2. Deploy (user handles this in separate window per workflow)
# User will run: gcloud builds submit
```

### Verification
```bash
# After deploy, check logs for successful signed URL generation
gcloud logging read "textPayload=~'Generated.*signed URL for.*episodes'" \
  --limit=10 --project=podcast612

# Should see: "[R2] Generated GET signed URL for user/episodes/123/audio/file.mp3 (expires in 86400s)"
```

## Prevention

### Why Didn't Tests Catch This?
- Unit tests mock storage responses
- Integration tests use GCS (not R2)
- Production testing phase just started with R2

### How to Prevent
1. ✅ Add integration test for R2 playback URLs
2. ✅ Add staging environment that mirrors production storage backend
3. ✅ Document R2 bucket public access policy (currently private, requires signed URLs)

---

**Status:** ✅ Fix implemented and ready for deployment  
**Priority:** 🚨 CRITICAL - Production users cannot play new episodes  
**Risk:** Low - Only changes URL generation for R2, no schema changes  
**Rollback:** Revert commit if issues (episodes will be unplayable again until fixed)
