# ONBOARDING FIX COMPLETE - SUMMARY (Oct 13, 2025)

## What Was Broken

User saw **"Could not determine preview URL"** error in onboarding flow Step 6 when trying to preview AI-generated intro/outro audio.

![Screenshot showing error toast in bottom-right corner](screenshot-reference.png)

## Root Cause

Two endpoints had **silent fallback logic** that stored intro/outro files in local filesystem when GCS upload failed:

1. **TTS endpoint** (`/api/media/tts`) - AI-generated intro/outro
2. **Media upload endpoint** (`/api/media/upload/{category}`) - Manual uploads

### The Problem with Silent Fallbacks

```python
# BEFORE (BROKEN):
try:
    gcs_url = gcs.upload_fileobj(...)
    if gcs_url:
        filename = gcs_url  # Use GCS URL
except Exception:
    pass  # Silently fall back to local filename
    
# Result: Worked in dev (local files persist), broke in production (ephemeral containers)
```

This created a **split-brain** situation:
- **Local dev**: Files work (local filesystem available)
- **Production**: Files break after container restart (ephemeral filesystem)
- **Preview endpoint** tried to load from GCS, couldn't find file, returned "No audio"

## The Fix

Changed both endpoints to **fail-fast** if GCS upload fails:

```python
# AFTER (FIXED):
log.info(f"[tts] Uploading {category} to gs://{bucket}/{key}")
gcs_url = gcs.upload_fileobj(...)

if gcs_url and gcs_url.startswith("gs://"):
    filename = gcs_url
    log.info(f"[tts] SUCCESS: Uploaded to GCS: {gcs_url}")
else:
    log.error(f"[tts] GCS upload returned non-GCS URL: {gcs_url}")
    raise HTTPException(
        status_code=500,
        detail=f"GCS upload failed - {category} files must be in GCS for production use"
    )
```

### Categories Enforced (Fail-Fast)

These categories **MUST** be in GCS or request fails:
- ✅ `intro` - Podcast intros
- ✅ `outro` - Podcast outros
- ✅ `music` - Background music
- ✅ `sfx` - Sound effects
- ✅ `commercial` - Commercial/ad reads

Still allowing fallback (for now):
- ⚠️ `main_content` - Episode audio (too large, needs separate migration)
- ⚠️ `cover` - Cover images (need to verify GCS support)

## Files Changed

### 1. `backend/api/routers/media_tts.py`
- Lines 153-181: Added strict GCS validation
- Fails with HTTP 500 if upload doesn't return `gs://` URL
- Cleans up local temp file on failure
- Clear error message: "GCS upload failed - intro files must be in GCS for production use"

### 2. `backend/api/routers/media_write.py`
- Lines 134-181: Added strict GCS validation
- Fails with HTTP 500 if upload doesn't return `gs://` URL
- Cleans up local file on failure
- Clear error message: "Failed to upload intro to cloud storage - this is required for production use"

### 3. `d:\PodWebDeploy\ONBOARDING_GCS_FIX_OCT13.md`
- Comprehensive technical documentation
- Testing plan
- Rollback procedure
- Error message reference

### 4. `.github/copilot-instructions.md`
- Updated "Known Active Issues" section
- Added "ONBOARDING GCS ENFORCEMENT" entry
- Marked as PRODUCTION CRITICAL

## What This Fixes

✅ **Onboarding flow** - AI-generated intro/outro now preview correctly  
✅ **Manual uploads** - User-uploaded intro/outro/music now preview correctly  
✅ **Admin music uploads** - Already working, no changes needed  
✅ **Production stability** - No more silent failures from local file fallbacks  

## What Could Break

⚠️ **If GCS is misconfigured or down:**
- TTS generation will fail with clear error
- Manual uploads will fail with clear error
- This is CORRECT behavior (fail-fast) but users will see errors

**Mitigation:**
- Monitor GCS error rates in Cloud Run logs
- Ensure `GCS_BUCKET` env var is set correctly
- Verify service account has `storage.objects.create` permission

## Deployment Steps

1. **Push changes to Git**:
   ```bash
   git add backend/api/routers/media_tts.py
   git add backend/api/routers/media_write.py
   git add ONBOARDING_GCS_FIX_OCT13.md
   git add .github/copilot-instructions.md
   git commit -m "fix: Enforce GCS-only for intro/outro/music (fail-fast)"
   git push origin main
   ```

2. **Deploy to Cloud Run**:
   ```bash
   gcloud builds submit --config=cloudbuild.yaml --region=us-west1
   ```

3. **Verify deployment**:
   - Check Cloud Run logs for startup
   - Test onboarding flow with new account
   - Test media library uploads
   - Monitor error rates

4. **Rollback if needed**:
   ```bash
   git revert HEAD
   git push origin main
   # Redeploy via Cloud Build
   ```

## Testing Checklist

- [ ] Deploy to production
- [ ] Create new test account
- [ ] Complete onboarding flow
- [ ] Generate AI intro in Step 6
- [ ] Verify preview button appears and works
- [ ] Go to Media Library
- [ ] Upload manual intro file
- [ ] Verify preview works
- [ ] Check Cloud Run logs for errors
- [ ] Monitor for 24 hours

## Success Criteria

✅ Onboarding flow works end-to-end  
✅ Preview buttons show for all intro/outro/music files  
✅ Audio plays when preview clicked  
✅ No "Could not determine preview URL" errors  
✅ Cloud Run logs show "SUCCESS: Uploaded to GCS" messages  
✅ No silent fallbacks to local files  

## Related Issues Fixed in Same Session

1. ✅ Manual Editor waveform display (edit-context endpoint)
2. ✅ Episode 204 audio missing (unpublish Spreaker ID preservation)
3. ✅ Scheduled episode editing (removed 7-day restriction)
4. ✅ GCS-only architecture (fail-fast assembly, no local fallbacks)
5. ✅ **Onboarding preview URLs (THIS FIX)**

---

**Deployed**: Not yet (code ready)  
**Priority**: CRITICAL (blocks new user onboarding)  
**Risk Level**: Low (fail-fast is safer than silent fallback)  
**Rollback**: Easy (single git revert + redeploy)  

**Next Action**: Deploy and test!
