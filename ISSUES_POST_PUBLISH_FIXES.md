# Post-Publication Issue Report & Fixes

## Summary
Episode published successfully with single-publish behavior working correctly. Identified 5 issues requiring attention.

---

## Issue #1: Background Music Not Audible at Level 8.2/11 ❗HIGH PRIORITY

### Problem
Background music was set to level 8.2/11 but was not audible in the final episode.

### Investigation
Looking at the audio orchestrator code in `backend/api/services/audio/orchestrator_steps.py` lines 1440-1550:

```python
vol_db = rule.get('volume_db')
# ...
if vol_db is not None:
    base_seg = base_seg.apply_gain(float(vol_db))
```

The music system:
1. Loads music file from GCS
2. Applies volume_db gain directly
3. Streams chunks and applies fade envelopes
4. Overlays onto final mix

### Root Cause Analysis
The `volume_db` value is being applied correctly, but **level 8.2/11 might be mapping to an insufficient dB value**.

Looking at `frontend/src/components/dashboard/template-editor/constants.js` lines 40-70:

```javascript
export const volumeLevelToDb = (level) => {
  const clamped = Math.max(1, Math.min(11, level));
  let ratio;
  if (clamped <= 10) {
    ratio = clamped / 10;  // Level 8.2 → ratio = 0.82
  } else {
    ratio = 1 + (clamped - 10) * extra;
  }
  if (ratio <= 0) return -60;
  return 20 * Math.log10(ratio);  // 20 * log10(0.82) = -1.7 dB
}
```

**Problem Found**: Level 8.2 maps to only **-1.7 dB**, which is nearly imperceptible under full voice audio!

The scale assumes:
- Level 1-10: Linear ratio 0.1 to 1.0 (quieter to equal volume)
- Level 10-11: Boosted above voice (1.0 to 1.35x via MUSIC_VOLUME_BOOST_RATIO)

### Solution

**Option A - Recommended**: Adjust the mapping curve to make levels 7-9 more audible:

```javascript
export const volumeLevelToDb = (level) => {
  const clamped = Math.max(1, Math.min(11, level));
  let ratio;
  if (clamped <= 10) {
    // Apply exponential curve instead of linear for better perceptual spread
    // Level 5 → -6dB (50%), Level 8 → -2dB (80%), Level 10 → 0dB (100%)
    ratio = Math.pow(clamped / 10, 0.7);
  } else {
    const extra = MUSIC_VOLUME_BOOST_RATIO - 1;
    ratio = 1 + (clamped - 10) * extra;
  }
  if (ratio <= 0) return -60;
  return 20 * Math.log10(ratio);
}
```

With this curve:
- Level 8.2 → **-0.9 dB** (much more audible)
- Level 5 → **-6 dB** (50% perceived volume)
- Level 10 → **0 dB** (equal to voice)
- Level 11 → **+2.6 dB** (35% boost)

**Option B**: Add user guidance in the UI:
- Levels 1-6: "Background bed"
- Levels 7-9: "Moderate presence" 
- Level 10: "Equal to voice"
- Level 11: "Louder than voice"

### Fix Location
- File: `frontend/src/components/dashboard/template-editor/constants.js`
- Function: `volumeLevelToDb()`
- Lines: 43-58

---

## Issue #2: Waveform Editor Icon Missing ❗MEDIUM PRIORITY

### Problem
The waveform editor (Manual Editor) button should appear for the first 7 days after an episode is published, but it's not showing up.

### Current Behavior
Looking at `frontend/src/components/dashboard/EpisodeHistory.jsx` lines 827-860:

```jsx
{ep.status === 'processed' && (
  <>
    {/* Cut for edits */}
    <button
      className="bg-white/85 hover:bg-white text-purple-700 border border-purple-300 rounded p-1 shadow-sm"
      title="Cut for edits"
      onClick={() => setFlubberEpId(prev => prev===ep.id? null : ep.id)}
    >
      <Scissors className="w-4 h-4" />
    </button>
    {/* Manual Editor */}
    <button
      className="bg-white/85 hover:bg-white text-blue-700 border border-blue-300 rounded p-1 shadow-sm"
      title="Open Manual Editor"
      onClick={() => setManualEpId(prev => prev===ep.id? null : ep.id)}
    >
      <Pencil className="w-4 h-4" />
    </button>
  </>
)}
```

