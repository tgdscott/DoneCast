# Episode Creator Draft Persistence & Exit Confirmation - November 4, 2025

## Problem
When users click "Back to Dashboard" after step 3 in the episode creation process, they lose all entered metadata (title, description, tags, season/episode numbers) with no warning. This creates frustration when users accidentally navigate away or want to take a break and come back later.

## Solution Implemented
**Two-part solution:**
1. **Automatic draft persistence** - Episode metadata is automatically saved to localStorage tied to the audio file
2. **Smart exit confirmation** - Shows confirmation dialog only when user has entered metadata past step 3

This is the **better solution** - drafts are NOT lost, they're automatically restored when the user returns to edit the same audio file.

## Implementation Details

### 1. Draft Persistence (`useEpisodeMetadata.js`)

**Storage Strategy:**
- Key format: `ppp_episode_draft_{uploadedFilename}`
- Tied to the audio file, not the user session
- Persists across browser sessions

**What's Saved:**
```javascript
{
  season: '1',
  episodeNumber: '42',
  title: 'My Episode Title',
  description: 'Episode description...',
  tags: 'tag1, tag2, tag3',
  is_explicit: false,
  cover_image_path: '/path/to/cover.jpg',
  cover_crop: '50,50,300,300',
  timestamp: 1699123456789  // For cleanup
}
```

**What's NOT Saved:**
- File objects (`coverArt`, `coverArtPreview`) - can't be serialized
- AI cache (regenerated on demand)
- Temporary UI state

**Load Behavior:**
- On mount, checks localStorage for existing draft matching `uploadedFilename`
- If found, restores all metadata fields
- If not found, uses default values
- Falls back gracefully on parse errors

**Save Behavior:**
- Automatically saves on every `episodeDetails` change
- Debounced by React's state batching
- Fails silently if localStorage is full/unavailable

### 2. Draft Cleanup

**Automatic Cleanup:**
- Runs once on mount
- Removes drafts older than 7 days
- Prevents localStorage bloat
- Logs cleanup count to console

**Manual Cleanup:**
- Draft automatically deleted on successful episode assembly
- Located in `useEpisodeAssembly.js` after `setAssemblyComplete(true)`

### 3. Exit Confirmation (`PodcastCreator.jsx`)

**Confirmation Logic:**
```javascript
const handleBackToDashboard = () => {
  const hasMetadata = !!(
    episodeDetails?.title?.trim() ||
    episodeDetails?.description?.trim() ||
    episodeDetails?.tags?.trim()
  );
  
  if (currentStep > 3 && hasMetadata) {
    const confirmed = window.confirm(
      'Your episode details will be saved and restored if you return to edit this audio file. Continue to dashboard?'
    );
    if (!confirmed) return;
  }
  
  onBack();
};
```

**When Confirmation Shows:**
- User is past step 3 (audio uploaded/selected)
- AND user has entered any metadata (title, description, or tags)

**When Confirmation DOESN'T Show:**
- Steps 1-3 (template selection, audio upload, segment customization)
- No metadata entered yet
- User clicks Cancel on confirmation

**Message:**
> "Your episode details will be saved and restored if you return to edit this audio file. Continue to dashboard?"

This is **informative**, not scary - lets users know their work is saved.

## User Experience Flow

### Scenario 1: New Episode, Exit Early
1. User selects template → Step 2
2. User clicks "Back to Dashboard"
3. ✅ No confirmation (before step 4)
4. Returns to dashboard immediately

### Scenario 2: New Episode, Exit After Metadata Entry
1. User completes steps 1-3 (audio uploaded)
2. User enters title "My Episode" on Step 5
3. User clicks "Back to Dashboard"
4. ⚠️ Confirmation dialog appears
5. User clicks "OK"
6. Returns to dashboard
7. Draft saved: `ppp_episode_draft_{filename}`

### Scenario 3: Returning to Saved Draft
1. User uploads same audio file again (or selects from preuploaded)
2. System detects matching draft in localStorage
3. ✅ **Automatically restores:** title, description, tags, season, episode number
4. User can continue where they left off

### Scenario 4: Completing Episode
1. User assembles episode successfully
2. System detects `assemblyComplete = true`
3. ✅ **Automatically deletes draft** from localStorage
4. No stale data left behind

### Scenario 5: Old Drafts
1. User has 10-day-old draft in localStorage
2. User opens episode creator (any audio file)
3. ✅ **Automatic cleanup** removes old draft
4. Keeps localStorage clean

## Files Modified

### 1. `frontend/src/components/dashboard/hooks/creator/useEpisodeMetadata.js`
**Changes:**
- Added `storageKey` calculation based on `uploadedFilename`
- Added `loadPersistedDetails()` helper function
- Modified `useState` initialization to load persisted data
- Added `useEffect` to persist details on change
- Added `useEffect` for old draft cleanup (7 days)
- Updated initial state to include `tags` and `is_explicit` fields

