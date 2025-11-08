# Upload GCS URL Storage Fix - Summary

## Problem
Files uploaded to the dev server were not being stored in GCS, causing the worker server to fail with `FileNotFoundError` when trying to assemble episodes.

## Root Cause
1. Files were being uploaded to local storage only (not GCS)
2. MediaItem records stored only filenames (not GCS URLs)
3. Worker server couldn't download files because they weren't in GCS

## Solution Implemented

### 1. Upload Endpoint (`backend/api/routers/media_write.py`)
- **Changed**: All files now upload directly to GCS from memory (no local storage)
- **Changed**: MediaItem records now store GCS URLs (`gs://bucket/key`) instead of just filenames
- **Changed**: Added `allow_fallback=False` to prevent silent local storage fallback
- **Changed**: Added comprehensive logging to track upload process
- **Changed**: Added validation to ensure MediaItem filename is always a GCS URL before saving

### 2. Storage Layer (`backend/infrastructure/storage.py`)
- **Changed**: `upload_fileobj` and `upload_bytes` now default to `allow_fallback=False`
- **Changed**: Added validation to ensure results are cloud storage URLs (not local paths)
- **Changed**: Added explicit error handling when uploads fail or return invalid results
- **Changed**: Added logging to trace upload success/failure

### 3. Worker Download (`backend/worker/tasks/assembly/media.py`)
- **Changed**: Enhanced diagnostics to show MediaItem filename type (GCS URL vs filename)
- **Changed**: Improved error messages when files aren't found
- **Changed**: Added logging to show what paths are being checked in GCS

## Testing

### To Verify Upload Works:
1. **Upload a NEW file** (don't reuse old files)
2. **Check dev server logs** for:
   ```
   [upload.request] Received upload request: category=main_content, filename=...
   [upload.storage] Starting upload for main_content: filename=..., size=... bytes, bucket=...
   [upload.storage] Uploading main_content to gcs bucket ppp-media-us-west1, key: ...
   [storage] Uploading ... to GCS bucket ppp-media-us-west1 (allow_fallback=False)
   [storage] Successfully uploaded to GCS: gs://ppp-media-us-west1/...
   [upload.storage] SUCCESS: main_content uploaded to cloud storage: gs://...
   [upload.storage] MediaItem will be saved with filename='gs://...'
   [upload.storage] Creating MediaItem with filename='gs://...' (GCS/R2 URL)
   [upload.storage] MediaItem created: id=..., filename='gs://...'
   [upload.db] Committing 1 MediaItem(s) to database
   [upload.db] MediaItem saved: id=..., filename='gs://...' (starts with gs://: True, starts with http: False)
   ```
3. **Verify MediaItem in database** has a GCS URL (starts with `gs://` or `http`)
4. **Assemble an episode** with the new file
5. **Check worker logs** for:
   ```
   [assemble] MediaItem filename value: 'gs://...' (starts with gs://: True, starts with http: False, length=...)
   [assemble] ✅ Found MediaItem with GCS/R2 URL: gs://...
   [assemble] Downloading from cloud storage...
   [assemble] ✅ Successfully downloaded from cloud storage: gs://... -> /tmp/...
   ```

### To Diagnose Old Files:
Run the diagnostic script:
```bash
python scripts/check_media_item_gcs_url.py "filename.mp3"
```

This will show if the MediaItem has a GCS URL or just a filename.

## Important Notes

### Old Files Won't Work
Files uploaded **before** this fix:
- Have only filenames in the database (not GCS URLs)
- May not be in GCS
- Will fail when the worker tries to download them

**Solution**: Upload NEW files - they will have GCS URLs stored correctly.

### Worker Server Must Be Updated
The worker server needs the updated code to:
- Show enhanced diagnostics
- Properly handle GCS URLs in MediaItem records
- Download files from GCS correctly

**Action**: Deploy the updated worker code to the Proxmox server.

### GCS Credentials Required
The dev server MUST have GCS credentials configured:
- `GOOGLE_APPLICATION_CREDENTIALS` environment variable pointing to service account key
- OR GCS client must be able to authenticate via Application Default Credentials

If GCS credentials are missing, uploads will fail with a clear error message.

## Next Steps

1. ✅ **Upload code updated** - Files now upload to GCS and store URLs
2. ⏳ **Upload a NEW file** - Test the upload flow
3. ⏳ **Update worker server** - Deploy updated code to Proxmox
4. ⏳ **Test assembly** - Verify worker can download files from GCS
5. ⏳ **Migrate old files** (optional) - Re-upload old files or update database records

## Files Changed
- `backend/api/routers/media_write.py` - Upload endpoint
- `backend/infrastructure/storage.py` - Storage layer
- `backend/infrastructure/gcs.py` - GCS upload functions (default `allow_fallback=False`)
- `backend/worker/tasks/assembly/media.py` - Worker download logic

