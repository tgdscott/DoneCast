# GCS-ONLY ARCHITECTURE - Critical System Change - October 13, 2025

## MISSION CRITICAL CHANGE

**GCS (Google Cloud Storage) is now the SOLE source of truth for ALL media files. Period.**

## What Changed

### 1. NO MORE FALLBACKS
- If GCS upload fails → **Episode assembly FAILS**
- No "will rely on local files" warnings
- No automatic fallback to Spreaker
- No tolerance for GCS errors

### 2. NO MORE LOCAL FILE DEPENDENCIES
- Local files are NO LONGER checked as audio sources
- `final_audio_path` is kept for backwards compatibility but NOT used for playback
- Production containers don't persist local files anyway
- Dev environment must use GCS or fail

### 3. SPREAKER IS LEGACY ONLY
- New episodes: **NEVER touch Spreaker**
- Old/imported episodes: Keep Spreaker stream URL as fallback ONLY
- `spreaker_episode_id` preserved only for legacy playback
- Publishing to Spreaker is deprecated (kept for transition period)

## Code Changes

### Assembly Orchestrator (`backend/worker/tasks/assembly/orchestrator.py`)

**Before:**
```python
try:
    gcs_audio_url = gcs.upload_fileobj(...)
    episode.gcs_audio_path = gcs_audio_url
except Exception:
    logging.warning("Failed to upload audio to GCS (will rely on local files)")
```

**After:**
```python
# Upload to GCS - if this fails, the entire assembly fails
try:
    gcs_audio_url = gcs.upload_fileobj(...)
except Exception as gcs_err:
    raise RuntimeError(f"CRITICAL: Failed to upload audio to GCS. Episode assembly cannot complete.") from gcs_err

if not gcs_audio_url or not str(gcs_audio_url).startswith("gs://"):
    raise RuntimeError(f"CRITICAL: GCS upload returned invalid URL: {gcs_audio_url}")

episode.gcs_audio_path = gcs_audio_url
```

**Impact:** Assembly STOPS if GCS fails. No half-baked episodes.

### Playback Resolution (`backend/api/routers/episodes/common.py`)

**Before:**
```python
# Priority 1: Check GCS URL
# Priority 2: Check local file (dev mode)  ← REMOVED
# Priority 3: Spreaker stream URL
```

**After:**
```python
# Priority 1: GCS URL - THE ONLY SOURCE FOR NEW EPISODES
# Priority 2: Spreaker stream URL - LEGACY ONLY (for old imported episodes)
```

**Removed:**
- All local file checking logic
- `_local_final_candidates()` calls
- `local_final_exists` variable (replaced with `gcs_exists`)
- Complex grace period logic (deprecated)

**Impact:** Episode playback ONLY works if GCS URL exists OR legacy Spreaker stream exists.

### Publishing Endpoint (`backend/api/routers/episodes/publish.py`)

**Before:**
```python
if not ep.final_audio_path:
    raise HTTPException(status_code=400, detail="Episode is not processed yet")
```

**After:**
```python
if not ep.gcs_audio_path or not str(ep.gcs_audio_path).startswith("gs://"):
    raise HTTPException(
        status_code=400, 
        detail="Episode has no GCS audio file. Local files and Spreaker-only episodes are no longer supported."
    )
```

**Impact:** Cannot publish without GCS audio. Period.

### Frontend Edit Restrictions (`frontend/src/components/dashboard/EpisodeHistory.jsx`)

**Before:**
```jsx
{(ep.status === 'processed' || 
  (statusLabel(ep.status) === 'published' && isWithin7Days(ep.publish_at)) ||
  (statusLabel(ep.status) === 'scheduled' && isWithin7Days(ep.publish_at))) && (
```

**After:**
```jsx
{(ep.status === 'processed' || 
  statusLabel(ep.status) === 'published' ||
  statusLabel(ep.status) === 'scheduled') && (
```

**Impact:** Can edit scheduled episodes at ANY time, not just within 7 days of publish.

## Why This Change

### The Problem
1. **Reliance on Spreaker:** Unscheduling episodes cleared `spreaker_episode_id`, removing audio fallback
2. **Container Restarts:** Local files disappeared, breaking episodes
3. **Inconsistent State:** GCS might fail, episode "succeeds", then breaks later
4. **Split Brain:** Multiple sources of truth (GCS, local, Spreaker) caused confusion

### The Solution
**ONE source of truth: GCS**
- Survives container restarts ✅
- Consistent across all environments ✅
- Fail-fast: If GCS fails, we know immediately ✅
- No silent degradation ✅