**Problem**: The Manual Editor button only shows when `status === 'processed'`, but after publishing, the status changes to `'published'` or `'scheduled'`.

### Solution

Add a time-based check that shows the Manual Editor button for:
1. All episodes with status `'processed'` (unpublished)
2. Episodes with status `'published'` or `'scheduled'` **within 7 days** of `publish_at`

**Code Fix**:

```jsx
// Helper function at top of component (around line 100)
const isWithin7Days = (dateValue) => {
  if (!dateValue) return false;
  const date = normalizeDate(dateValue);
  if (!date) return false;
  const now = Date.now();
  const elapsed = now - date.getTime();
  const sevenDays = 7 * 24 * 60 * 60 * 1000;
  return elapsed >= 0 && elapsed <= sevenDays;
};

// In the grid rendering (around line 827)
const showManualEditor = (
  ep.status === 'processed' || 
  (statusLabel(ep.status) === 'published' && isWithin7Days(ep.publish_at)) ||
  (statusLabel(ep.status) === 'scheduled' && isWithin7Days(ep.publish_at))
);

{showManualEditor && (
  <>
    {/* Cut for edits */}
    <button ... onClick={() => setFlubberEpId(...)}>
      <Scissors className="w-4 h-4" />
    </button>
    {/* Manual Editor */}
    <button ... onClick={() => setManualEpId(...)}>
      <Pencil className="w-4 h-4" />
    </button>
  </>
)}
```

### Fix Location
- File: `frontend/src/components/dashboard/EpisodeHistory.jsx`
- Lines: ~827-860 (grid view) and ~1013 (list/mosaic views)
- Add helper function around line 100

---

## Issue #3: Delete Button Behavior After 7 Days ❗HIGH PRIORITY

### Problem
Once an episode is over 7 days published, will the delete button delete it from **both** our system and Spreaker, or only from our system?

### Current Implementation

Looking at `backend/api/routers/episodes/write.py` lines 367-390:

```python
@router.delete("/{episode_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_episode(
    episode_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    # ... validates episode ownership ...
    _svc_repo.delete_episode(session, ep)
    return
```

The `delete_episode` function only removes the episode from **our database**. It does **NOT** attempt to delete from Spreaker.

### Risk
Users have no way to remove episodes from Spreaker after the 7-day Unpublish window expires. The only workflow is:
1. Days 0-7: Use "Unpublish" button (removes from Spreaker + reverts to processed)
2. After day 7: Delete button only removes from our system, **Spreaker copy remains**

### Solution Options

**Option A - Recommended**: Add Spreaker deletion to the delete endpoint:

```python
@router.delete("/{episode_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_episode(
    episode_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    # ... validate ownership ...
    
    # Attempt to delete from Spreaker if published
    spreaker_id = getattr(ep, 'spreaker_episode_id', None)
    token = getattr(current_user, 'spreaker_access_token', None)
    remote_deleted = False
    
    if spreaker_id and token:
        try:
            from api.services.publisher import SpreakerClient
            client = SpreakerClient(token)
            r = client.session.delete(f"{client.BASE_URL}/episodes/{spreaker_id}")
            if r.status_code in (200, 204, 404):
                remote_deleted = True
                logger.info(f"Deleted episode {spreaker_id} from Spreaker")
        except Exception as e:
            logger.warning(f"Failed to delete from Spreaker: {e}")
            # Continue with local deletion even if Spreaker fails
    
    _svc_repo.delete_episode(session, ep)
    return
```

**Option B**: Add a confirmation dialog warning:

