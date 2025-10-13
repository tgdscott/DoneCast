# Raw Audio File Management Feature Implementation

## Overview
Implemented a comprehensive solution for managing raw podcast audio files after episode processing, giving users control over whether files are automatically deleted or kept for manual deletion.

## Date
October 13, 2025

## Features Implemented

### 1. Red Text Notification for Processed Episodes ✅

**Location:** `frontend/src/components/dashboard/podcastCreatorSteps/StepUploadAudio.jsx`

**What it does:**
- When an episode reaches "Processed", "Published", or "Scheduled" status
- A red notification box appears below the file upload area in Step 2
- Message: "This episode has successfully processed. You may delete this file."
- Only shows when user has auto-delete DISABLED

**Changes made:**
- Added `episodeStatus` prop to `StepUploadAudio` component
- Added conditional rendering of red notification box
- Passes episode status from `PodcastCreator` component via `assembledEpisode?.status`

### 2. User Setting for Auto-Delete ✅

**Backend:** `backend/api/routers/users.py`
**Frontend:** `frontend/src/components/dashboard/AudioCleanupSettings.jsx`

**What it does:**
- New user preference: `autoDeleteRawAudio` (boolean, default: `false`)
- Stored in `User.audio_cleanup_settings_json`
- Accessible via existing audio cleanup settings API

**Changes made:**
- Added `autoDeleteRawAudio: False` to backend defaults in `/api/users/me/audio-cleanup-settings`
- Added `autoDeleteRawAudio: false` to frontend `DEFAULT_SETTINGS`
- Setting is persisted using existing save mechanism

### 3. Settings UI Toggle ✅

**Location:** `frontend/src/components/dashboard/AudioCleanupSettings.jsx`

**What it does:**
- New section in Audio Cleanup Settings: "Raw file cleanup"
- Toggle switch labeled: "Automatically delete raw audio files after they are used"
- Helper text explains the behavior
- Uses existing save button and dirty state tracking

**Visual design:**
- Consistent with other audio cleanup settings
- Uses `Trash2` icon from lucide-react
- Follows existing styling patterns with SectionItem component

### 4. Backend Auto-Delete Logic ✅

**Location:** `backend/worker/tasks/assembly/orchestrator.py`

**What it does:**
- Modified `_cleanup_main_content()` function
- Before deleting files, checks user's `autoDeleteRawAudio` setting
- If setting is `false` (default), skips cleanup entirely
- If setting is `true`, proceeds with existing deletion logic

**Changes made:**
- Loads user from database
- Parses `audio_cleanup_settings_json`
- Checks `autoDeleteRawAudio` boolean
- Logs decision for debugging
- Falls back to NOT deleting if setting can't be read

**Deletion behavior (when enabled):**
- Deletes file from Google Cloud Storage (if stored there)
- Deletes local file (if stored locally)
- Removes MediaItem record from database
- Comprehensive logging throughout

## User Experience

### Scenario 1: Auto-Delete Disabled (Default)
1. User uploads raw audio file in Episode Creator Step 2
2. Episode is assembled and reaches "Processed" status
3. Raw file is **NOT** deleted automatically
4. Red notification appears in Step 2: "This episode has successfully processed. You may delete this file."
5. User can manually delete the file when ready

### Scenario 2: Auto-Delete Enabled
1. User goes to Settings → Audio Improvements
2. Scrolls to "Raw file cleanup" section
3. Enables "Automatically delete raw audio files after they are used"
4. Clicks "Save changes"
5. Future episodes: raw files are deleted automatically after processing
6. No red notification appears (file is already gone)

## Technical Details

### File Deletion Logic
The existing `_cleanup_main_content()` function handles:
- **GCS files:** Parses `gs://bucket/path` URIs and uses Google Cloud Storage client
- **Local files:** Checks multiple possible locations (MEDIA_DIR, media_uploads)
- **Database:** Removes MediaItem record with retry logic
- **Matching:** Flexible filename matching (exact, partial, with/without paths)

### Setting Storage
```json
{
  "autoDeleteRawAudio": false,
  "removeFillers": true,
  "removePauses": true,
  // ... other audio cleanup settings
}
```

### Status Check
Episodes with these statuses trigger the notification:
- `processed` - Episode assembly completed successfully
- `published` - Episode is live on Spreaker
- `scheduled` - Episode scheduled for future publication

## Files Modified

### Frontend
1. `frontend/src/components/dashboard/podcastCreatorSteps/StepUploadAudio.jsx`
   - Added `episodeStatus` prop
   - Added red notification box with conditional rendering

2. `frontend/src/components/dashboard/PodcastCreator.jsx`
   - Pass `assembledEpisode?.status` to StepUploadAudio

3. `frontend/src/components/dashboard/AudioCleanupSettings.jsx`
   - Added `autoDeleteRawAudio: false` to DEFAULT_SETTINGS
   - Added new "Raw file cleanup" SectionItem with toggle

### Backend
1. `backend/api/routers/users.py`
   - Added `"autoDeleteRawAudio": False` to settings defaults
   - Setting automatically saved/loaded via existing endpoints

2. `backend/worker/tasks/assembly/orchestrator.py`
   - Modified `_cleanup_main_content()` to check user setting
   - Added user lookup and settings parsing
   - Skip cleanup if `autoDeleteRawAudio` is false

## Testing Checklist

### With Auto-Delete OFF (Default)
- [ ] Upload audio file in Episode Creator
- [ ] Complete episode assembly
- [ ] Verify raw file still exists in media library
- [ ] Go back to Step 2 in Episode Creator
- [ ] Verify red notification appears
- [ ] Message reads: "This episode has successfully processed. You may delete this file."

### With Auto-Delete ON
- [ ] Go to Settings → Audio Improvements
- [ ] Find "Raw file cleanup" section
- [ ] Enable the toggle
- [ ] Save changes
- [ ] Create a new episode
- [ ] Complete episode assembly
- [ ] Verify raw file is automatically deleted from GCS/database
- [ ] Go back to Step 2
- [ ] Verify NO red notification appears (file already deleted)

### Edge Cases
- [ ] Test with very large files
- [ ] Test with files in GCS vs local storage
- [ ] Test with special characters in filenames
- [ ] Test changing setting mid-workflow
- [ ] Verify setting persists across sessions

## Backward Compatibility

- **Default behavior:** Files are NOT auto-deleted (safe, non-destructive)
- **Existing episodes:** Not affected (cleanup only happens at assembly time)
- **Existing users:** Default to manual deletion (current behavior)
- **No migrations needed:** Setting is optional in JSON structure

## Future Enhancements

Possible improvements for later:
1. Bulk deletion UI for orphaned raw files
2. Storage usage dashboard showing raw file sizes
3. Retention period setting (e.g., "Delete after 30 days")
4. Notification when storage limit is reached
5. Download raw file before deletion option
6. Trash/recycle bin for accidental deletions

## Notes

- The existing cleanup logic was already robust and well-tested
- We simply made it conditional based on user preference
- Logging is comprehensive for troubleshooting
- Falls back to safe behavior (don't delete) if setting can't be read
- UI is consistent with existing audio cleanup settings
- No breaking changes to existing workflows
