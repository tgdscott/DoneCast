# 🚨 ONBOARDING MEDIA UPLOAD ISSUES - Steps 5, 6, 7

**Status**: CRITICAL ANALYSIS  
**Date**: October 11, 2025  
**Reported By**: User - "Steps 6 and 7 completely broken, Step 5 might be as well"

---

## Problem Statement

User reports that onboarding steps 5, 6, 7 are "completely broken, probably because it involves saving media files":
- **Step 5**: Podcast Cover Art (optional) - Saving cover image
- **Step 6**: Intro & Outro - Uploading/generating audio files  
- **Step 7**: Music (optional) - Selecting background music

---

## Code Analysis

### Step 5: Cover Art (`coverArt` step)

**Location**: `frontend/src/pages/Onboarding.jsx` lines 1387-1391

**Current Logic**:
```jsx
s.id === 'coverArt' ? async () => {
  // Require cover or explicit skip
  if (formData.coverArt || skipCoverNow) return true;
  return false;
}
```

**Final Submission** (lines 634-648):
```jsx
const podcastPayload = new FormData();
podcastPayload.append('name', formData.podcastName);
podcastPayload.append('description', formData.podcastDescription);
if (formData.coverArt) {
  try {
    const blob = await coverCropperRef.current?.getProcessedBlob?.();
    if (blob) {
      const file = new File([blob], 'cover.jpg', { type: 'image/jpeg' });
      podcastPayload.append('cover_image', file);
    } else {
      podcastPayload.append('cover_image', formData.coverArt);
    }
  } catch {
    podcastPayload.append('cover_image', formData.coverArt);
  }
}
const createdPodcast = await makeApi(token).raw('/api/podcasts/', { method: 'POST', body: podcastPayload });
```

**Backend Endpoint**: `/api/podcasts/` POST

**Potential Issues**:
1. ❓ Does the podcast creation endpoint handle cover_image uploads?
2. ❓ Is the file field name correct (`cover_image`)?
3. ❓ Does the backend use GCS for cover storage?

---

### Step 6: Intro & Outro (`introOutro` step)

**Location**: `frontend/src/pages/Onboarding.jsx` lines 1392-1413

**Upload Logic** (lines 595-616):
```jsx
async function generateOrUploadTTS(kind, mode, script, file) {
  // kind: 'intro' | 'outro'
  try {
    if (mode === 'upload') {
      if (!file) return null;
      const fd = new FormData();
      fd.append('files', file);
      const data = await makeApi(token).raw(`/api/media/upload/${kind}`, { method: 'POST', body: fd });
      if (Array.isArray(data) && data.length > 0) return data[0];
      return null;
    } else {
      const body = { text: script, category: kind };
      if (selectedVoiceId && selectedVoiceId !== 'default') body.voice_id = selectedVoiceId;
      if (firstTimeUser) body.free_override = true;
      const item = await makeApi(token).post('/api/media/tts', body);
      return item || null;
    }
  } catch (e) {
    toast({ title: `Could not prepare ${kind}`, description: e?.message || String(e), variant: 'destructive' });
    return null;
  }
}
```

**Endpoints Used**:
- Upload: `/api/media/upload/${kind}` (POST) where kind = 'intro' or 'outro'
- TTS: `/api/media/tts` (POST)

**Potential Issues**:
1. ❓ Does `/api/media/upload/intro` exist as an endpoint?
2. ❓ Is the file field name correct (`files`)?
3. ❓ Does the backend upload to GCS properly?
4. ❓ Does the response format match expectations (Array)?

---

### Step 7: Music (`music` step)

**Location**: Music is selected but not uploaded

**Logic**:
```jsx
// Music assets are loaded from backend
const data = await makeApi(token).get('/api/media/');
const musicItems = (data?.items || data || []).filter(i => 
  ((i.category || '') === 'music' || (i.category || '') === 'background_music')
);
```

**Music is NOT uploaded** - User selects from existing assets

**Background Music Rules** (lines 679-699):
```jsx
const musicRules = [];
const selectedMusic = (musicAssets || []).find(a => a.id === musicChoice && a.id !== 'none');
if (selectedMusic && selectedMusic.filename) {
  musicRules.push({
    music_filename: selectedMusic.filename,
    apply_to_segments: ['intro'],
    start_offset_s: 0,
    end_offset_s: 1,
    fade_in_s: 1.5,
    fade_out_s: 2.0,
    volume_db: -4,
  });
  // ... outro rule
}
```

**Potential Issues**:
1. ✅ Music step probably works (no upload, just selection)
2. ❓ But relies on intro/outro working properly

---

## Backend Verification Needed

### 1. Check Podcast Creation Endpoint

**Endpoint**: `POST /api/podcasts/`

**Need to verify**:
- [ ] Accepts `cover_image` file upload
- [ ] Uploads to GCS properly
- [ ] Returns podcast object with ID

**Current Code** (likely in `backend/api/routers/podcasts.py`):
```python
@router.post("/", response_model=PodcastPublic)
async def create_podcast(
    name: str = Form(...),
    description: str = Form(...),
    cover_image: UploadFile = File(None),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    # Does this upload cover_image to GCS?
    # Or does it save to /tmp?
```

### 2. Check Media Upload Endpoint

**Endpoint**: `POST /api/media/upload/{category}`

**Need to verify**:
- [ ] `/api/media/upload/intro` route exists
- [ ] `/api/media/upload/outro` route exists
- [ ] Accepts `files` form field
- [ ] Uploads to GCS properly
- [ ] Returns array of MediaItem objects

