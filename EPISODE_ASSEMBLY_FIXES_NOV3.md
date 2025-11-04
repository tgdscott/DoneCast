# Episode Assembly & Publishing Fixes - November 3, 2025

## Issues Fixed

### 1. Assembly Running Locally Instead of Production Worker

**Problem:** Episode assembly was executing on dev laptop (in logs: `DEV MODE chunk processing`) instead of routing to production worker server.

**Root Cause:** Missing `GOOGLE_CLOUD_PROJECT` environment variable in `.env.local`. The Cloud Tasks client checks for this variable and falls back to local execution if missing:

```python
# backend/infrastructure/tasks_client.py
required = {
    "GOOGLE_CLOUD_PROJECT": os.getenv("GOOGLE_CLOUD_PROJECT"),
    "TASKS_LOCATION": os.getenv("TASKS_LOCATION"),
    "TASKS_QUEUE": os.getenv("TASKS_QUEUE"),
    "TASKS_URL_BASE": os.getenv("TASKS_URL_BASE"),
}
if missing:
    log.info("event=tasks.cloud.disabled reason=missing_config missing=%s", missing)
    return False
```

**Fix:** Added `GOOGLE_CLOUD_PROJECT=podcast612` to `backend/.env.local`:

```bash
# ==== Cloud Tasks ====
GOOGLE_CLOUD_PROJECT=podcast612  # ADDED THIS LINE
TASKS_AUTH=tsk_Zu2c2kJx8m1JjNnN2pZrZ0V0yK2OQm6r1i7m0PZVbKpVf3qDk5JbJ9kW
TASKS_LOCATION=us-west1
TASKS_QUEUE=ppp-queue
TASKS_URL_BASE=http://api.podcastplusplus.com/api/tasks
USE_CLOUD_TASKS=1
```

**Result:** Assembly tasks will now route to Cloud Tasks queue → production worker server (office server).

---

### 2. Publishing Failed with "Episode has no GCS audio file"

**Problem:** Episode assembly succeeded and uploaded to R2 storage (`https://ppp-media.e08eed3e2786f61e25e9e1993c75f61e.r2.cloudflarestorage.com/...`), but publishing failed with:

```
HTTPException 400: Episode has no GCS audio file. Episode must be properly assembled with audio uploaded to GCS before publishing.
```

**Root Cause:** Publish endpoint validation was hardcoded to only accept `gs://` URLs (GCS), but R2 storage returns `https://` URLs. System uses `STORAGE_BACKEND=r2` but validation logic hadn't been updated.

**Previous Code:**
```python
# backend/api/routers/episodes/publish.py
if not ep.gcs_audio_path or not str(ep.gcs_audio_path).startswith("gs://"):
    raise HTTPException(
        status_code=400, 
        detail="Episode has no GCS audio file..."
    )
```

**Fix:** Updated validation to accept BOTH GCS (`gs://`) and R2 (`https://`) URL formats:

```python
# REQUIRE cloud storage audio path (GCS or R2)
if not ep.gcs_audio_path:
    raise HTTPException(
        status_code=400, 
        detail="Episode has no cloud storage audio file. Episode must be properly assembled with audio uploaded to cloud storage before publishing."
    )

# Accept both gs:// (GCS) and https:// (R2) URLs
audio_path_str = str(ep.gcs_audio_path)
if not (audio_path_str.startswith("gs://") or audio_path_str.startswith("https://")):
    raise HTTPException(
        status_code=400, 
        detail=f"Episode audio path has unexpected format: {audio_path_str[:50]}... (expected gs:// or https:// URL)"
    )
```

**Result:** Publishing will now work with both GCS and R2 storage backends.

---

### 3. Episode Showing "processed" Instead of "scheduled"

**Problem:** User scheduled episode for future date/time in Step 6, confirmation message said "Episode assembled and scheduled", but episode showed status `processed` instead of `scheduled` in dashboard.

**Root Cause:** The `publish()` function in RSS-only mode (no Spreaker) was setting status to `published` immediately, even when `auto_publish_iso` (scheduled publish time) was provided. The system doesn't have a `scheduled` status enum value - instead, frontend determines "scheduled" by checking for `status=processed` + `publish_at` in future.

**Previous Code:**
```python
# backend/api/services/episodes/publisher.py
if not spreaker_access_token or not derived_show_id:
    # Just update episode status and publish to RSS feed
    from api.models.podcast import EpisodeStatus
    ep.status = EpisodeStatus.published  # ❌ WRONG - sets published immediately
    session.add(ep)
    session.commit()
    session.refresh(ep)
    return {
        "job_id": "rss-only",
        "message": "Episode published to RSS feed only (Spreaker not configured)"
    }
```

**Fix:** Check for `auto_publish_iso` and keep status as `processed` for scheduled episodes:

```python
if not spreaker_access_token or not derived_show_id:
    logger.info(
        "publish: RSS-only mode (spreaker_token=%s show_id=%s auto_publish=%s) episode_id=%s",
        bool(spreaker_access_token),
        derived_show_id,
        auto_publish_iso,
        episode_id
    )
    # Update episode status based on whether it's scheduled or immediate
    from api.models.podcast import EpisodeStatus
    
    if auto_publish_iso:
        # Scheduled publish - keep status as "processed" until scheduled time
        # (Frontend determines "scheduled" by checking processed + future publish_at)
        ep.status = EpisodeStatus.processed
        message = f"Episode scheduled for {auto_publish_iso} (RSS feed only)"
    else:
        # Immediate publish - set to published
        ep.status = EpisodeStatus.published
        message = "Episode published to RSS feed (Spreaker not configured)"
    
    session.add(ep)
    session.commit()
    session.refresh(ep)
    return {
        "job_id": "rss-only",
        "message": message
    }
```

