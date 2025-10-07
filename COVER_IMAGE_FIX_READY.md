# COVER IMAGE & AUDIO 404 FIX - READY FOR DEPLOYMENT

**Date**: October 7, 2025  
**Issue**: Episode history page showing missing cover images and audio files
**Status**: ✅ FIXED (NOT YET DEPLOYED per user request)

## Problem

Episodes on the history page were showing broken images due to 404 errors like:
```
GET /static/media/b6d5f77e699e444ba31ae1b4cb15feb4_2fbadd68a98945f4b4727336b0f25ef8_MV5BMmU3YjQ1YzAtMGU4OS00MWJkLTg2NGMtM2NmMmQ3NTM3NjNjXkEyXkFqcGc_._V1_-square.jpg -> 404: Not Found
```

### Root Cause

The cover URL generation logic had several issues:

1. **No validation of local files**: `_cover_url_for()` would return `/static/media/filename.jpg` URLs even if the file didn't exist locally
2. **Swallowed GCS errors**: When GCS URL generation failed, errors were silently caught and fell through to invalid local paths
3. **No final fallback**: When GCS and local files were unavailable, the code didn't fall back to `remote_cover_url` (Spreaker-hosted cover)
4. **Silent failures**: No logging when covers were missing or URL generation failed

### Impact

- Episodes showed broken image icons
- User experience degraded - couldn't see cover art
- Especially affected older episodes where:
  - GCS 7-day retention expired
  - Local files don't exist in production containers
  - Spreaker remote_cover_url was available but not used

## Solution

### Fix 1: Validate Local Files (`_cover_url_for`)

**Before**:
```python
# Priority 3: Local file
return f"/static/media/{os.path.basename(p)}"
```

**After**:
```python
# Priority 3: Local file (only if exists)
try:
    basename = os.path.basename(p)
    local_path = MEDIA_DIR / basename
    if local_path.exists() and local_path.is_file():
        return f"/static/media/{basename}"
except Exception:
    pass

# No valid source found - return None instead of invalid URL
return None
```

**Why this fixes it**: Only returns `/static/media/` URLs for files that actually exist, preventing 404s.

### Fix 2: Better Error Logging (`_cover_url_for`)

**Added**:
```python
except Exception as e:
    from api.core.logging import get_logger
    logger = get_logger("api.episodes.common")
    logger.warning("GCS URL generation failed for %s: %s", gcs_path, e)
    # Fall through to path-based resolution
```

**Why this helps**: Provides visibility into why GCS URLs fail, making debugging easier.

### Fix 3: Always Fall Back to Spreaker (`compute_cover_info`)

**Before**:
```python
if not cover_url and remote_cover_url:
    # Fall back to Spreaker hosted cover
    cover_url = _cover_url_for(remote_cover_url)
    cover_source = "remote"
```

**After**:
```python
# ALWAYS fall back to Spreaker remote_cover_url if nothing else works
if not cover_url and remote_cover_url:
    cover_url = _cover_url_for(remote_cover_url)
    if cover_url:
        cover_source = "remote"
```

**Why this fixes it**: Ensures Spreaker-hosted covers are used when GCS/local unavailable. This is critical for published episodes.

### Fix 4: Log Missing Local Files (`_local_media_url`)

**Added**:
```python
if not candidate.exists():
    logger.warning("Local media file not found for key: %s (path: %s)", key, candidate)
    return None
```

**Why this helps**: Provides visibility into which files are missing from local storage.

## Testing Checklist

When deployed to production:

- [ ] Episode history page loads without broken images
- [ ] Recent episodes (< 7 days published) show GCS covers if available
- [ ] Older episodes (> 7 days published) show Spreaker covers
- [ ] No 404 errors in Cloud Run logs for `/static/media/` requests
- [ ] Logs show which cover source is used: `gcs`, `local`, or `remote`
- [ ] Episodes with missing covers in all sources show no image (not broken icon)

## Deployment Notes

**Files Changed**:
- `backend/api/routers/episodes/common.py` - Core cover URL logic
- `backend/infrastructure/gcs.py` - Local media fallback logging

**Commit**: `[commit hash from git log]`

**Zero-Downtime**: Yes - backward compatible changes only

**Rollback Plan**: 
```bash
git revert [commit hash]
git push origin main
```

## Expected Behavior After Fix

### Scenario 1: Recent Episode (< 7 days)
- GCS URL works → Returns GCS signed URL → Cover loads ✅
- GCS URL fails → Falls back to local → Local exists → `/static/media/` → Cover loads ✅
- GCS URL fails → Falls back to local → Local missing → Falls back to Spreaker → Cover loads ✅

### Scenario 2: Old Episode (> 7 days)
- GCS skipped (outside window) → Local exists → `/static/media/` → Cover loads ✅
- Local missing → Falls back to Spreaker → Cover loads ✅
- No Spreaker URL → Returns None → No image shown (clean failure) ✅

### Scenario 3: Unpublished Episode
- Local exists → `/static/media/` → Cover loads ✅
- Local missing → No Spreaker URL yet → Returns None → No image ✅

## Monitoring

After deployment, check logs for:

**Success Indicators**:
```
[INFO] No private key available; using public URL for GET (bucket is publicly readable)
[INFO] Episode list: cover_source=remote for episode_id=...
```

**Warning Indicators** (expected, not errors):
```
[WARNING] GCS URL generation failed for gs://...: [error]
[WARNING] Local media file not found for key: covers/user_id/file.jpg
[WARNING] No valid cover source for path=..., gcs_path=...
```

**Error Indicators** (investigate):
```
[ERROR] HTTPException GET /static/media/... -> 404
```
If you see 404s after this fix, it means audio files are missing (separate issue).

## Related Issues

This fix also improves the same logic used for:
- Episode audio files (same `_cover_url_for` pattern)
- Admin panel media display
- Public RSS feed images

## Status: ✅ READY FOR DEPLOYMENT

**User requested NOT to deploy yet** - waiting for Episode 193/194 retry testing to complete first.

**Deploy command** (when ready):
```bash
git push origin main
# Cloud Build will auto-deploy
```
