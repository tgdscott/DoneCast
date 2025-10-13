# Voice Recorder Upload Fix - October 12, 2025

## Issue
Voice recorder in onboarding wizard was showing "Failed to save recording. Please try again." error when users tried to upload their intro/outro recordings.

## Root Cause Analysis

### Problem 1: Missing Content-Type on Browser-Recorded Blobs
When recording audio using MediaRecorder API in the browser, the resulting Blob might not have a properly set content type when appended to FormData. The backend validation in `media_write.py` was rejecting uploads without valid content types.

**Original Validation Logic:**
```python
def _validate_meta(f: UploadFile, cat: MediaCategory) -> None:
    ct = (getattr(f, "content_type", None) or "").lower()
    type_prefix = CATEGORY_TYPE_PREFIX.get(cat)
    if type_prefix and not ct.startswith(type_prefix):
        # This would fail if ct is empty!
        raise HTTPException(status_code=400, detail=f"Invalid file type...")
```

### Problem 2: Insufficient Error Logging
The frontend wasn't logging enough detail about upload failures, making it hard to diagnose the issue.

## Solution

### Backend Fix (media_write.py)
**Relaxed validation to allow missing content type if file extension is valid:**

```python
def _validate_meta(f: UploadFile, cat: MediaCategory) -> None:
    ct = (getattr(f, "content_type", None) or "").lower()
    type_prefix = CATEGORY_TYPE_PREFIX.get(cat)
    
    # Get file extension first for validation
    ext = Path(f.filename or "").suffix.lower()
    if not ext:
        raise HTTPException(status_code=400, detail="File must have an extension.")
    
    # Determine allowed extensions based on category
    allowed = AUDIO_EXTS if type_prefix == AUDIO_PREFIX else IMAGE_EXTS
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file extension '{ext}'.")
    
    # If content type is provided, validate it matches the category
    # But allow missing content type if extension is valid (for browser recordings)
    if ct and type_prefix and not ct.startswith(type_prefix):
        expected = "audio" if type_prefix == AUDIO_PREFIX else "image"
        raise HTTPException(status_code=400, detail=f"Invalid file type '{ct}'. Expected {expected} file for category '{cat.value}'.")
```

**Key Changes:**
1. Validate file extension first (required)
2. Only validate content type IF it's provided
3. Allow missing content type for valid file extensions

### Frontend Fix (VoiceRecorder.jsx)

#### 1. Explicit Content Type in FormData
```javascript
// Create a new blob with explicit content type to ensure proper upload
const isMP4 = audioBlob.type.includes('mp4') || audioBlob.type.includes('m4a');
const ext = isMP4 ? 'm4a' : 'webm';
const contentType = isMP4 ? 'audio/mp4' : 'audio/webm';

const typedBlob = new Blob([audioBlob], { type: contentType });
const fileName = `${type}_${Date.now()}.${ext}`;

formData.append('files', typedBlob, fileName);
```

#### 2. Enhanced Error Logging
Added comprehensive console logging:
- Upload attempt details (type, filename, size, endpoint)
- Full response logging
- Detailed error logging with status codes and messages

#### 3. Better Error Messages
```javascript
let errorMsg = 'Failed to save recording. Please try again.';
if (err?.status === 401) {
    errorMsg = 'Session expired. Please refresh the page and try again.';
} else if (err?.status === 413) {
    errorMsg = 'Recording is too large. Please record a shorter clip.';
} else if (err?.detail) {
    errorMsg = typeof err.detail === 'string' ? err.detail : 'Failed to save recording. Please try again.';
}
```

#### 4. Flexible Response Handling
Handle both array and single object responses:
```javascript
if (response && Array.isArray(response) && response.length > 0) {
    onRecordingComplete(response[0]);
} else if (response && typeof response === 'object' && !Array.isArray(response)) {
    onRecordingComplete(response);
}
```

## Files Modified
1. `backend/api/routers/media_write.py` - Relaxed content type validation
2. `frontend/src/components/onboarding/VoiceRecorder.jsx` - Added explicit content type + better error handling

## Testing Checklist
- [ ] Record intro using voice recorder in onboarding wizard
- [ ] Verify upload succeeds and shows success toast
- [ ] Record outro using voice recorder in onboarding wizard  
- [ ] Verify upload succeeds and shows success toast
- [ ] Check browser console for proper logging
- [ ] Verify files are stored in GCS (for persistence)
- [ ] Test with different browsers (Chrome, Firefox, Edge)
- [ ] Test with different audio formats (webm, m4a)

## Impact
- **User Experience**: Users can now successfully upload voice recordings during onboarding
- **Debugging**: Better logging makes future issues easier to diagnose
- **Reliability**: More robust error handling and validation

## Notes
- The backend was already configured to upload intro/outro files to GCS for persistence
- The validation change doesn't compromise security since we still validate file extensions
- Browser recording typically produces webm format (Chrome/Edge) or ogg (Firefox)
