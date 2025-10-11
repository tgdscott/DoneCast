# 🚨 ONBOARDING MEDIA UPLOAD FIX - DEPLOYMENT PLAN

**Status**: FIX READY  
**Date**: October 11, 2025  
**Revision Target**: 00531  
**Priority**: CRITICAL - Users cannot complete onboarding

---

## Root Cause Identified ✅

### Problem 1: Podcast Cover Upload (Step 5) - LOCAL DISK STORAGE ❌

**File**: `backend/api/services/podcasts/utils.py` lines 24-82  
**Function**: `save_cover_upload()`

**Current Behavior**:
```python
# BROKEN: Saves to local disk only
def save_cover_upload(...):
    save_path = upload_dir / unique_filename  # Local /tmp
    with save_path.open("wb") as buffer:
        # Write to local disk
        buffer.write(chunk)
    return unique_filename, save_path  # Returns local path
```

**Issues**:
1. ❌ Saves to `/tmp` (ephemeral storage in Cloud Run)
2. ❌ File lost when container restarts
3. ❌ No GCS upload
4. ❌ Podcast cover 404s immediately or after deployment

---

### Problem 2: Intro/Outro Upload (Step 6) - PARTIAL GCS SUPPORT ⚠️

**File**: `backend/api/routers/media.py` lines 220-252  
**Function**: `upload_media_files()`

**Current Behavior**:
```python
# PARTIALLY WORKING: Has GCS upload but flawed
if gcs_bucket and category in (
    MediaCategory.intro,
    MediaCategory.outro,
    MediaCategory.music,
    MediaCategory.sfx,
    MediaCategory.commercial,
):
    try:
        gcs_url = gcs.upload_fileobj(gcs_bucket, gcs_key, f, content_type)
        if gcs_url and gcs_url.startswith("gs://"):
            final_filename = gcs_url  # ✅ Stores GCS URL
    except Exception as e:
        print(f"Warning: Failed to upload to GCS: {e}")  # ⚠️ Silent failure
```

**Issues**:
1. ✅ Has GCS upload logic for intro/outro
2. ⚠️ Silent failure if GCS upload fails
3. ⚠️ Falls back to local /tmp storage
4. ❓ GCS upload might be failing due to IAM/permissions

---

## Fix Strategy

### Fix 1: Update `save_cover_upload()` to Use GCS

**Apply same pattern as intern/flubber snippets**:

```python
def save_cover_upload(
    cover_image: UploadFile,
    user_id: UUID,
    *,
    upload_dir: Path,
    max_bytes: int = 10 * MB,
    allowed_extensions: Optional[Iterable[str]] = None,
    require_image_content_type: bool = False,
) -> Tuple[str, Path]:
    """Persist cover image to GCS with temporary local staging."""
    
    # ... validation (keep existing) ...
    
    # Stage to /tmp temporarily
    temp_path = upload_dir / unique_filename
    total = 0
    with temp_path.open("wb") as buffer:
        while True:
            chunk = cover_image.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if max_bytes and total > max_bytes:
                temp_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Cover exceeds 10 MB limit.")
            buffer.write(chunk)
    
    # Upload to GCS immediately
    gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
    gcs_key = f"{user_id.hex}/covers/{unique_filename}"
    
    try:
        from infrastructure import gcs
        with open(temp_path, "rb") as f:
            gcs_url = gcs.upload_fileobj(gcs_bucket, gcs_key, f, 
                                         content_type=cover_image.content_type or "image/jpeg")
        
        # Clean up temp file
        temp_path.unlink(missing_ok=True)
        
        # Return GCS URL as filename
        return gcs_url, temp_path  # temp_path only for backward compat
        
    except Exception as e:
        # Clean up and fail
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, 
                          detail=f"Failed to upload cover to GCS: {e}")
```

### Fix 2: Make Media Upload GCS Failures More Visible

**Add logging and ensure GCS upload succeeds**:

```python
# In upload_media_files(), around line 240:
if gcs_bucket and category in (...):
    try:
        from infrastructure import gcs
        gcs_key = f"{current_user.id.hex}/media/{category.value}/{safe_filename}"
        with open(file_path, "rb") as f:
            gcs_url = gcs.upload_fileobj(gcs_bucket, gcs_key, f, content_type=final_content_type or "audio/mpeg")
        
        if gcs_url and gcs_url.startswith("gs://"):
            final_filename = gcs_url
            print(f"[media.upload] ✅ Uploaded {category.value} to GCS: {gcs_url}")
        else:
            # GCS upload returned invalid URL
            raise Exception(f"GCS upload returned invalid URL: {gcs_url}")
            
    except Exception as e:
        # FAIL THE UPLOAD - don't silently fall back to /tmp
        print(f"[media.upload] ❌ FAILED to upload {category.value} to GCS: {e}")
        try:
            file_path.unlink(missing_ok=True)
        except:
            pass
        raise HTTPException(status_code=500, 
                          detail=f"Failed to upload {category.value} to cloud storage: {e}")
```

### Fix 3: Update Podcast Model to Use GCS URL

**Ensure `Podcast.cover_path` stores GCS URL**:

In `backend/api/routers/podcasts/crud.py` around line 119:

```python
if cover_image and cover_image.filename:
    log.info("Cover image provided: '%s'. Processing file.", cover_image.filename)
    try:
        stored_filename, save_path = save_cover_upload(
            cover_image,
            current_user.id,
            upload_dir=UPLOAD_DIRECTORY,
            allowed_extensions={".png", ".jpg", ".jpeg"},
            require_image_content_type=True,
        )
        # stored_filename is now a GCS URL (gs://bucket/path)
        db_podcast.cover_path = stored_filename
        log.info("✅ Cover uploaded to GCS: %s", stored_filename)
```

