# Worker GCS Download Fix

## Problem
The worker server is failing to download audio files from GCS, resulting in `FileNotFoundError` when trying to assemble episodes.

## Root Cause
1. The worker server is running old code that doesn't include the GCS download logic
2. When a file is uploaded to GCS from the dev server, the worker tries to find it locally first
3. If not found locally, the old code doesn't attempt to download from GCS

## Solution Implemented
Updated `backend/worker/tasks/assembly/media.py` to:
1. **Look up MediaItem in database** when file is not found locally
2. **Check if MediaItem has GCS/R2 URL** - if so, download directly
3. **Construct GCS path** if MediaItem only has filename - check at `{user_id}/media_uploads/{filename}`
4. **Download from GCS** using `_resolve_media_file()` which handles both GCS (`gs://`) and R2 (`https://`) URLs
5. **Enhanced logging** to trace the download process

## Changes Made
1. **Media Item Lookup**: Added comprehensive MediaItem lookup with multiple matching strategies:
   - Exact filename match
   - Filename ending match (for GCS URLs)
   - Partial match
   - Extracted basename match

2. **GCS Path Construction**: If MediaItem only has a filename (not a GCS URL), construct the expected GCS path:
   - Primary: `{user_id_hex}/media_uploads/{filename}`
   - Fallback: `{user_id_hex}/media/main_content/{filename}`

3. **Download Logic**: Use `_resolve_media_file()` to download from GCS/R2, which:
   - Handles `gs://` URLs (GCS)
   - Handles `https://` URLs (R2)
   - Downloads to local media directory
   - Returns path to downloaded file

4. **Enhanced Logging**: Added detailed logging at each step:
   - When looking up MediaItem
   - When checking GCS paths
   - When downloading from GCS
   - When download succeeds/fails

## Deployment Steps
1. **Update worker server code**:
   ```bash
   # On worker server, pull latest code
   cd /path/to/CloudPod
   git pull origin main  # or your branch
   ```

2. **Restart worker service**:
   ```bash
   # Restart the worker service (method depends on your setup)
   systemctl restart podcast-worker
   # OR
   supervisorctl restart podcast-worker
   # OR whatever service manager you're using
   ```

3. **Verify deployment**:
   - Check worker logs for the new log messages
   - Upload a new file from dev server
   - Try assembling an episode
   - Check logs for GCS download attempts

## Testing
1. **Upload a new file** from dev server (this will upload to GCS)
2. **Start assembly** from dev server (should route to worker)
3. **Check worker logs** for:
   - `[assemble] Audio file not found locally, looking up MediaItem for: ...`
   - `[assemble] Found %d main_content MediaItems for user ...`
   - `[assemble] Checking GCS path: gs://...`
   - `[assemble] downloading main content from GCS: ...`
   - `[assemble] Successfully downloaded main content from GCS to: ...`

## Expected Behavior
1. Worker receives assembly request with `main_content_filename`
2. Worker tries to resolve file locally (won't find it)
3. Worker looks up MediaItem in database
4. Worker finds MediaItem with GCS URL or constructs GCS path
5. Worker downloads file from GCS to local media directory
6. Worker uses downloaded file for assembly
7. Assembly completes successfully

## Troubleshooting
If downloads still fail:
1. **Check GCS credentials** on worker server
2. **Verify GCS_BUCKET** environment variable is set
3. **Check file exists in GCS** at expected path
4. **Verify MediaItem filename** matches expected format
5. **Check worker logs** for specific error messages

## Related Files
- `backend/worker/tasks/assembly/media.py` - Main media resolution logic
- `backend/api/routers/media_write.py` - File upload (saves to GCS)
- `backend/infrastructure/gcs.py` - GCS storage utilities

