# GCS Handling Audit - October 13, 2025

## Overview
Investigation triggered by Manual Editor audio loading bug revealed a **pattern of missing GCS handling** across multiple endpoints. This is a production-critical issue because Cloud Run containers have ephemeral storage - local files don't survive restarts.

## Root Cause Pattern
Many endpoints were written assuming local filesystem access via `final_audio_path` or `cover_path`, but these patterns fail in production where:
1. ✅ **GCS is primary storage** (`gcs_audio_path`, `gcs_cover_path`)
2. ❌ **Local files are temporary** (dev only, lost on container restart)
3. ❌ **Spreaker URLs are legacy** (migration in progress)

## Endpoints With Missing GCS Handling

### 🔴 CRITICAL - User-Facing Endpoints

#### 1. `/api/public/episodes` (public.py)
**Status:** Missing GCS support  
**Impact:** Public demo page won't show audio for production episodes  
**Current behavior:**
- Only checks `FINAL_DIR` and `MEDIA_DIR` local paths
- Returns relative URLs like `/static/final/{file}` or `/static/media/{file}`
- **Fails silently** when audio is in GCS (returns `null` for `audio_url`)

**Lines:** 28-44 in `backend/api/routers/public.py`

**Fix needed:**
```python
# BEFORE (broken for GCS):
audio_url = None
if e.final_audio_path:
    base = os.path.basename(e.final_audio_path)
    candidates = [FINAL_DIR / base, MEDIA_DIR / base]
    existing = next((c for c in candidates if c.exists()), None)
    if existing is not None:
        audio_url = f"/static/final/{base}"  # Relative path

# AFTER (production-ready):
from api.routers.episodes.common import compute_playback_info

playback_info = compute_playback_info(e)
audio_url = playback_info.get("final_audio_url") or playback_info.get("stream_url")
```

---

#### 2. `/api/episodes/{id}/cover` (episode_covers.py)
**Status:** Missing GCS support  
**Impact:** Episode cover images broken in production if stored in GCS  
**Current behavior:**
- Only checks local filesystem paths
- Returns `FileResponse` from local disk only
- **404s** when cover is in GCS

**Lines:** 20-48 in `backend/api/routers/episode_covers.py`

**Fix needed:**
```python
# Check gcs_cover_path first, similar to compute_playback_info logic
gcs_cover_path = getattr(ep, "gcs_cover_path", None)
if gcs_cover_path and str(gcs_cover_path).startswith("gs://"):
    from infrastructure.gcs import get_signed_url
    gcs_str = str(gcs_cover_path)[5:]  # Remove "gs://"
    parts = gcs_str.split("/", 1)
    if len(parts) == 2:
        bucket, key = parts
        signed_url = get_signed_url(bucket, key, expiration=3600)
        # Redirect to signed URL or proxy through backend
        return RedirectResponse(url=signed_url)
```

---

### 🟡 MEDIUM PRIORITY - Processing Endpoints

#### 3. Flubber endpoints (flubber.py)
**Status:** ⚠️ **Partially fixed** but needs verification  
**Impact:** Flubber audio cutting may fail if GCS paths not handled correctly  
**Current state:**
- Lines 190-250: **Has GCS download logic** for retrieving audio from GCS
- Lines 29, 102-103: Uses `final_audio_path` directly without GCS fallback
- **Risk:** May work for some flows but fail for others

**Action needed:**
1. Verify GCS download logic works with both:
   - Legacy filenames: `"abc123.mp3"`
   - New GCS URLs: `"gs://bucket/user_id/media/main_content/abc123.mp3"`
2. Ensure `_load_episode_meta()` can resolve episodes with GCS-only audio
3. Test Flubber workflow end-to-end with production GCS episode

---

### ✅ ALREADY FIXED

#### 4. Manual Editor `/api/episodes/{id}/edit-context` (edit.py)
**Status:** ✅ **FIXED** October 13, 2025  
**Fix:** Now uses `compute_playback_info()` instead of manual file checks  
**See:** `MANUAL_EDITOR_AUDIO_FIX_OCT13.md`

