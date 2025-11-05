# Dashboard "Assemble New Episode" Button Missing - November 4, 2025

## Problem
The "Assemble New Episode" button (green button) was not appearing on the dashboard even when preuploaded audio files with ready transcripts existed. Users had to click "Record or Upload Audio" and then navigate back to dashboard to see the button appear.

## Root Cause
The dashboard component had logic to display the "Assemble New Episode" button conditionally:

```javascript
{preuploadItems.some((item) => item?.transcript_ready) && (
  <Button variant="green">
    <Library className="w-4 h-4 mr-2" />
    Assemble New Episode
  </Button>
)}
```

However, `preuploadItems` state was initialized as an empty array and **never fetched on dashboard mount**. The only places that triggered `refreshPreuploads()` were:

1. When clicking "Record or Upload Audio" button
2. When navigating to specific views (episodeStart, preuploadUpload, createEpisode)
3. Polling (but only if items already existed)

This meant the dashboard had no way to know about existing preuploaded files until the user navigated through the creator flow.

## Solution
Added a new `useEffect` hook to fetch preuploaded items when the dashboard first loads:

```javascript
// Initial fetch of preuploaded items when dashboard loads
useEffect(() => {
  if (token && currentView === 'dashboard' && !preuploadFetchedOnceRef.current) {
    refreshPreuploads();
  }
}, [token, currentView, refreshPreuploads]);
```

**Key features:**
- Runs when dashboard view loads
- Only runs once (tracked by `preuploadFetchedOnceRef`)
- Respects authentication (requires token)
- Uses existing `refreshPreuploads()` function (no new logic)

## User Experience Impact

**Before:**
1. User has preuploaded audio with ready transcript
2. Visits dashboard → only sees "Record or Upload Audio" (red button)
3. Clicks "Record or Upload Audio"
4. Navigates back to dashboard
5. NOW sees "Assemble New Episode" (green button)

**After:**
1. User has preuploaded audio with ready transcript
2. Visits dashboard → **immediately sees both buttons:**
   - "Record or Upload Audio" (red button with mic icon)
   - "Assemble New Episode" (green button with library icon) ✅
3. Can click green button directly to start assembling

## Technical Details

### File Modified
`frontend/src/components/dashboard.jsx`

### Change Location
Added new useEffect hook after the existing "When navigating back to Dashboard" useEffect, before the polling useEffect.

### Existing Infrastructure Used
- `refreshPreuploads()` - Existing function that fetches `/api/media/main-content`
- `preuploadFetchedOnceRef` - Existing ref to prevent duplicate fetches
- `preuploadItems` - Existing state array
- Button visibility condition unchanged (still checks `preuploadItems.some((item) => item?.transcript_ready)`)

### Related Code
The polling logic (5-second intervals) still runs when:
- On dashboard view
- Has items that are processing (not transcript_ready yet)

This polling will now work correctly because `preuploadItems` will be populated on mount.

## Testing Checklist

### ✅ Green Button Visibility
- [ ] Upload audio file, wait for transcript → Navigate to dashboard → Green button appears immediately
- [ ] No preuploaded files → Dashboard shows only red button
- [ ] Preuploaded file still processing → Red button only (green appears when transcript ready)
- [ ] Multiple preuploaded files, one ready → Green button appears

### ✅ Button Functionality
- [ ] Click green "Assemble New Episode" → Goes to preuploaded selector (Step 2)
- [ ] Click red "Record or Upload Audio" → Goes to record/upload choice screen
- [ ] Green button takes user directly to episode assembly flow

### ✅ Performance
- [ ] Dashboard loads without noticeable delay
- [ ] Network tab shows single `/api/media/main-content` request on mount
- [ ] No duplicate fetches on initial load
- [ ] Polling continues correctly (5s intervals) if files are processing

### ✅ Edge Cases
- [ ] No token → No fetch attempted
- [ ] Token expires mid-session → Handles gracefully (already handled by `refreshPreuploads()`)
- [ ] Network error on fetch → Fails silently (already handled)
- [ ] Navigate away and back → Uses cached data (preuploadFetchedOnceRef)

## Related Components

### Preupload Management
- `refreshPreuploads()` - Fetches main content audio files
- `requestPreuploadRefresh()` - Resets fetch flag and calls refresh
- `resetPreuploadFetchedFlag()` - Clears the once-only flag

### Button Rendering
Located in dashboard default case, "Create Episode" card:
```javascript
<Button variant="default">Record or Upload Audio</Button>
{preuploadItems.some((item) => item?.transcript_ready) && (
  <Button variant="green">Assemble New Episode</Button>
)}
```

### API Endpoint
- `GET /api/media/main-content` - Returns array of uploaded audio files with metadata
- Response includes `transcript_ready` boolean flag

## Why This Bug Existed
The two-button interface was added in a previous update (see `EPISODE_INTERFACE_SEPARATION_OCT19.md`), but the initial fetch logic wasn't added at that time. The assumption was that the polling logic would handle it, but polling only runs when `preuploadItems.length > 0`, creating a chicken-and-egg problem.

## Future Improvements

1. **Loading State:** Show spinner while fetching preuploaded items on first load
2. **Error State:** Display error message if fetch fails (currently silent)
3. **Badge Count:** Show number of ready files on green button ("3 files ready")
4. **Smart Polling:** Increase polling interval (10s, 30s) when files take longer
5. **WebSocket Updates:** Real-time updates when transcripts complete (no polling needed)

## Status
✅ **Fixed and ready for testing**
- Initial fetch now runs on dashboard mount
- Green button appears immediately when ready files exist
- No duplicate fetches (tracked by ref)
- Uses existing infrastructure (no new APIs)

---

*Last updated: November 4, 2025*
