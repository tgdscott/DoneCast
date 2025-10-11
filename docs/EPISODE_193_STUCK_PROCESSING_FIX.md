# Episode 193 Stuck Processing - Fix Summary

**Date**: October 7, 2025  
**Issue**: Episode 193 (29-minute audio) stuck in "Processing" status for 44+ minutes with no retry button

## Problem Analysis

### Timeline (from Cloud Run logs):
```
06:58:35 UTC - Assembly started
06:59:19 UTC - Word selection completed  
07:42:51 UTC - 404 error for cover image (193-square.jpg)
```

**Episode never completed** - No final assembly logs, no audio generated.

### Root Causes:

1. **Worker Stuck/Crashed**: Assembly process started but never finished
   - Likely timeout, memory exhaustion, or silent crash
   - No error logged to indicate what went wrong

2. **Retry Button Not Showing**: UI logic had multiple issues
   - Required `ep.duration_ms` which might not be set yet
   - Didn't account for "No audio" + "Processing" = definitely stuck
   - Thresholds too conservative for actual production issues

## Fixes Applied

### 1. Fixed Retry Button Logic (`EpisodeHistory.jsx`)

**Before:**
- Only showed retry after 1.25x duration (15min fallback)
- Relied on `duration_ms` being set

**After:**
- ✅ **Always shows retry** if `processing` + no audio
- ✅ Increased fallback to 20 minutes
- ✅ Added 30-minute absolute safeguard
- ✅ Catches stuck workers more reliably

**Changes:**
```javascript
// NEW: Always show retry if processing with no audio (likely stuck/failed)
if (st === 'processing' && !ep.final_audio_exists && !audioUrl) showRetry = true;

// Increased fallback from 15min to 20min
const durMs = (typeof ep.duration_ms === 'number' && ep.duration_ms > 0) 
  ? ep.duration_ms 
  : (20*60*1000); // was 15*60*1000

// NEW: Absolute 30min safeguard
if (elapsed > 30*60*1000) showRetry = true;
```

### 2. Committed and Pushed to Production

```bash
commit 84c0d211
"Fix: Show retry button for stuck processing episodes"
```

## How to Fix Episode 193 RIGHT NOW

### Option 1: Wait for Frontend Deploy (5-10 minutes)
1. Cloud Build will deploy the fix automatically
2. Hard refresh browser (Ctrl+F5)
3. Retry button should now appear on episode 193
4. Click it!

### Option 2: Use Manual Script (Immediate)
Run the provided script:
```bash
python d:\PodWebDeploy\retry_episode_193.py
```

You'll need to:
1. Get your auth token from browser DevTools
2. Paste it into the script
3. Script will trigger the retry via API

### Option 3: Browser DevTools (Advanced)
1. Open DevTools Console (F12)
2. Run:
```javascript
fetch('/api/episodes/193/retry', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${localStorage.getItem('ppp_token')}`,
    'Content-Type': 'application/json'
  },
  body: '{}'
}).then(r => r.json()).then(console.log)
```

## Prevention for Future

### Immediate Actions Needed:

1. **Better Assembly Logging**
   - Add more granular progress logs
   - Log each step: transcript → word selection → mixing → upload
   - Catch and log all exceptions

2. **Timeout Monitoring**
   - Add explicit timeouts for each assembly step
   - Auto-retry on timeout
   - Alert/notify on failures

3. **Health Checks**
   - Monitor Cloud Run worker health
   - Track average processing times
   - Alert if >2x expected duration

### Code Changes Recommended:

**File: `backend/worker/tasks.py` (or orchestrator)**
```python
# Add comprehensive try-catch and logging
import logging
logger = logging.getLogger(__name__)

def assemble_episode(episode_id, ...):
    try:
        logger.info(f"[assemble] Step 1: Loading transcript for {episode_id}")
        # ... transcript loading ...
        
        logger.info(f"[assemble] Step 2: Word selection")
        # ... word selection ...
        
        logger.info(f"[assemble] Step 3: Audio mixing")
        # ... mixing ...
        
        logger.info(f"[assemble] Step 4: Uploading to GCS")
        # ... upload ...
        
        logger.info(f"[assemble] ✅ COMPLETE for {episode_id}")
        
    except TimeoutError as e:
        logger.error(f"[assemble] ❌ TIMEOUT for {episode_id}: {e}")
        # Auto-retry or mark as error
        
    except Exception as e:
        logger.error(f"[assemble] ❌ ERROR for {episode_id}: {e}", exc_info=True)
        # Mark episode as error status
```

## What Probably Happened to Episode 193

Best guess based on logs:

1. ✅ Transcription completed
2. ✅ Word selection completed
3. ❌ **Audio mixing/assembly failed** (no log = silent failure)
4. Possible causes:
   - Memory exceeded during audio processing
   - GCS upload timeout/failure
   - Intro/outro download failed
   - Python exception not caught

The 404 for cover image is a **red herring** - that happens on every page load, not related to assembly failure.

## Next Steps

1. **Retry episode 193** using one of the methods above
2. **Monitor the retry** - check if it completes
3. **If it fails again**, we need to:
   - Check Cloud Run logs during processing
   - Look for memory/CPU issues
   - Possibly increase Cloud Run memory allocation

4. **After successful retry**, implement the logging improvements above

---

## Status: FIXED ✅

- [x] Retry button logic improved
- [x] Changes pushed to production
- [ ] Episode 193 retried (waiting for you!)
- [ ] Assembly logging improvements (future work)
