# GCS-ONLY ENFORCEMENT - ONBOARDING & MEDIA LIBRARY FIX (Oct 13, 2025)

## Problem Description

User reported **"Could not determine preview URL"** error in the onboarding flow when trying to preview AI-generated intro/outro audio (Step 6).

### Root Cause
The system had **silent fallback logic** that allowed intro/outro/music files to be stored in local filesystem when GCS upload failed. This created a split-brain situation:
- **Local dev**: Files work (local filesystem available)
- **Production**: Files break after container restart (ephemeral filesystem)

### User Impact
- Onboarding flow broken (can't preview intro/outro)
- Manual uploads of intro/outro/music broken
- TTS-generated intro/outro unusable
- Admin music uploads might fail silently

## Solution: Fail-Fast GCS Enforcement

Removed ALL fallbacks for categories that require persistent storage. If GCS upload fails, **the entire request fails** with a clear error message.

### Changes Made

#### 1. TTS Endpoint (media_tts.py)
**File**: `backend/api/routers/media_tts.py`

**Changed behavior** (lines 153-181):
```python
# BEFORE: Silent fallback to local file
if gcs_url:
    final_filename = gcs_url
    log.info(f"[tts] Uploaded {body.category.value} to GCS: {gcs_url}")
except Exception as e:
    log.warning(f"[tts] Failed to upload to GCS: {e}")
    # Fallback to local filename - non-fatal in dev

# AFTER: Fail-fast enforcement
if gcs_url and gcs_url.startswith("gs://"):
    final_filename = gcs_url
    log.info(f"[tts] SUCCESS: Uploaded {body.category.value} to GCS: {gcs_url}")
else:
    log.error(f"[tts] GCS upload returned non-GCS URL: {gcs_url}")
    raise HTTPException(
        status_code=500,
        detail=f"GCS upload failed - {body.category} files must be in GCS for production use"
    )
```

**Impact**:
- TTS intro/outro/music generation now **fails immediately** if GCS upload fails
- User gets clear error message: "GCS upload failed - intro files must be in GCS for production use"
- No more orphaned local files that work in dev but break in production

#### 2. Media Upload Endpoint (media_write.py)
**File**: `backend/api/routers/media_write.py`

**Changed behavior** (lines 134-181):
```python
# BEFORE: Silent fallback with warning
try:
    gcs_url = gcs.upload_fileobj(...)
    if gcs_url and gcs_url.startswith("gs://"):
        safe_filename = gcs_url
except Exception as e:
    log.warning("[upload.gcs] Failed to upload: %s", e)
    # Continue with local-only storage (will work until container restart)

# AFTER: Fail-fast enforcement
try:
    log.info("[upload.gcs] Uploading %s to gs://%s/%s", category.value, gcs_bucket, gcs_key)
    gcs_url = gcs.upload_fileobj(...)
    if gcs_url and gcs_url.startswith("gs://"):
        safe_filename = gcs_url
        log.info("[upload.gcs] SUCCESS: %s uploaded: %s", category.value, gcs_url)
    else:
        log.error("[upload.gcs] Upload returned non-GCS URL: %s", gcs_url)
        # Clean up local file
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload {category.value} to cloud storage - this is required for production use"
        )
except HTTPException:
    raise
except Exception as e:
    log.error("[upload.gcs] CRITICAL: Failed to upload: %s", e, exc_info=True)
    # Clean up local file
    if file_path.exists():
        file_path.unlink()
    raise HTTPException(
        status_code=500,
        detail=f"Failed to upload {category.value} to cloud storage: {str(e)}"
    )
```

**Impact**:
- Manual uploads of intro/outro/music/sfx/commercial now **fail immediately** if GCS upload fails
- User gets clear error: "Failed to upload intro to cloud storage - this is required for production use"
- Local file is cleaned up on failure (no orphaned files)

#### 3. Admin Music Upload (Already Correct)
**File**: `backend/api/routers/admin/music.py`

Admin music upload endpoint (lines 187-280) was already uploading to GCS correctly. No changes needed.

#### 4. Music Listing Endpoint (Already Correct)
**File**: `backend/api/routers/music.py`

Music asset listing (lines 40-100) already handled GCS URLs correctly by generating signed URLs for playback. No changes needed.

#### 5. Preview Endpoint (Already Correct)
**File**: `backend/api/routers/media.py`

The `/api/media/preview` endpoint (lines 377-470) was already correctly handling GCS URLs:
1. Loads MediaItem by ID
2. Checks if `filename` starts with `gs://`
3. Generates signed URL for playback
4. Returns `{"url": "https://signed-url..."}`

No changes needed.

## Categories Affected

**Enforced GCS-only** (fail-fast if GCS upload fails):
- `intro` - Podcast intros
- `outro` - Podcast outros
- `music` - Background music
- `sfx` - Sound effects
- `commercial` - Commercial/ad reads

**Still allow local fallback** (for now):
- `main_content` - Episode audio (too large, needs separate migration)
- `cover` - Cover images (need to verify GCS support)

## Testing Plan

### Local Dev Testing
1. **Verify GCS credentials are configured**:
   ```bash
   # Check ADC (Application Default Credentials)
   gcloud auth application-default login
   
   # Or set GOOGLE_APPLICATION_CREDENTIALS env var
   echo $GOOGLE_APPLICATION_CREDENTIALS
   ```

2. **Test TTS generation**:
   - Go to onboarding Step 6
   - Click "Generate with AI" for intro
   - Should succeed and show preview button
   - Click preview button - should hear audio
   
3. **Test manual upload**:
   - Go to Media Library
   - Upload an audio file as category "intro"
   - Should succeed and file should preview

4. **Test failure case** (optional):
   - Temporarily remove GCS credentials
   - Try TTS generation
   - Should get error: "GCS upload failed - intro files must be in GCS for production use"
   - This is CORRECT behavior (fail-fast)

### Production Testing
1. **Deploy changes**:
   ```bash
   gcloud builds submit --config=cloudbuild.yaml --region=us-west1
   ```

2. **Verify environment**:
   - Check Cloud Run logs for startup
   - Verify `GCS_BUCKET` env var is set
   - Verify service account has GCS write permissions

3. **Test onboarding**:
   - Create new test account
   - Go through onboarding flow
   - Generate AI intro/outro in Step 6
   - Verify preview works
   - Complete onboarding
   - Verify template saved with GCS URLs

4. **Test existing users**:
   - Load Media Library
   - Verify existing intro/outro files show preview buttons
   - Upload new intro file
   - Verify it appears and previews correctly

## Error Messages

Users will see these errors if GCS fails:

### TTS Generation Failure
```
Error: GCS upload failed - intro files must be in GCS for production use

This means:
- Cloud storage is temporarily unavailable
- Retry in a few minutes
- Contact support if issue persists
```

### Manual Upload Failure
```
Error: Failed to upload intro to cloud storage - this is required for production use

This means:
- Cloud storage is temporarily unavailable
- Retry the upload
- Contact support if issue persists
```

## Rollback Plan

If this breaks production:

1. **Quick fix**: Revert both files to allow fallbacks again
   ```bash
   git revert <commit-hash>
   gcloud builds submit --config=cloudbuild.yaml
   ```

2. **Investigate**: Check Cloud Run logs for GCS errors:
   ```bash
   gcloud logging read "resource.type=cloud_run_revision AND labels.service_name=api AND severity>=ERROR" --limit=50
   ```

3. **Common issues**:
   - Service account lacks `storage.objects.create` permission
   - `GCS_BUCKET` env var not set or wrong value
   - Network issues between Cloud Run and GCS

## Verification Checklist

- [x] TTS endpoint fails fast on GCS upload failure
- [x] Media upload endpoint fails fast on GCS upload failure
- [x] Admin music upload uses GCS (already correct)
- [x] Preview endpoint handles GCS URLs (already correct)
- [x] Error messages are clear and actionable
- [x] Local files cleaned up on failure
- [ ] Local dev tested with valid GCS credentials
- [ ] Production deployed and verified
- [ ] Onboarding flow tested end-to-end
- [ ] Existing user media library tested

## Next Steps

1. **Deploy to production** (HIGH PRIORITY)
2. **Test onboarding flow** with new account
3. **Monitor error rates** in Cloud Run logs
4. **Consider migrating main_content** to GCS-only (future work)
5. **Update user documentation** to explain cloud storage requirement

## Related Issues

- Manual Editor audio loading (FIXED - Oct 13)
- Episode 204 audio missing (diagnosed - no GCS path)
- Scheduled episodes editing (FIXED - removed 7-day restriction)
- GCS-only architecture (IMPLEMENTED - Oct 13)

---

**Last Updated**: 2025-10-13  
**Author**: GitHub Copilot  
**Status**: Ready for Production Deployment  
**Priority**: CRITICAL (blocks onboarding flow)
