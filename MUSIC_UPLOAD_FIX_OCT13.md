# Music Upload Fix - October 13, 2025

## Issue
Uploading global music in the Admin Panel Music Library was causing 500 Internal Server Error and CORS errors in the browser console.

### Error Messages
```
Access to fetch at 'https://api.podcastsplusplus.com/api/music/assets/' from origin 'https://podcastsplusplus.com' has been blocked by CORS policy
Failed to load resource: net::ERR_FAILED
POST https://api.getpodcastplus.com/admin/music/assets/upload 500 (Internal Server Error)
```

## Root Cause
The `/api/admin/music/assets/upload` endpoint (in `backend/api/routers/admin/music.py`) was synchronously reading from an UploadFile stream which could fail or be consumed before being passed to GCS upload functions. The error handling was also insufficient for debugging.

**Note:** There were two upload endpoints - one in `admin.py` and the actual active one in `admin/music.py`. The correct file needed to be fixed.

## Solution

### Changes Made to `backend/api/routers/admin/music.py`

1. **Made the endpoint async** - Changed from `def` to `async def` to properly handle file uploads
2. **Read file contents first** - Read the entire file into memory using `await file.read()` before processing
3. **Use temporary file for GCS** - Create a temporary file on disk that can be reliably uploaded to GCS
4. **Enhanced error logging** - Added detailed logging with file size, path info, and full stack traces
5. **Proper cleanup** - Added finally block to clean up temporary files
6. **Better validation** - Check if file is empty before attempting upload

### Key Code Changes

```python
@router.post("/music/assets/upload", status_code=201)
async def admin_upload_music_asset(  # Now async
    file: UploadFile = File(...),
    ...
):
    import tempfile
    import traceback
    
    temp_path = None
    try:
        # Read file contents into memory first
        file_content = await file.read()
        if not file_content:
            raise HTTPException(status_code=400, detail="Empty file received")
        
        # Log for debugging
        log.info(f"Uploading music file: {orig} ({len(file_content)} bytes)")

        # Create temp file for reliable GCS upload
        if bucket:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(file_content)
                temp_path = tmp.name
            
            with open(temp_path, "rb") as f:
                stored_uri = gcs_upload_fileobj(bucket, key, f, ...)
        else:
            # Direct write for local storage
            with out_path.open("wb") as f:
                f.write(file_content)
        
        # ... rest of the logic ...
        
    finally:
        # Clean up temp file
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass
```

## Testing

1. Navigate to Admin Panel → Music Library
2. Click "Add New" 
3. Select an audio file (MP3 recommended)
4. Enter display name and mood tags
5. Click "Create"
6. Verify:
   - No CORS errors in console
   - Upload progress shows
   - Success message appears
   - Music asset appears in the list

## Notes

- The CORS configuration was already correct - the 500 error was preventing CORS headers from being sent
- The fix ensures file streams are properly handled in async context
- Temporary files are used as an intermediate step for reliable GCS uploads
- All errors now include full stack traces for easier debugging

## Related Files
- `backend/api/routers/admin/music.py` - **ACTUAL fix location** (music router with /upload endpoint)
- `backend/api/routers/admin.py` - Also fixed but this endpoint wasn't being used
- `frontend/src/components/admin/AdminMusicLibrary.jsx` - Frontend component (no changes needed)
- `backend/infrastructure/gcs.py` - GCS upload utilities (no changes needed)

## Important Notes
- The admin router includes the music router at `/admin` prefix, so music router's `/upload` becomes `/admin/music/assets/upload`
- There were duplicate endpoints - the one in `admin/music.py` is the active one
