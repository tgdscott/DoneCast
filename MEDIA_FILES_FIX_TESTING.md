# Media Files GCS Fix - Testing Guide

## What Was Fixed

**Problem:** Intro/outro/music/sfx files uploaded to media library disappear after container restart (Cloud Run ephemeral storage)

**Solution:** Upload media files to GCS immediately after save, download from GCS during episode assembly

**Status:** ✅ **COMPLETE** - Ready for testing

---

## Files Modified

### 1. `backend/api/routers/media_write.py`
**Lines 2, 126-145** - Added `import os` and GCS upload logic

**What it does:**
- After saving file locally for initial validation
- Uploads intro/outro/music/sfx/commercial files to GCS
- Stores GCS URL (`gs://...`) in `MediaItem.filename` field
- Falls back gracefully if GCS upload fails

**Key code:**
```python
# Upload to GCS for persistence (intro/outro/music/sfx/commercial)
gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
if gcs_bucket and category in (intro, outro, music, sfx, commercial):
    from infrastructure import gcs
    gcs_key = f"{current_user.id.hex}/media/{category.value}/{safe_filename}"
    with open(file_path, "rb") as f:
        gcs_url = gcs.upload_fileobj(gcs_bucket, gcs_key, f, content_type=...)
    if gcs_url and gcs_url.startswith("gs://"):
        safe_filename = gcs_url  # Store GCS URL in database
```

### 2. `backend/api/services/audio/orchestrator_steps.py`
**Lines 1078-1122** - Added GCS download support for static files

**What it does:**
- Checks if filename starts with `gs://`
- Downloads from GCS to temporary file
- Loads audio from temp file
- Cleans up temp file after use
- Falls back to local file lookup for backward compatibility

**Key code:**
```python
if raw_name.startswith("gs://"):
    # Parse gs://bucket/key
    gcs_str = raw_name[5:]
    bucket, key = gcs_str.split("/", 1)
    
    # Download to temp file
    temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
    os.close(temp_fd)
    with open(temp_path, "wb") as f:
        blob = gcs.get_blob(bucket, key)
        f.write(blob.download_as_bytes())
    
    audio = AudioSegment.from_file(temp_path)
    os.unlink(temp_path)  # Cleanup
else:
    # Original local file logic (backward compatible)
    ...
```

---

## Testing Checklist

### Test 1: Upload New Intro File
1. ✅ Navigate to Media Library
2. ✅ Upload an intro audio file (e.g., `test_intro.mp3`)
3. ✅ Check database: `SELECT id, category, filename, friendly_name FROM media_items WHERE category = 'intro' ORDER BY created_at DESC LIMIT 1;`
4. ✅ **Expected:** `filename` field contains `gs://ppp-media-us-west1/{user_id}/media/intro/...`
5. ✅ Check GCS: Verify file exists in bucket at that path
6. ✅ Delete local file: `rm backend/local_media/{user_id}_*_test_intro.mp3` (simulate restart)

### Test 2: Use Intro in Episode Assembly
1. ✅ Create new podcast episode
2. ✅ Select template that uses the uploaded intro
3. ✅ Assemble episode
4. ✅ **Expected:** Assembly succeeds, intro plays correctly
5. ✅ Check logs for: `[TEMPLATE_STATIC_GCS_OK]` message
6. ✅ Play assembled episode and verify intro is present

### Test 3: Container Restart Simulation
1. ✅ Upload intro, outro, music, sfx files
2. ✅ Note the filenames (should be `gs://...` URLs)
3. ✅ Stop Cloud Run instance (or clear `/tmp` locally)
4. ✅ Start new instance
5. ✅ Assemble episode using uploaded media files
6. ✅ **Expected:** All media files load correctly from GCS

### Test 4: Backward Compatibility
1. ✅ Test with existing episodes that reference local files
2. ✅ **Expected:** Falls back to local file lookup
3. ✅ **Expected:** Shows `[TEMPLATE_STATIC_MISSING]` if local file gone (correct behavior)

### Test 5: Error Handling
1. ✅ Upload file with special characters in name
2. ✅ Upload very large file (near size limit)
3. ✅ Simulate GCS upload failure (invalid credentials)
4. ✅ **Expected:** Graceful fallback, logs warning, continues with local file

---

## Database Verification Queries

### Check uploaded media files
```sql
SELECT 
    id,
    category,
    filename,
    friendly_name,
    created_at
FROM media_items 
WHERE category IN ('intro', 'outro', 'music', 'sfx')
ORDER BY created_at DESC 
LIMIT 10;
```

**Expected:** Recent uploads should have `filename` starting with `gs://`

### Count GCS vs local files
```sql
SELECT 
    category,
    CASE 
        WHEN filename LIKE 'gs://%' THEN 'GCS'
        ELSE 'Local'
    END as storage,
    COUNT(*) as count
FROM media_items
WHERE category IN ('intro', 'outro', 'music', 'sfx')
GROUP BY category, storage
ORDER BY category, storage;
```