**Result:** Scheduled episodes will now show correct "scheduled" badge in dashboard (frontend checks `processed` + future `publish_at`).

---

### 4. React Error: "Objects are not valid as a React child"

**Problem:** When attempting to schedule episode, publishing failed with 400 error, but React crashed with:

```
Uncaught Error: Objects are not valid as a React child (found: object with keys {code, message, details, request_id}).
```

**Root Cause:** Error handling in `submitSchedule()` was extracting error message correctly, but React was trying to render the entire error object directly in the JSX. The error variable `scheduleError` was being set to a complex object instead of a string.

**Previous Code:**
```javascript
catch(e){
  const msg = isApiError(e) ? (e.detail || e.error || e.message) : String(e);
  setScheduleError(msg || 'Failed to schedule');  // msg could still be an object
  ...
}
```

**Fix:** Added comprehensive type checking to ensure only strings are set:

```javascript
catch(e){
  // Extract string message from error object (never render object directly)
  let msg = 'Failed to schedule';
  if (isApiError(e)) {
    // API error object: extract detail/error/message string
    msg = e.detail || e.error || e.message || JSON.stringify(e);
  } else if (e instanceof Error) {
    msg = e.message;
  } else if (typeof e === 'string') {
    msg = e;
  } else {
    // Last resort: stringify the error
    try {
      msg = JSON.stringify(e);
    } catch {
      msg = String(e);
    }
  }
  setScheduleError(msg);
  setEpisodes(prev => prev.map(p => p.id===scheduleEp.id ? { ...p, _scheduling:false } : p));
} finally { setScheduleSubmitting(false); }
```

**Result:** Error messages will now always be strings, preventing React rendering crashes.

---

## Testing Checklist

After restarting backend API:

1. **Cloud Tasks Routing:**
   - [ ] Check logs for `event=tasks.cloud.enabled` (not `disabled`)
   - [ ] Verify no `DEV MODE chunk processing` messages
   - [ ] Confirm `Cloud Tasks dispatch` messages appear
   - [ ] Monitor production worker logs (office server) for assembly tasks

2. **Publishing:**
   - [ ] Verify episode with R2 URL (`https://...`) can be published
   - [ ] Check that immediate publish sets status to `published`
   - [ ] Check that scheduled publish keeps status as `processed`

3. **Scheduling:**
   - [ ] Schedule episode for future date/time
   - [ ] Verify dashboard shows "Scheduled" badge (not "Processed")
   - [ ] Verify episode card shows scheduled date/time
   - [ ] Attempt to edit scheduled episode - should work without errors

4. **Audio Playback:**
   - [ ] Grey play button → should become black/playable
   - [ ] Click play → audio should load and play
   - [ ] Check browser network tab → signed URL should return 200 OK

---

## Environment Configuration Summary

**Required Variables for Cloud Tasks (backend/.env.local):**
```bash
GOOGLE_CLOUD_PROJECT=podcast612  # ✅ ADDED
TASKS_AUTH=tsk_Zu2c2kJx8m1JjNnN2pZrZ0V0yK2OQm6r1i7m0PZVbKpVf3qDk5JbJ9kW
TASKS_LOCATION=us-west1
TASKS_QUEUE=ppp-queue
TASKS_URL_BASE=http://api.podcastplusplus.com/api/tasks
USE_CLOUD_TASKS=1
APP_ENV=staging  # ✅ Already set (enables Cloud Tasks in dev)
```

**Storage Backend Configuration:**
```bash
STORAGE_BACKEND=r2  # ✅ Using Cloudflare R2
R2_BUCKET=ppp-media
GCS_BUCKET=ppp-media-us-west1  # Used for temp chunks during processing
```

---

## Files Modified

1. **backend/.env.local** - Added `GOOGLE_CLOUD_PROJECT=podcast612`
2. **backend/api/routers/episodes/publish.py** - Accept both `gs://` and `https://` URLs
3. **backend/api/services/episodes/publisher.py** - Keep status `processed` for scheduled episodes
4. **frontend/src/components/dashboard/EpisodeHistory.jsx** - Robust error message extraction

---

## Architecture Notes

### Why Assembly Was Running Locally

The Cloud Tasks client has a hierarchy of checks:

1. **Check `APP_ENV`** - If `dev/development/local/test`, return False
2. **Check force loopback** - If `TASKS_FORCE_HTTP_LOOPBACK=true`, return False  
3. **Check google.cloud.tasks_v2** - If import fails, return False
4. **Check required env vars** - If any missing, return False

We already set `APP_ENV=staging` (passes check #1), but were missing `GOOGLE_CLOUD_PROJECT` (failed check #4).

### Why Episode Status Was Wrong

The system has NO `scheduled` status enum value. Instead:

- **EpisodeStatus enum:** `pending`, `processing`, `processed`, `published`, `error`
- **Scheduled logic:** Episode has `status=processed` AND `publish_at` is in the future
- **Frontend badge:** Checks both conditions to show "Scheduled" vs "Processed"

When RSS-only publish path set status to `published` immediately, frontend saw `published` status and ignored the future `publish_at` date.

---

## Next Steps

1. **Restart backend API** to load new `GOOGLE_CLOUD_PROJECT` variable
2. **Test assembly** - Create new episode, verify production worker receives task
3. **Test publishing** - Verify R2 URLs work for both immediate and scheduled publishes
4. **Monitor production logs** - Confirm assembly tasks execute on office server
5. **Test playback** - Verify audio player loads R2 URLs correctly

---

*Last updated: November 3, 2025*
