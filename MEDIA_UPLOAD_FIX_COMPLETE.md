# Media Upload Fix - Complete

## Problem Identified
The file `backend/api/routers/media.py` (which is the actual upload endpoint being used) was:
1. **Only uploading non-main_content files to GCS** (intro, outro, music, sfx, commercial)
2. **NOT uploading main_content files to GCS** - they were only saved locally
3. **Storing only filenames in the database** instead of GCS URLs for main_content

This meant that when the worker tried to assemble episodes, it couldn't find the main_content files in GCS.

## Solution Implemented

### Updated `backend/api/routers/media.py`
- ✅ **All files now upload directly to GCS from memory** (no local storage)
- ✅ **main_content files are uploaded to GCS** at `{user_id}/media_uploads/{filename}`
- ✅ **Other categories upload to** `{user_id}/media/{category}/{filename}`
- ✅ **MediaItem records store GCS URLs** (`gs://bucket/key`) instead of just filenames
- ✅ **Added `allow_fallback=False`** to ensure cloud storage is always used
- ✅ **Added comprehensive logging** to track upload process
- ✅ **Transcription tasks now receive GCS URLs** instead of just filenames

## Key Changes

1. **Removed local file writes** - Files are read into memory and uploaded directly to GCS
2. **Added GCS upload for main_content** - Previously only other categories were uploaded
3. **Storage URL validation** - Ensures MediaItem always has a GCS/R2 URL before saving
4. **Enhanced logging** - Tracks upload requests, GCS uploads, and database saves

## Testing

### Next Steps:
1. **Restart the dev server** to load the updated code
2. **Upload a NEW main_content file** (don't reuse old files)
3. **Check dev server logs** for:
   ```
   [upload.request] Received upload request: category=main_content, filename=...
   [upload.storage] Starting upload for main_content: filename=..., size=... bytes, bucket=...
   [upload.storage] Uploading main_content to gcs bucket ppp-media-us-west1, key: ...
   [upload.storage] SUCCESS: main_content uploaded to cloud storage: gs://...
   [upload.storage] MediaItem will be saved with filename='gs://...'
   [upload.db] MediaItem saved: id=..., filename='gs://...' (starts with gs://: True)
   ```
4. **Verify MediaItem in database** has a GCS URL (starts with `gs://` or `http`)
5. **Assemble an episode** with the new file
6. **Check worker logs** - should show:
   ```
   [assemble] MediaItem filename value: 'gs://...' (starts with gs://: True, starts with http: False)
   [assemble] ✅ Found MediaItem with GCS/R2 URL: gs://...
   [assemble] Downloading from cloud storage...
   [assemble] ✅ Successfully downloaded from cloud storage: gs://... -> /tmp/...
   ```

## Important Notes

### Old Files Won't Work
Files uploaded **before** this fix:
- Have only filenames in the database (not GCS URLs)
- Were never uploaded to GCS (for main_content)
- Will fail when the worker tries to download them

**Solution**: Upload NEW files - they will have GCS URLs stored correctly.

### Storage Backend
- **Dev server**: Should use GCS (`STORAGE_BACKEND=gcs`)
- **Worker server**: Currently configured for R2 (`STORAGE_BACKEND=r2`)
- **Files uploaded to GCS** should be accessible from the worker if it has GCS credentials
- If worker is using R2, ensure it can also access GCS (or configure worker to use GCS)

### GCS Credentials
Both dev server and worker server MUST have GCS credentials configured:
- `GOOGLE_APPLICATION_CREDENTIALS` environment variable pointing to service account key
- OR GCS client must be able to authenticate via Application Default Credentials

If GCS credentials are missing, uploads will fail with a clear error message.

## Files Changed
- `backend/api/routers/media.py` - Main upload endpoint (now uploads all files to GCS)
- `backend/api/routers/media_write.py` - Alternative endpoint (also updated, but not currently used)

## Status
✅ **Code updated** - All files now upload to GCS
⏳ **Testing required** - Upload a new file and verify GCS URL is stored
⏳ **Worker verification** - Verify worker can download files from GCS

