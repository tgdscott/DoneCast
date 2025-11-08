# GCS File Not Found Diagnosis

## Problem
Worker server cannot find uploaded audio files in GCS, causing assembly to fail with `FileNotFoundError`.

## Current Status
- ✅ Worker code is running (new logs appearing)
- ✅ MediaItem lookup is working (finding records in database)
- ❌ Files are not found in GCS at expected paths
- ❌ MediaItem records have only filenames, not GCS URLs

## Root Cause Analysis

### Expected Behavior
1. File is uploaded via `/api/media/upload/main_content`
2. File is uploaded to GCS at: `{user_id_hex}/media_uploads/{filename}`
3. MediaItem record is saved with `filename = storage_url` (GCS URL like `gs://bucket/key`)
4. Worker looks up MediaItem, gets GCS URL, downloads file

### Actual Behavior
1. File upload may have succeeded or failed
2. MediaItem record has only filename (no GCS URL)
3. Worker constructs GCS path from filename
4. File not found in GCS at constructed path

## Possible Causes

### 1. Upload Failed Silently
- Upload code may have failed before saving GCS URL
- Exception caught but not logged properly
- Database transaction rolled back

### 2. File Uploaded Before Code Changes
- Files uploaded before `media_write.py` changes saved locally
- Old files have only filenames in database
- These files were never uploaded to GCS

### 3. GCS Upload Succeeded But Database Not Updated
- File uploaded to GCS successfully
- But database save failed or wasn't committed
- MediaItem still has old filename value

### 4. Wrong GCS Bucket or Path
- File uploaded to different bucket
- File uploaded to different path structure
- Storage backend configuration mismatch

## Diagnostic Steps

### 1. Check Upload Logs
Look for these log messages in dev server logs when uploading:
```
[upload.storage] Uploading main_content to bucket (backend: gcs), key: {path}
[upload.storage] SUCCESS: main_content uploaded: gs://bucket/key
```

If these don't appear, the upload is not reaching the GCS upload code.

### 2. Check Database
Query the MediaItem record:
```sql
SELECT id, filename, filesize, created_at 
FROM mediaitem 
WHERE filename LIKE '%fe7e244b073d4515ae29e0344016f956_Shit_covered_Plunger.mp3%';
```

Check if `filename` is:
- GCS URL: `gs://ppp-media-us-west1/...` ✅
- Just filename: `b6d5f77e699e444ba31ae1b4cb15feb4_fe7e244b...` ❌

### 3. Check GCS Bucket
List files in GCS bucket:
```bash
gsutil ls gs://ppp-media-us-west1/b6d5f77e699e444ba31ae1b4cb15feb4/media_uploads/
```

Or use GCS console to browse the bucket.

### 4. Check Worker Logs
The worker now logs:
- All GCS paths it checks
- Whether files are found
- List of files actually in GCS (if listing succeeds)

## Solution

### Immediate Fix
1. **Upload a NEW file** after the code changes
2. Verify upload logs show GCS upload success
3. Verify database has GCS URL stored
4. Try assembly with the new file

### Long-term Fix
1. **Backfill old files**: Upload existing files that are missing from GCS
2. **Update MediaItem records**: Set filename to GCS URL for existing records
3. **Add monitoring**: Alert when uploads fail or files are missing from GCS

## Code Changes Made

1. **`backend/api/routers/media_write.py`**:
   - Uploads files directly to GCS (no local storage)
   - Saves GCS URL to MediaItem.filename

2. **`backend/worker/tasks/assembly/media.py`**:
   - Looks up MediaItem in database
   - Checks multiple GCS path patterns
   - Downloads from GCS if file not found locally
   - Enhanced logging for diagnostics

## Next Steps

1. **Test with a new file upload**:
   - Upload a new file from dev server
   - Check dev logs for upload success
   - Check database for GCS URL
   - Try assembly

2. **If new file also fails**:
   - Check GCS credentials on dev server
   - Check GCS_BUCKET environment variable
   - Check upload error logs
   - Verify GCS client initialization

3. **If old files need to be fixed**:
   - Create migration script to upload old files to GCS
   - Update MediaItem records with GCS URLs
   - Or re-upload files manually

## Worker Logs to Watch

When assembly runs, look for:
- `[assemble] MediaItem filename value: '...'` - Shows what's in database
- `[assemble] Checking GCS path: gs://...` - Shows paths being checked
- `[assemble] ✅ Found file at GCS path: ...` - Success!
- `[assemble] ❌ File not found in GCS at any of these paths:` - Failure
- `[assemble] Found X files in GCS at prefix ...` - Shows what's actually in GCS