#### 5. Transcript endpoints (transcripts.py)
**Status:** ✅ **Already has GCS fallback**  
**Implementation:** `_resolve_from_gcs()` function checks GCS when local file missing  
**Lines:** 142-152 in `backend/api/routers/transcripts.py`

#### 6. Episode list/history (episodes/list.py or common.py)
**Status:** ✅ **Already correct**  
**Implementation:** Uses `compute_playback_info()` properly

---

## The Golden Pattern: `compute_playback_info()`

This function in `backend/api/routers/episodes/common.py` is the **production-tested solution**:

```python
def compute_playback_info(episode: Any, *, now: Optional[datetime] = None) -> dict[str, Any]:
    """Determine playback preference between local and GCS audio.

    Priority order:
    1. GCS URL (gcs_audio_path) - survives container restarts
    2. Local file (final_audio_path) - dev only
    3. Spreaker stream URL - published episodes
    """
    # 1. Check GCS
    if gcs_audio_path and str(gcs_audio_path).startswith("gs://"):
        from infrastructure.gcs import get_signed_url
        # Parse gs://bucket/key
        # Generate signed URL with 1-hour expiration
        final_audio_url = get_signed_url(bucket, key, expiration=3600)
    
    # 2. Check local file (dev fallback)
    if not final_audio_url:
        # Check FINAL_DIR, MEDIA_DIR
    
    # 3. Check Spreaker (legacy)
    if spreaker_episode_id:
        stream_url = f"https://api.spreaker.com/v2/episodes/{spk_id}/play"
    
    return {
        "final_audio_url": final_audio_url,
        "stream_url": stream_url,
        "local_final_exists": bool(local exists or GCS exists),
        # ... other metadata
    }
```

### Why This Matters
- ✅ Handles all 3 storage types (GCS, local, Spreaker)
- ✅ Proper fallback chain
- ✅ Generates signed URLs with expiration
- ✅ Applies 7-day grace period logic
- ✅ Production-tested and battle-hardened

### When to Use It
**ANY time you need to serve or return an audio URL:**
- Episode playback
- Audio previews
- Manual editor
- Public demo pages
- RSS feed generation (has separate logic but similar pattern)

**DON'T manually check `final_audio_path` and return `/static/...` paths!**

---

## GCS Cover Art Pattern

For cover images, a similar pattern is needed. Currently missing but should be:

```python
def compute_cover_url(episode: Any, *, expiration: int = 3600) -> Optional[str]:
    """Get cover URL with GCS priority."""
    
    # Priority 1: GCS path
    gcs_cover_path = getattr(episode, "gcs_cover_path", None)
    if gcs_cover_path and str(gcs_cover_path).startswith("gs://"):
        from infrastructure.gcs import get_signed_url
        gcs_str = str(gcs_cover_path)[5:]
        parts = gcs_str.split("/", 1)
        if len(parts) == 2:
            bucket, key = parts
            return get_signed_url(bucket, key, expiration=expiration)
    
    # Priority 2: Remote URL (already uploaded somewhere)
    remote_cover_url = getattr(episode, "remote_cover_url", None)
    if remote_cover_url:
        return remote_cover_url
    
    # Priority 3: Local file (dev only)
    cover_path = getattr(episode, "cover_path", None)
    if cover_path:
        # Check if URL already
        if str(cover_path).startswith(("http://", "https://")):
            return cover_path
        # Generate local static path
        return f"/static/media/{os.path.basename(cover_path)}"
    
    return None
```

---

## Database Fields Reference

### Episode Model (`backend/api/models/podcast.py`)