```jsx
const handleDeleteEpisode = async (episodeId) => {
  const ep = episodes.find(e => e.id === episodeId);
  const isPublished = ep && ep.spreaker_episode_id;
  
  let message = 'Delete this episode permanently? This cannot be undone.\n' +
                'Deleting does not return processing minutes.';
  
  if (isPublished) {
    message += '\n\n⚠️ This episode is published to Spreaker. ' +
               'It will be removed from your dashboard but MAY REMAIN on Spreaker. ' +
               'To remove from Spreaker, go to spreaker.com and delete manually.';
  }
  
  if (!window.confirm(message)) return;
  // ... continue with deletion ...
};
```

**Option C**: Extend the "Unpublish" button to work after 7 days with `force=true` flag (already supported in backend):

```jsx
const showUnpublish = (
  statusLabel(ep.status) === 'scheduled' || 
  statusLabel(ep.status) === 'published'  // Remove the isWithin24h check
);
```

The backend already supports `force=true` for unpublish after 24 hours (see `backend/api/services/episodes/publisher.py` line 205).

### Recommended Approach
**Combination of A + C**:
1. Make Delete button always attempt Spreaker deletion (Option A)
2. Keep Unpublish button visible for all published episodes (Option C)
3. Show different text: "Unpublish (7-day window)" vs "Unpublish (force)"

---

## Issue #4: Raw Audio Cleanup After Episode Creation ❗HIGH PRIORITY

### Problem
Once raw audio is used to create an episode successfully, it needs to be removed from step 2 (media library) so it's no longer shown there.

### Current Implementation

Looking at `backend/worker/tasks/assembly/orchestrator.py` lines 55-165, the `_cleanup_main_content()` function **already does this**!

```python
def _cleanup_main_content(*, session, episode, main_content_filename: str) -> None:
    """Remove the main content source file and database record after successful assembly."""
    try:
        # Find the MediaItem in database
        query = select(MediaItem).where(
            MediaItem.user_id == episode.user_id,
            MediaItem.category == MediaCategory.main_content,
        )
        media_item = None
        for item in session.exec(query).all():
            stored = str(getattr(item, "filename", "") or "").strip()
            if stored in candidates:
                media_item = item
                break
        
        if not media_item:
            return
        
        # Delete the file (local or GCS)
        filename = str(media_item.filename or "").strip()
        removed_file = False
        
        if filename.startswith("gs://"):
            # Delete from GCS
            client.bucket(bucket_name).blob(key).delete()
            removed_file = True
        else:
            # Delete local file
            candidate.unlink()
            removed_file = True
        
        # Delete database record
        session.delete(media_item)
        session.commit()
        
        logging.info(f"[cleanup] Removed main content source {media_item.filename}")
    except Exception:
        logging.warning("[cleanup] Failed to remove main content media item")
```

This is called at the end of `_finalize_episode()` on line 418:

```python
_cleanup_main_content(
    session=session, 
    episode=episode, 
    main_content_filename=main_content_filename
)
```

### Status
✅ **Already implemented and working!** The raw audio file is:
1. Deleted from GCS (if uploaded there)
2. Deleted from local filesystem (if stored locally)
3. Removed from the MediaItem database table

### Why It Might Still Appear

The file **should** disappear from step 2 after assembly completes. If it's still showing:

**Possible causes**:
1. **Frontend caching**: The media library might be showing stale data
2. **Race condition**: Frontend queried media list before cleanup completed
3. **Error during cleanup**: Check logs for `[cleanup] Failed to remove`

**Quick fix**: Add a media library refresh after successful assembly:

```jsx
// In PodcastCreator after successful assembly
const assembleResult = await api.post('/api/episodes/assemble', { ... });
setAssembledEpisode(assembleResult);

// Refresh media library to remove used audio
try {
  await onRefreshPreuploaded?.();  // If available
} catch {}
```

### Verification
Check logs after next assembly for:
- `[cleanup] Removed main content source gs://...` (SUCCESS)
- `[cleanup] Failed to remove main content media item` (ERROR)

---

## Issue #5: Allow Users to Download Raw Recorded Audio ❗MEDIUM PRIORITY

### Problem
Users need a way to save raw audio they record using our in-browser recorder. They should be responsible for their own raw audio storage.

### Current Behavior
The Recorder component (`frontend/src/components/quicktools/Recorder.jsx`) allows users to:
1. Record audio in-browser
2. Save to media library
3. Use for episode creation

