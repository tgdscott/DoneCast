# Upload 501 Fallback Fix

## Issue
Users getting "Upload failed" error with 501 status code when trying to upload audio files.

**Screenshot Error:** "Failed to load resource: the server responded with a status of 501 ()"

## Root Cause
The frontend `uploadMediaDirect` function was trying to use the direct GCS upload flow:
1. Call `/api/media/upload/{category}/presign` to get signed upload URL
2. Upload directly to GCS
3. Call `/api/media/upload/{category}/register` to register the uploaded file

However, the backend presign/register endpoints intentionally return **501 Not Implemented** because:
- Direct upload feature not yet fully implemented
- Endpoints return 501 to signal "use standard upload instead"

The problem: **Frontend didn't detect the 501 and fall back** - it just threw an error.

## Solution
Enhanced `uploadMediaDirect` to detect 501 and automatically fall back to standard multipart/form-data upload:

### Changes to `frontend/src/lib/directUpload.js`:

1. **Wrap presign call in try/catch**:
   ```javascript
   try {
     presign = await api.post(`/api/media/upload/${category}/presign`, {
       filename: file.name || 'upload',
       content_type: contentType,
     });
   } catch (err) {
     // If presign returns 501, fall back to standard upload
     if (err?.response?.status === 501 || err?.status === 501) {
       useDirectUpload = false;
     } else {
       throw err; // Re-throw other errors
     }
   }
   ```

2. **Add fallback path for standard upload**:
   - Use `multipart/form-data` with FormData
   - Send to `/api/media/upload/{category}` (existing endpoint)
   - Use XMLHttpRequest to track progress
   - Preserve notify_when_ready and notify_email parameters

3. **Both paths support progress tracking**:
   - Direct upload: Progress tracked during GCS upload
   - Standard upload: Progress tracked during multipart upload
   - User experience identical regardless of path

## Impact

**Before:**
- Upload fails with 501 error
- No fallback mechanism
- User blocked from uploading

**After:**
- Tries direct upload first
- If 501, automatically falls back to standard upload
- User sees seamless upload with progress bar
- Works whether presign is implemented or not

## Technical Details

### Standard Upload Flow (Current Active Path):
```
1. Frontend: Create FormData with file + friendly_name
2. Frontend: POST /api/media/upload/main_content (multipart)
3. Backend: Receive file, validate, save to GCS
4. Backend: Create MediaItem record in database
5. Backend: Return MediaItem to frontend
6. Backend: Trigger transcription worker (if notify_when_ready=true)
```

### Direct Upload Flow (Future - When Presign Implemented):
```
1. Frontend: POST /api/media/upload/main_content/presign
2. Backend: Generate GCS signed URL + object_path
3. Frontend: PUT file directly to GCS signed URL
4. Frontend: POST /api/media/upload/main_content/register
5. Backend: Verify object in GCS, create MediaItem record
6. Backend: Return MediaItem to frontend
```

**Benefits of Direct Upload (when implemented):**
- Faster uploads (no API server bottleneck)
- Resumable uploads
- Chunked uploads for large files
- Lower server load

**Current Standard Upload Works Because:**
- Backend endpoint validates and saves to GCS
- Progress tracking via XHR upload events
- Same result: file in GCS + MediaItem in database

## Deployment Status

**Commit:** 8c62a738
**Message:** "Fix: Handle 501 fallback in uploadMediaDirect"
**Status:** Deploying to Cloud Run
**Build:** In progress

## Testing

After deployment, test:

1. **Upload Audio File:**
   - Navigate to Upload Audio page
   - Select Trust.mp3
   - Enter friendly name "Trust"
   - Enable "Email me when ready"
   - Click Upload
   - Expected: Progress bar shows, upload completes, success message

2. **Verify Upload:**
   - Check GCS: `gs://ppp-media-us-west1/.../main_content/*.mp3`
   - Check database: MediaItem with gs:// URL in filename
   - Wait for transcription notification email

3. **Try Assembly:**
   - Navigate to Episode Assembler
   - Select uploaded Trust.mp3
   - Create episode with template
   - Expected: Assembly completes without "invalid audio file" error

## Notes

- The 501 response is **intentional** - it's the backend saying "not implemented yet"
- Frontend now **gracefully handles this** by falling back
- When direct upload is fully implemented, change backend to return proper presign response
- Frontend will automatically use direct upload once available
- Zero code changes needed when presign is implemented

## Related Files

- `frontend/src/lib/directUpload.js` - Fixed fallback logic
- `backend/api/routers/media.py` - Presign/register stubs (lines 570-600)
- `backend/api/routers/media.py` - Standard upload endpoint (lines 37-300)
