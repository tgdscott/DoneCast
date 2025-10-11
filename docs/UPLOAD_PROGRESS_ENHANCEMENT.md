# Upload Progress Enhancement

## Current State

### Concurrent Uploads
- **Status:** Sequential (one at a time)
- **Location:** `frontend/src/ab/pages/CreatorUpload.jsx` line 488-500
- **Reason:** "Sequential uploads to keep UI/order predictable"

### Progress Tracking

#### What's Already Built:
The `uploadMediaDirect()` function in `frontend/src/lib/directUpload.js` already calculates:
- ✅ `percent` - Upload percentage (0-100)
- ✅ `loaded` - Bytes uploaded so far
- ✅ `total` - Total file size in bytes
- ✅ `bytesPerSecond` - Current upload speed (smoothed)
- ✅ `etaSeconds` - Estimated time remaining

#### Where It's Used:

**AB Creator (`CreatorUpload.jsx`)** - ✅ FULLY IMPLEMENTED
- Shows percentage, speed, ETA, and bytes progress
- Example: "45% • 450 MB of 1 GB • 8.5 MB/s • 2m 15s remaining"

**Main Podcast Creator** - ⚠️ PARTIALLY IMPLEMENTED
- Only shows percentage bar
- Missing: speed, ETA, bytes uploaded
- Location: `usePodcastCreator.js` line 972

## Recommended Enhancements

### Option 1: Quick Fix - Add Progress Details to Main Creator

Update `frontend/src/components/dashboard/hooks/usePodcastCreator.js` line 961-996:

```javascript
// ADD NEW STATE
const [uploadProgress, setUploadProgress] = useState(null);
const [uploadStats, setUploadStats] = useState(null); // NEW

// UPDATE onProgress callback (line 971)
onProgress: ({ percent, loaded, total, bytesPerSecond, etaSeconds }) => {
  if (typeof percent === 'number') setUploadProgress(percent);
  setUploadStats({ loaded, total, bytesPerSecond, etaSeconds }); // NEW
},
```

Then pass `uploadStats` down to `StepUploadAudio.jsx` and display:

```jsx
{isUploading && uploadStats && (
  <div className="text-xs text-slate-600 mt-1">
    {formatBytes(uploadStats.loaded)} of {formatBytes(uploadStats.total)} • 
    {formatSpeed(uploadStats.bytesPerSecond)} • 
    {formatEta(uploadStats.etaSeconds)}
  </div>
)}
```

**Helper functions** (copy from `CreatorUpload.jsx` lines 5-40):
```javascript
const formatBytes = (bytes) => {
  if (!Number.isFinite(bytes) || bytes <= 0) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
};

const formatSpeed = (bytesPerSecond) => {
  if (!Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) return '';
  return `${formatBytes(bytesPerSecond)}/s`;
};

const formatEta = (seconds) => {
  if (!Number.isFinite(seconds) || seconds <= 0) return '';
  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  if (minutes > 0) {
    return `${minutes}m ${secs.toString().padStart(2, '0')}s remaining`;
  }
  return `${secs}s remaining`;
};
```

### Option 2: Enable Concurrent Uploads

**Benefits:**
- Faster bulk uploads
- Better utilization of available bandwidth
- Users can upload multiple raw files simultaneously

**Considerations:**
- Browser limit: 6 concurrent connections per domain
- Network congestion if too many uploads
- More complex UI (multiple progress bars)
- GCS upload limits

**Implementation in `CreatorUpload.jsx`:**

```javascript
// Change from sequential (line 488)
for (let i = 0; i < files.length; i++) {
  const item = await uploadOneFile(files[i]);
  if (item) createdDrafts.push(item);
}

// To parallel with limit
const MAX_CONCURRENT = 3;
const chunks = [];
for (let i = 0; i < files.length; i += MAX_CONCURRENT) {
  chunks.push(files.slice(i, i + MAX_CONCURRENT));
}

for (const chunk of chunks) {
  const items = await Promise.all(chunk.map(f => uploadOneFile(f)));
  createdDrafts.push(...items.filter(Boolean));
}
```

**UI Changes Needed:**
- Show all files in the upload list immediately
- Each file gets its own progress bar
- Display "Uploading 2 of 5 files..." status

### Option 3: Background Upload with Notification

**Best for large files (500MB+):**
- Start upload in background
- User can navigate away
- Show toast notification when complete
- Email notification option (already implemented!)

**Already Available in `PreUploadManager.jsx`:**
- `notify_when_ready` flag
- `notify_email` parameter
- User can leave the page during upload

## Recommended Approach

**Phase 1 (Quick Win):**
✅ Add progress details to main podcast creator (Option 1)
- ~30 minutes of work
- Huge UX improvement
- Leverages existing infrastructure

**Phase 2 (Future Enhancement):**
- Enable concurrent uploads with limit of 2-3 (Option 2)
- Test with various file sizes and network speeds
- Add per-file progress indicators in UI

**Phase 3 (Advanced):**
- Chunked upload with resume capability
- Better handling of network interruptions
- Upload queue management

## File Size Limits

Current limits (from `media_write.py` line 51):
```python
MediaCategory.main_content: 1536 * MB  # 1.5 GB
MediaCategory.intro: 50 * MB
MediaCategory.outro: 50 * MB
MediaCategory.music: 50 * MB
MediaCategory.commercial: 50 * MB
MediaCategory.sfx: 25 * MB
MediaCategory.podcast_cover: 10 * MB
MediaCategory.episode_cover: 10 * MB
```

## Testing Recommendations

1. **Upload Progress Accuracy:**
   - Test with files of various sizes (10MB, 100MB, 500MB, 1GB)
   - Verify ETA updates smoothly
   - Check speed calculation is accurate

2. **Concurrent Upload Stability:**
   - Upload 5 files simultaneously
   - Verify all complete successfully
   - Check database consistency

3. **Error Handling:**
   - Network interruption mid-upload
   - File too large
   - Invalid file type
   - Browser tab closed during upload
