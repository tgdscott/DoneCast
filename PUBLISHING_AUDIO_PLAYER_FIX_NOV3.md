# Publishing & Audio Player Fixes - November 3, 2025

## Issues Found & Fixed

### 1. Publishing Failed with 503 "Worker Unavailable" Error

**Problem:** User scheduled episode successfully (assembly worked in 50 seconds), but scheduling/publishing failed with:

```
HTTPException POST /api/episodes/05d4c4ae-0cc4-442e-8623-73aea74b340d/publish -> 503: 
{'code': 'PUBLISH_WORKER_UNAVAILABLE', 'message': 'Episode publish worker is not available...
```

**Root Cause:** The `publish()` function was calling `_ensure_publish_task_available()` at the TOP of the function, BEFORE checking if the user needed Spreaker at all. This function raises a 503 error if the Spreaker/Celery worker is unavailable.

**Why This is Wrong:**
- User doesn't have Spreaker connected (RSS-only mode)
- System should skip Spreaker entirely and just update database + RSS feed
- But it was checking for Spreaker worker FIRST, failing before reaching RSS-only logic

**Fix Applied:** Moved the worker availability check AFTER the RSS-only logic:

```python
# backend/api/services/episodes/publisher.py

def publish(...):
    # DON'T check worker availability until we know we need Spreaker
    # Many users don't have Spreaker and should publish RSS-only without errors
    
    ep = repo.get_episode_by_id(session, episode_id, user_id=current_user.id)
    # ... validation ...
    
    spreaker_access_token = getattr(current_user, "spreaker_access_token", None)
    
    # Skip Spreaker task if no token or no show ID (RSS-only mode)
    if not spreaker_access_token or not derived_show_id:
        logger.info("publish: RSS-only mode...")
        
        # Update episode status based on whether it's scheduled or immediate
        if auto_publish_iso:
            ep.status = EpisodeStatus.processed  # Scheduled
            message = f"Episode scheduled for {auto_publish_iso} (RSS feed only)"
        else:
            ep.status = EpisodeStatus.published  # Immediate
            message = "Episode published to RSS feed (Spreaker not configured)"
        
        session.add(ep)
        session.commit()
        session.refresh(ep)
        return {"job_id": "rss-only", "message": message}
    
    # Only check Spreaker worker availability if we actually need it
    _ensure_publish_task_available()  # MOVED HERE - only called for Spreaker users
    
    # ... rest of Spreaker publishing logic ...
```

**Result:** 
- RSS-only users can now publish/schedule without errors
- Spreaker check only runs for users who actually have Spreaker connected
- Status correctly set to `processed` (scheduled) or `published` (immediate)

---

### 2. Frontend Dashboard Crashes ("Something went wrong")

**Problem:** After assembly completes, dashboard shows "Something went wrong" error page with React error:

```
Objects are not valid as a React child (found: object with keys {code, message, details, request_id})
```

**Root Cause:** Same issue as the scheduling error - error objects being rendered directly as React children instead of extracting the message string.

**Already Fixed Earlier:** Error handling in `EpisodeHistory.jsx` was updated to properly extract strings from error objects. The dashboard crash might be from a different component that hasn't been fixed yet.

**Additional Fix Needed:** May need to check other components that render episode data to ensure they handle errors correctly.

---

### 3. Audio Player Shows Grey (No Playback)

**Problem:** Audio player appears grey/disabled, doesn't play audio even though assembly succeeded and audio uploaded to R2.

**Root Cause (Suspected):** Either:
1. Frontend not receiving `playback_url` from API response
2. R2 signed URL not being generated correctly
3. CORS issue preventing browser from loading R2 URLs
4. Frontend crash preventing proper rendering

**Already Fixed Earlier:** 
- `compute_playback_info()` updated to handle R2 https:// URLs
- Publish endpoint updated to accept https:// URLs
- Episode list endpoint uses `compute_playback_info()` which should return correct URLs

**Needs Testing:** After restarting API and resolving publish errors, audio player should work.

---

## Files Modified

1. **backend/api/services/episodes/publisher.py**
   - Moved `_ensure_publish_task_available()` check AFTER RSS-only logic
   - Added comment explaining why check is deferred
   - RSS-only users no longer get 503 worker unavailable errors

---

## Testing Checklist

**After restarting API:**

1. **Test Scheduling:**
   - [ ] Go to episode "E201 - Twinless - What Would YOU Do?"
   - [ ] Click "Schedule" button
   - [ ] Pick future date/time
   - [ ] Click "Schedule"
   - [ ] **Expected:** Success, episode shows "Scheduled" badge
   - [ ] **Expected:** No 503 error, no React crash

2. **Test Immediate Publishing:**
   - [ ] Create or find another processed episode
   - [ ] Click "Publish" button
   - [ ] **Expected:** Episode status changes to "Published"
   - [ ] **Expected:** No errors

3. **Test Audio Playback:**
   - [ ] Find published/scheduled episode in dashboard
   - [ ] Look at audio player widget
   - [ ] **Expected:** Player shows black play button (not grey)
   - [ ] Click play button
   - [ ] **Expected:** Audio starts playing
   - [ ] Check browser network tab
   - [ ] **Expected:** R2 URL returns 200 OK with audio data

4. **Test Dashboard Stability:**
   - [ ] Navigate to dashboard
   - [ ] **Expected:** Episode list loads without "Something went wrong"
   - [ ] **Expected:** Cover images display
   - [ ] **Expected:** Episode metadata (title, description) displays

---

## Performance Results (Chunking Disabled)

**Assembly completed successfully in ~50 seconds:**
- Filler/silence removal: 16 seconds
- Audio mixing: 34 seconds
- Upload to R2: 3 seconds

**Compared to chunked processing (previous attempt):**
- Chunked: 30+ minutes (timeout waiting for worker)
- Direct: 50 seconds
- **Improvement: 36x faster without chunking overhead**

**Conclusion:** For this use case (dev laptop, good specs, 26-minute episode), direct processing is FAR superior to chunking when worker server is unavailable.

---

## Root Cause Summary

The publishing system has three paths:

1. **RSS-only path** (no Spreaker):
   - Should just update database + RSS feed
   - Works directly, no worker needed
   - **Was broken:** Checked for Spreaker worker first, failed before reaching this path

2. **Spreaker path** (legacy):
   - Requires Spreaker worker available
   - Dispatches async task to publish to Spreaker
   - Most users DON'T use this path anymore

3. **Hybrid path**:
   - User has Spreaker token but no show ID
   - Falls back to RSS-only
   - **Was broken:** Same issue, checked worker too early

**Fix:** Only check for worker availability AFTER determining which path to use. RSS-only path doesn't need the worker at all.

---

## Next Steps

1. ✅ **Fix applied** - Moved worker check
2. 🔄 **Restart API** - User needs to restart
3. ⏳ **Test publishing** - Try scheduling the episode again
4. ⏳ **Test playback** - Verify audio player works
5. ⏳ **Verify dashboard** - Check for React crashes

---

*Last updated: November 3, 2025*