**Current Code** (backend/api/routers/media.py):
```python
@router.post("/upload/{category}", response_model=List[MediaItem])
async def upload_media(
    category: MediaCategory,
    files: List[UploadFile] = File(...),
    # ...
):
    # Does this upload to GCS?
    # Does it return List[MediaItem]?
```

### 3. Check TTS Endpoint

**Endpoint**: `POST /api/media/tts`

**Need to verify**:
- [ ] Accepts text and category
- [ ] Generates TTS audio
- [ ] Uploads to GCS
- [ ] Returns MediaItem object

---

## Most Likely Root Causes

### Theory 1: GCS Upload Not Working in Media Endpoints ⚠️ HIGH PROBABILITY

**Evidence**:
- Recent GCS migrations focused on download, not upload
- Media upload endpoints might still try to serve from `/tmp`
- Same ephemeral storage problem as intern/flubber

**Test**:
```bash
# Try uploading an intro file
curl -X POST https://podcast-api-kge7snpz7a-uw.a.run.app/api/media/upload/intro \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@test_intro.mp3"
```

### Theory 2: Response Format Mismatch ⚠️ MEDIUM PROBABILITY

**Evidence**:
- Frontend expects: `Array<MediaItem>`
- Backend might return: Single `MediaItem` or different structure

**Frontend Code**:
```jsx
const data = await makeApi(token).raw(`/api/media/upload/${kind}`, { method: 'POST', body: fd });
if (Array.isArray(data) && data.length > 0) return data[0];
```

**If backend returns single object** → `Array.isArray(data)` fails → returns `null`

### Theory 3: Podcast Creation Doesn't Accept Cover Image ⚠️ LOW PROBABILITY

**Evidence**:
- Less likely since this is fundamental functionality
- But possible if endpoint signature changed

---

## Immediate Testing Plan

### Test 1: Check Podcast Creation Endpoint
```bash
# Test with curl
curl -X POST https://podcast-api-kge7snpz7a-uw.a.run.app/api/podcasts/ \
  -H "Authorization: Bearer $TOKEN" \
  -F "name=Test Podcast" \
  -F "description=Test Description" \
  -F "cover_image=@test_cover.jpg"
```

**Expected**: 201 Created with podcast object  
**If fails**: Check error message

### Test 2: Check Media Upload Endpoint
```bash
# Test intro upload
curl -X POST https://podcast-api-kge7snpz7a-uw.a.run.app/api/media/upload/intro \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@test_intro.mp3"
```

**Expected**: 201 Created with array of MediaItem  
**If fails**: Check if endpoint exists, check response format

### Test 3: Check TTS Endpoint
```bash
curl -X POST https://podcast-api-kge7snpz7a-uw.a.run.app/api/media/tts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"Welcome to my podcast","category":"intro"}'
```

**Expected**: 200/201 with MediaItem  
**If fails**: Check error message

---

## Action Plan

### Phase 1: Diagnose (5 min)
1. Check backend logs for onboarding flow errors
2. Test endpoints with curl
3. Identify exact failure point

### Phase 2: Fix Backend (15-30 min)
**If GCS upload broken**:
- Verify media upload endpoint uses GCS
- Verify podcast creation endpoint uploads cover to GCS
- Ensure proper response formats

**If response format wrong**:
- Fix backend to return List[MediaItem]
- Or fix frontend to handle single MediaItem

### Phase 3: Test Full Flow (10 min)
1. Start new onboarding
2. Upload cover art
3. Upload/generate intro
4. Upload/generate outro
5. Complete onboarding
6. Verify podcast created with all assets

---

## Files To Check

**Backend**:
- `backend/api/routers/podcasts.py` - Podcast creation
- `backend/api/routers/media.py` - Media upload endpoint
- `backend/api/routers/media_tts.py` or similar - TTS generation

**Frontend**:
- `frontend/src/pages/Onboarding.jsx` - Main onboarding flow (already reviewed)

---

## Quick Fix Options

### Option A: Skip Media Steps Temporarily
```jsx
// In Onboarding.jsx, allow skipping intro/outro
s.id === 'introOutro' ? async () => {
  return true; // Always allow continue
}
```

### Option B: Fix Response Handling
```jsx
// Handle both array and single object responses
if (mode === 'upload') {
  const data = await makeApi(token).raw(`/api/media/upload/${kind}`, { method: 'POST', body: fd });
  if (Array.isArray(data) && data.length > 0) return data[0];
  if (data && data.id) return data; // Handle single object
  return null;
}
```

### Option C: Fix Backend to Return Proper Format
```python
# In media.py upload endpoint
# Ensure it returns List[MediaItem]
@router.post("/upload/{category}", response_model=List[MediaItem])
async def upload_media(...):
    # ... upload logic ...
    return created_items  # Must be a list
```

---

## Next Immediate Actions

1. **CHECK BACKEND LOGS** for onboarding errors:
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api" --limit=100 | grep -i "upload\|onboarding\|media\|intro\|outro"
```

2. **TEST ENDPOINTS** with curl (see Test 1, 2, 3 above)

3. **IDENTIFY EXACT FAILURE** - which step actually breaks?

4. **DEPLOY FIX** based on findings

---

**PRIORITY**: HIGH - Blocking user signups  
**ESTIMATED FIX TIME**: 30-60 minutes once diagnosed  
**BLOCKING**: Yes - Urgent auth fix deployment (revision 00530)

**RECOMMENDATION**: Let revision 00530 finish deploying, THEN diagnose and fix onboarding