## Migration Path

### For New Episodes
✅ **Already handled** - Assembly orchestrator enforces GCS upload

### For Existing Episodes

**Episodes with GCS path:** ✅ Work perfectly
**Episodes with Spreaker ID only:** ⚠️  Work via legacy stream URL
**Episodes with neither:** ❌ **BROKEN** - Need manual fix

### Fixing Episode 204 (and similar broken episodes)

**Option A: Re-upload & Re-assemble** (Recommended)
1. Find original audio source
2. Upload via media upload endpoint
3. Re-assemble episode
4. GCS path will be set automatically

**Option B: Restore from backup** (If available)
1. Find audio file in backups
2. Upload directly to GCS: `gs://{bucket}/{user_id}/episodes/{episode_id}/audio/{filename}`
3. Update database: `UPDATE episode SET gcs_audio_path = 'gs://...' WHERE id = '...'`

**Option C: Keep Spreaker fallback** (Temporary)
- If episode still exists on Spreaker, keep `spreaker_episode_id`
- Unpublish fix preserves this now

## Breaking Changes

### Dev Environment
- **Local file serving is GONE**
- Must configure GCS credentials (ADC or service account key)
- Set `GCS_BUCKET` env var
- If GCS unavailable in dev → episode assembly will FAIL (intentional)

### API Responses
- `playback_type` values changed:
  - ~~`"local"`~~ → **REMOVED**
  - `"gcs"` → **NEW** (for GCS audio)
  - `"stream"` → Kept (for legacy Spreaker)
  - `"none"` → Kept (for broken episodes)

- `local_final_exists` → **DEPRECATED**, replaced with `gcs_exists`

### Error Messages
- More explicit: "Episode has no GCS audio file" vs generic "not processed"
- Fail-fast errors instead of silent degradation warnings

## Testing Requirements

### Critical Tests
1. ✅ New episode assembly → GCS upload succeeds
2. ✅ New episode assembly → GCS upload fails → Assembly FAILS
3. ✅ Episode playback → GCS audio works
4. ✅ Episode playback → GCS audio missing → Shows "no audio" error (not silent failure)
5. ✅ Publishing → Requires GCS path
6. ✅ Scheduled episodes → Can be edited
7. ✅ Unscheduling → Preserves Spreaker ID (if not removed from Spreaker)

### Regression Tests
- Legacy episodes with Spreaker ID only → Still play via stream URL
- Episodes with both GCS and Spreaker → Prefer GCS
- Episode 204 (broken) → Shows clear error message

## Monitoring & Alerts

### Critical Metrics
- **GCS upload success rate** → Must be >99.9%
- **Episodes with missing audio** → Alert if >0
- **GCS signed URL generation failures** → Alert immediately

### Log Patterns to Watch
- `CRITICAL: Failed to upload audio to GCS` → Episode assembly failure
- `CRITICAL: GCS signed URL generation failed` → Playback broken

## Rollback Plan

**DO NOT ROLLBACK.** This is a one-way architectural change.

If GCS has issues:
1. Fix GCS (auth, network, bucket policy)
2. Do NOT revert to local files
3. Episodes will be broken until GCS is fixed (intentional)

## Future Enhancements

### Planned (Not Yet Implemented)
1. **Backup strategy:** Separate backup bucket or service
2. **GCS health check endpoint:** Pre-flight check before assembly
3. **Bulk GCS migration tool:** Fix old episodes missing GCS paths
4. **Subscription tiers:** Different retention periods per tier
5. **CDN layer:** CloudFlare/CloudFront in front of GCS for faster delivery

### NOT Planned
- ~~Local file fallback~~ → NEVER AGAIN
- ~~Spreaker as primary source~~ → Legacy only
- ~~Silent GCS failures~~ → Always fail loudly

## Summary

🎯 **GCS or BUST**
- GCS upload fails → Episode assembly fails
- GCS audio missing → Episode is broken (no fallbacks)
- Local files → Not checked anymore
- Spreaker → Legacy fallback only

🛡️ **Fail-Fast Philosophy**
- Better to fail loudly during assembly than silently during playback
- Better to block publishing than allow broken episodes
- Better to show "no audio" error than pretend it works

📊 **Impact**
- ✅ More reliable (one source of truth)
- ✅ More consistent (survives restarts)
- ✅ More transparent (clear errors)
- ⚠️  Less forgiving (GCS must work)

---

**Status:** ✅ Implemented and deployed
**Rollback:** ❌ Not possible - one-way change
**Next:** Bulk migration tool for fixing old episodes

*Last updated: October 13, 2025*