---

## Testing Plan

### 1. Test Cover Upload Endpoint

```bash
# Create test image
echo "Test" > test_cover.jpg

# Test podcast creation with cover
curl -X POST https://podcast-api-kge7snpz7a-uw.a.run.app/api/podcasts/ \
  -H "Authorization: Bearer $TOKEN" \
  -F "name=Test Onboarding Podcast" \
  -F "description=Testing cover upload" \
  -F "cover_image=@test_cover.jpg"

# Expected response:
# {
#   "id": "...",
#   "name": "Test Onboarding Podcast",
#   "cover_path": "gs://ppp-media-us-west1/{user_id}/covers/{uuid}.jpg",
#   ...
# }
```

### 2. Test Intro Upload

```bash
# Create test audio (1 second silence)
ffmpeg -f lavfi -i anullsrc=r=44100:cl=mono -t 1 -q:a 9 -acodec libmp3lame test_intro.mp3

# Test intro upload
curl -X POST https://podcast-api-kge7snpz7a-uw.a.run.app/api/media/upload/intro \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@test_intro.mp3"

# Expected response:
# [
#   {
#     "id": "...",
#     "filename": "gs://ppp-media-us-west1/{user_id}/media/intro/{uuid}_{name}.mp3",
#     "category": "intro",
#     ...
#   }
# ]
```

### 3. Test Full Onboarding Flow

1. Create new account
2. Start onboarding wizard
3. Complete all steps including:
   - Upload cover art (step 5)
   - Upload intro audio (step 6)
   - Skip or select music (step 7)
4. Complete onboarding
5. Verify podcast created successfully
6. Check database for GCS URLs:
   ```sql
   SELECT id, name, cover_path FROM podcasts WHERE user_id = '...';
   SELECT id, filename, category FROM media_items WHERE user_id = '...' AND category IN ('intro', 'outro');
   ```

---

## Deployment Commands

```powershell
# 1. Stage changes
git add backend/api/services/podcasts/utils.py
git add backend/api/routers/podcasts/crud.py
git add backend/api/routers/media.py

# 2. Commit with clear message
git commit -m "fix: Onboarding media uploads - migrate cover art to GCS storage

- Update save_cover_upload() to upload covers to GCS immediately
- Store GCS URLs in Podcast.cover_path instead of local paths
- Make intro/outro upload failures explicit (no silent fallback to /tmp)
- Add logging for GCS upload success/failure
- Fixes steps 5-6 of onboarding wizard

Closes: Onboarding steps 5-7 broken due to /tmp ephemeral storage
Related: Revisions 00528 (intern GCS), 00529 (flubber GCS), 00530 (auth fixes)"

# 3. Deploy to Cloud Run
gcloud run deploy podcast-api `
  --region us-west1 `
  --source . `
  --allow-unauthenticated

# 4. Wait for deployment
# Expected: Revision 00531

# 5. Test onboarding flow immediately
```

---

## Files to Modify

### 1. `backend/api/services/podcasts/utils.py`

**Lines to replace**: 24-82 (entire `save_cover_upload` function)

**Changes**:
- Add GCS upload after temp file staging
- Store GCS URL as filename
- Delete temp file after GCS upload
- Fail loudly if GCS upload fails

### 2. `backend/api/routers/media.py`

**Lines to modify**: 220-252 (GCS upload section in `upload_media_files`)

**Changes**:
- Add success logging
- Fail upload if GCS fails (don't silently fallback)
- Raise HTTPException 500 with clear error message

### 3. `backend/api/routers/podcasts/crud.py`

**Lines to verify**: 119-126 (cover_path assignment)

**Changes**:
- Add logging for GCS URL storage
- No logic changes needed (already stores returned filename)

---

## Success Criteria

- [ ] Users can upload cover art in onboarding step 5
- [ ] Cover art persists after Cloud Run deployment
- [ ] Users can upload intro audio in onboarding step 6
- [ ] Intro audio accessible immediately and after restart
- [ ] Users can upload outro audio in onboarding step 6
- [ ] Outro audio accessible immediately and after restart
- [ ] Database stores GCS URLs (starting with `gs://`)
- [ ] No 404 errors when accessing uploaded media
- [ ] Clear error messages if GCS upload fails
- [ ] Full onboarding flow completes successfully

---

## Rollback Plan

If deployment fails:

```powershell
# Rollback to revision 00530 (auth fixes)
gcloud run services update-traffic podcast-api `
  --region us-west1 `
  --to-revisions podcast-api-00530=100
```

---

## Post-Deployment Monitoring

```bash
# Check Cloud Run logs for GCS upload issues
gcloud logging read "resource.type=cloud_run_revision 
  AND resource.labels.service_name=podcast-api 
  AND resource.labels.revision_name=podcast-api-00531" `
  --limit=100 `
  --format=json | jq '.[] | select(.textPayload | contains("GCS") or contains("upload"))'

# Monitor for errors
gcloud logging read "resource.type=cloud_run_revision 
  AND resource.labels.service_name=podcast-api 
  AND severity>=ERROR" `
  --limit=50

# Check GCS bucket for new uploads
gsutil ls -lh gs://ppp-media-us-west1/**/covers/
gsutil ls -lh gs://ppp-media-us-west1/**/media/intro/
gsutil ls -lh gs://ppp-media-us-west1/**/media/outro/
```

---

## Timeline Estimate

- **Code Changes**: 20 minutes
- **Testing Locally**: 10 minutes
- **Deployment**: 5-10 minutes
- **Post-Deploy Testing**: 15 minutes
- **Total**: 50-55 minutes

---

**NEXT ACTION**: Implement fixes in the three identified files