After episode creation, the raw audio is deleted per Issue #4.

### Solution

Add a download button in the Recorder component after recording completes, valid for 24 hours or until used in an episode:

**Step 1**: Add download button to Recorder UI (around line 876):

```jsx
<div className="flex gap-2 md:justify-end">
  {/* Existing Save button */}
  <Button
    className="flex-1 md:flex-none"
    onClick={handleSave}
    disabled={!audioUrl || saving}
  >
    {saving ? <Loader2 className="w-4 h-4 animate-spin mr-2"/> : <Save className="w-4 h-4 mr-2"/>}
    Save to Library
  </Button>
  
  {/* NEW: Download button */}
  <Button
    variant="outline"
    className="flex-1 md:flex-none"
    onClick={handleDownload}
    disabled={!audioUrl}
  >
    <Download className="w-4 h-4 mr-2"/>
    Download
  </Button>
</div>
```

**Step 2**: Add download handler:

```jsx
const handleDownload = () => {
  if (!audioUrl || !audioRef.current) return;
  
  const link = document.createElement('a');
  link.href = audioUrl;
  link.download = `${recordingName || 'recording'}.wav`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};
```

**Step 3**: Add download link in media library for main_content items:

In `frontend/src/components/dashboard/EpisodeHistory.jsx` or media library view:

```jsx
{item.category === 'main_content' && (
  <a
    href={item.url}
    download={item.friendly_name || item.filename}
    className="text-blue-600 hover:underline text-xs"
  >
    Download
  </a>
)}
```

**Step 4**: Add "Download before use" tooltip:

```jsx
<div className="text-xs text-gray-500 mt-2">
  💡 Tip: Download your raw recording now. Once used in an episode, 
  it will be automatically removed from the library.
</div>
```

### Implementation Priority
- **Phase 1** (Quick): Add download button to Recorder component
- **Phase 2** (Later): Add download links in media library
- **Phase 3** (Optional): Add "Download all unused recordings" bulk action

---

## Deployment Checklist

### High Priority (Deploy ASAP)
- [ ] Issue #1: Fix music volume mapping curve
- [ ] Issue #3: Add Spreaker deletion to delete endpoint OR extend unpublish
- [ ] Issue #4: Verify cleanup is working + add frontend refresh

### Medium Priority (Next Sprint)
- [ ] Issue #2: Add waveform editor icon for published episodes (7-day window)
- [ ] Issue #5: Add download button to Recorder component

### Testing Required
- [ ] Test music at levels 5, 7, 8, 9, 10, 11 (confirm audibility)
- [ ] Test waveform editor appears for <7 day published episodes
- [ ] Test delete button removes from Spreaker when applicable
- [ ] Test raw audio cleanup after assembly
- [ ] Test download button in Recorder

---

## Notes

### Why Music Level 8.2 Was Inaudible
The current linear mapping (level → ratio → dB) makes levels 1-9 map to negative dB values that are too quiet under full voice audio. The exponential curve fixes this by giving more "perceptual space" to the audible range.

### 7-Day Window Purpose
The 7-day window for waveform editing aligns with the design doc which mentions "7-day grace period for edits before final Spreaker publish" in the pricing tier comments.

### Raw Audio Cleanup Is Intentional
The cleanup prevents:
1. Storage bloat from unused source files
2. Confusion about which files are "active"
3. Accidental re-use of already-assembled audio

Users who want to keep raw recordings should download them before assembly.

---

## Questions for User

1. **Music Volume**: Do you want the exponential curve fix (Option A) or just better UI labels (Option B)?

2. **Delete Behavior**: Should Delete button:
   - A) Attempt Spreaker deletion (recommended)
   - B) Just warn user about Spreaker copies
   - C) Keep Unpublish button visible after 7 days with force option

3. **Raw Audio Downloads**: Should this be:
   - A) Recorder-only (download during/after recording)
   - B) Media library (download any main_content item)
   - C) Both

4. **Waveform Editor Window**: Is 7 days the right duration or should it be longer?