```python
class Episode(SQLModel, table=True):
    # Legacy local paths (dev only, ephemeral in production)
    final_audio_path: Optional[str] = Field(default=None)
    cover_path: Optional[str] = Field(default=None)
    
    # Production GCS paths (persistent, survive restarts)
    gcs_audio_path: Optional[str] = Field(default=None, description="GCS path (gs://...) for assembled audio")
    gcs_cover_path: Optional[str] = Field(default=None, description="GCS path (gs://...) for episode cover")
    
    # Legacy remote URLs (Spreaker migration)
    spreaker_episode_id: Optional[str] = Field(default=None)
    remote_cover_url: Optional[str] = Field(default=None, description="Spreaker-hosted cover image URL")
```

**Always check in priority order:**
1. `gcs_*_path` (production primary)
2. `remote_*_url` (legacy, but persistent)
3. Local `*_path` (dev only, ephemeral)

---

## Migration Status

### Already Migrated to GCS ✅
- Episode audio after assembly (via assembler service)
- Transcripts (via transcript migration)
- Media uploads (raw content)

### Not Yet GCS-Aware ❌
- `/api/public/episodes` endpoint (returns local paths only)
- `/api/episodes/{id}/cover` endpoint (serves local files only)
- Possibly some Flubber flows (needs verification)

---

## Action Plan

### Phase 1: Critical Fixes (Production Broken)
- [ ] **Fix `/api/public/episodes`** - Use `compute_playback_info()`
- [ ] **Fix `/api/episodes/{id}/cover`** - Add GCS cover support
- [ ] **Test fixes in production** - Verify signed URLs work

### Phase 2: Verification (Production Risk)
- [ ] **Audit Flubber flows** - Verify GCS download logic works end-to-end
- [ ] **Test Intern flows** - Check if similar issues exist
- [ ] **Review all `FileResponse` usage** - Ensure no other direct file serving

### Phase 3: Refactoring (Technical Debt)
- [ ] **Create `compute_cover_url()` helper** - Standardize cover URL resolution
- [ ] **Document GCS patterns** - Add to copilot instructions
- [ ] **Add GCS checks to PR template** - Prevent future regressions

---

## Testing Checklist

### For Each Fixed Endpoint:

#### Local Dev Testing
```bash
# 1. Episode with local audio only
curl http://localhost:8000/api/public/episodes | jq '.items[0].final_audio_url'
# Should return: "/static/final/..." or "/static/media/..."

# 2. Episode with GCS audio
# (set gcs_audio_path in DB)
# Should return: "https://storage.googleapis.com/..." (signed URL)

# 3. Episode with Spreaker audio only
# Should return: "https://api.spreaker.com/v2/episodes/{id}/play"
```

#### Production Testing
```bash
# 1. Check production episode
curl https://getpodcastplus.com/api/public/episodes | jq '.items[0].final_audio_url'
# MUST return GCS signed URL, not null

# 2. Verify signed URL works
curl -I "https://storage.googleapis.com/..." 
# Should return 200 OK

# 3. Check expiration
# Signed URLs expire after 1 hour (3600 seconds)
# Verify 'Expires' parameter in URL
```

---

## Related Documentation
- `MANUAL_EDITOR_AUDIO_FIX_OCT13.md` - Original bug that triggered this audit
- `GCS_MIGRATION_COMPLETE_STATUS.md` - GCS migration history
- `TRANSCRIPT_MIGRATION_TO_GCS.md` - Transcript GCS migration details

---

## Prevention Strategy

### Code Review Checklist
When reviewing PRs that touch media/audio endpoints:
- [ ] Does it check `gcs_audio_path` or `gcs_cover_path` first?
- [ ] Does it use `compute_playback_info()` or equivalent?
- [ ] Does it avoid hardcoding `/static/...` paths?
- [ ] Does it handle signed URL expiration properly?
- [ ] Is there a fallback for local dev mode?

### Lint Rule (Future)
Consider adding a lint rule that warns on:
```python
# BAD PATTERNS:
f"/static/final/{filename}"  # Hardcoded static path
Path(episode.final_audio_path)  # Direct access without GCS check
FileResponse(path=...)  # Direct file serving without GCS check
```

---

*Audit completed: October 13, 2025*  
*Triggered by: Manual Editor audio loading bug*  
*Priority: Production-critical - local files don't survive container restarts*