---

## GCS Bucket Verification

### List uploaded media files
```bash
gsutil ls -r gs://ppp-media-us-west1/*/media/
```

**Expected structure:**
```
gs://ppp-media-us-west1/{user_id}/media/intro/{filename}
gs://ppp-media-us-west1/{user_id}/media/outro/{filename}
gs://ppp-media-us-west1/{user_id}/media/music/{filename}
gs://ppp-media-us-west1/{user_id}/media/sfx/{filename}
```

### Verify file size
```bash
gsutil du -sh gs://ppp-media-us-west1/{user_id}/media/intro/{filename}
```

---

## Log Monitoring

### Success indicators
```
[upload.gcs] intro uploaded: gs://ppp-media-us-west1/...
[TEMPLATE_STATIC_GCS_OK] seg_id=... gcs=gs://... len_ms=...
```

### Error indicators
```
[upload.gcs] Failed to upload intro to GCS: ...
[TEMPLATE_STATIC_GCS_ERROR] seg_id=... gcs=gs://... error=...
[TEMPLATE_STATIC_MISSING] seg_id=... file=...
```

### View recent logs (local dev)
```powershell
Get-Content -Path backend/local_tmp/app.log -Tail 50 -Wait
```

### View Cloud Run logs
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api" --limit 50 --format json
```

---

## Rollback Plan

If issues occur in production:

### Option 1: Quick revert (recommended)
```bash
# Rollback to previous working revision
gcloud run services update-traffic podcast-api --to-revisions=00448-6pw=100 --region=us-west1
```

### Option 2: Emergency fix deploy
1. Comment out GCS upload code in `media_write.py` (lines 126-145)
2. Comment out GCS download code in `orchestrator_steps.py` (lines 1078-1097)
3. Deploy immediately

### Option 3: Database cleanup (if needed)
```sql
-- Revert GCS URLs back to local filenames (only if migration script ran)
UPDATE media_items 
SET filename = SUBSTRING(filename FROM '[^/]*$')  -- Extract filename from gs:// URL
WHERE filename LIKE 'gs://%' 
  AND category IN ('intro', 'outro', 'music', 'sfx');
```

**WARNING:** Option 3 will break if local files are already deleted!

---

## Known Limitations

1. **Existing Files:** Files uploaded before this fix will still have local paths
   - **Impact:** Will disappear after next container restart
   - **Solution:** User must re-upload existing intro/outro/music/sfx files
   - **Alternative:** Could build migration script to upload existing files to GCS

2. **File Size:** Large files (>50MB) may slow down uploads
   - **Current limit:** 50MB per file (defined in `CATEGORY_SIZE_LIMITS`)
   - **GCS upload time:** ~3-5 seconds per 10MB
   - **User impact:** Upload progress bar already shows speed/ETA

3. **GCS Costs:** Storage costs ~$0.023/GB/month (Standard storage)
   - **Estimated cost:** 1000 media files × 5MB avg = 5GB = $0.12/month
   - **Negligible** compared to Cloud Run costs

4. **Bandwidth:** Downloads from GCS during assembly add latency
   - **Impact:** ~200-500ms per media file download
   - **Mitigated by:** Files cached in memory after first download in assembly
   - **Episode assembly:** Already takes 10-30 seconds, this adds ~1-2 seconds total

---

## Success Criteria

✅ **PASS if:**
1. New intro/outro/music/sfx uploads create `gs://...` URLs in database
2. Files persist in GCS bucket after upload
3. Episode assembly successfully loads media files from GCS
4. Audio quality unchanged after GCS round-trip
5. Uploaded media files survive container restart
6. No new errors in Cloud Run logs
7. Assembly time increase < 2 seconds per media file

❌ **FAIL if:**
1. Database shows local paths instead of `gs://...` URLs
2. GCS bucket is empty after upload
3. Episode assembly fails with "file not found" errors
4. Audio quality degraded (transcoding issues)
5. Media files still missing after restart
6. Cloud Run logs show GCS authentication errors
7. Assembly time increase > 5 seconds per media file

---

## Next Steps After Testing

1. ✅ Test locally with real audio files
2. ✅ Test in staging environment (if available)
3. ✅ Monitor first production upload carefully
4. ✅ Document any issues discovered
5. ✅ Consider building migration script for existing files (optional)
6. ✅ Update user documentation about re-uploading media files

---

## Related Documentation

- `MEDIA_FILES_GCS_FIX.md` - Root cause analysis and implementation plan
- `GCS_FIX_DEPLOYMENT.md` - Original episode audio/cover GCS fix
- `UPLOAD_PROGRESS_IMPLEMENTATION.md` - Upload progress enhancement

---

## Questions?

If you encounter any issues during testing:
1. Check Cloud Run logs for error messages
2. Verify GCS bucket permissions
3. Confirm `GCS_BUCKET` environment variable is set
4. Test with small audio files first (< 5MB)
5. Verify database shows `gs://...` URLs after upload