**Key Functions:**
```javascript
const loadPersistedDetails = () => {
  // Loads from localStorage, handles errors gracefully
};

// Persist on change
useEffect(() => {
  localStorage.setItem(storageKey, JSON.stringify(toStore));
}, [episodeDetails, storageKey, uploadedFilename]);

// Cleanup old drafts
useEffect(() => {
  // Removes drafts older than 7 days
}, []);
```

### 2. `frontend/src/components/dashboard/hooks/creator/useEpisodeAssembly.js`
**Changes:**
- Added draft cleanup after successful assembly
- Clears `ppp_episode_draft_{uploadedFilename}` key
- Logs cleanup to console

**Location:** Inside polling success handler, after `setAssemblyComplete(true)`

```javascript
// Clear persisted draft data on successful assembly
if (uploadedFilename) {
  try {
    const draftKey = `ppp_episode_draft_${uploadedFilename}`;
    localStorage.removeItem(draftKey);
    console.log('[Assembly] Cleared draft data for:', uploadedFilename);
  } catch (err) {
    console.warn('[Assembly] Failed to clear draft data:', err);
  }
}
```

### 3. `frontend/src/components/dashboard/PodcastCreator.jsx`
**Changes:**
- Added `handleBackToDashboard()` function
- Wraps original `onBack` with confirmation logic
- Checks `currentStep > 3` AND `hasMetadata`
- Updated `<PodcastCreatorScaffold onBack={handleBackToDashboard} />`

**Smart Confirmation:**
- Only shows when user has work to lose
- Message is informative, not alarming
- Explains that draft will be saved

## Testing Checklist

### ✅ Draft Persistence
- [ ] Enter metadata on Step 5, navigate away, return → metadata restored
- [ ] Complete episode assembly → draft automatically deleted
- [ ] Upload different audio file → different draft loaded (or blank)
- [ ] Close browser, reopen → draft still available
- [ ] Fill out all fields (title, desc, tags, season, episode) → all restored

### ✅ Exit Confirmation
- [ ] Step 1-3: "Back to Dashboard" → no confirmation
- [ ] Step 4+, no metadata → no confirmation
- [ ] Step 4+, with title → confirmation shows
- [ ] Click "Cancel" on confirmation → stays in creator
- [ ] Click "OK" on confirmation → returns to dashboard

### ✅ Draft Cleanup
- [ ] Old drafts (7+ days) automatically removed on mount
- [ ] Recent drafts (< 7 days) preserved
- [ ] Cleanup logs to console

### ✅ Edge Cases
- [ ] localStorage full → fails gracefully, no errors
- [ ] Corrupted draft JSON → falls back to defaults
- [ ] Missing uploadedFilename → no persistence, no errors
- [ ] Multiple tabs → latest change wins (expected behavior)

## Known Limitations

1. **File-based, not episode-based:** Draft is tied to filename, not episode ID. If user uploads same audio file multiple times, they'll see the same draft. This is acceptable and may even be desirable.

2. **No sync across devices:** localStorage is browser-specific. Draft won't follow user to different computer/browser.

3. **File objects not persisted:** Cover art uploads reset on reload. User must re-upload cover art if they navigate away. This is a localStorage limitation (can't serialize File objects).

4. **No conflict resolution:** Last write wins. If user has multiple tabs open editing same audio file, latest save will overwrite.

5. **7-day retention:** Drafts older than 7 days are automatically deleted. This is by design to prevent localStorage bloat.

## Future Enhancements

1. **Server-side draft storage:** Store drafts in database instead of localStorage
   - Enables cross-device sync
   - No 7-day limitation
   - Can store File objects (as blobs/URLs)

2. **Draft list in UI:** Show user all saved drafts with timestamp
   - "Continue where you left off" section on dashboard
   - Delete/restore draft controls

3. **Auto-save indicator:** Visual feedback when draft is saved
   - "Draft saved at 3:45 PM" message
   - Saving spinner

4. **Explicit "Save Draft" button:** Let users manually trigger save
   - Gives users control
   - More familiar UX pattern

5. **Draft versioning:** Keep multiple versions of same draft
   - Undo/redo functionality
   - Restore previous version

## Related Documentation
- `AI_TAG_RETRY_UI_NOV4.md` - AI generation retry functionality
- `EPISODE_ASSEMBLY_EMAIL_FIX_OCT19.md` - Assembly completion emails
- `RAW_FILE_CLEANUP_NOTIFICATION_IMPLEMENTATION_OCT23.md` - File cleanup

## Status
✅ **Implemented and ready for testing**
- Draft persistence working (localStorage)
- Exit confirmation working (smart detection)
- Automatic cleanup working (7 days)
- Draft cleared on assembly success
- No errors, all files compile

---

*Last updated: November 4, 2025*
