# Transcript Migration to GCS

**Status**: In Progress  
**Started**: 2025-01-11  
**Related**: TMP_FILES_PROBLEM_AND_SOLUTION.md

## Problem

Transcripts are currently stored in `/tmp/transcripts/` which doesn't work in Cloud Run:
- Multiple container instances don't share `/tmp` storage
- Files created in one container aren't accessible from another
- Container restarts lose all `/tmp` data
- Autoscaling creates new containers without existing files

This is the same root cause as the intern/flubber waveform issue.

## Solution

Migrate to GCS-first architecture:
1. Generate transcript using transcription service
2. **Upload to GCS immediately**: `gs://ppp-media-us-west1/{user_id}/transcripts/{stem}.{type}.json`
3. Store GCS URL in Episode metadata or return directly
4. Clean up any `/tmp` files used during processing
5. Return GCS URL for access

## Implementation Plan

### Phase 1: Create GCS Storage Layer ✅

**File**: `backend/api/services/episodes/transcript_gcs.py`

**Functions**:
- ✅ `save_transcript_to_gcs()` - Upload transcript to GCS
- ✅ `load_transcript_from_gcs()` - Download transcript from GCS
- ✅ `transcript_exists_in_gcs()` - Check existence without downloading
- ✅ `delete_transcript_from_gcs()` - Remove transcript from GCS
- ✅ `get_transcript_gcs_url()` - Generate GCS URL

**Pattern**:
```python
# Save
gcs_url = save_transcript_to_gcs(
    user_id=user.id,
    stem=stem,
    transcript_data=words,
    transcript_type="original"
)
# Returns: gs://ppp-media-us-west1/abc123.../transcripts/{stem}.original.json

# Load
data = load_transcript_from_gcs(
    user_id=user.id,
    stem=stem,
    transcript_type="original"  # or None to try all types
)
```

### Phase 2: Update Write Locations

**2.1 Worker Transcription Task** (HIGH PRIORITY)

**File**: `backend/worker/tasks/transcription.py`

**Current Code** (lines 21-48):
```python
tr_dir = TRANSCRIPTS_DIR
tr_dir.mkdir(parents=True, exist_ok=True)

words = run_transcription(filename)
stem = Path(filename).stem

orig_new = tr_dir / f"{stem}.original.json"
work_new = tr_dir / f"{stem}.json"

with open(orig_new, "w", encoding="utf-8") as fh:
    _json.dump(words, fh, ensure_ascii=False)
with open(work_new, "w", encoding="utf-8") as fh:
    _json.dump(words, fh, ensure_ascii=False)
```

**Target Code**:
```python
from api.services.episodes.transcript_gcs import save_transcript_to_gcs

words = run_transcription(filename)
stem = Path(filename).stem

# Save to GCS (source of truth)
orig_url = save_transcript_to_gcs(user_id, stem, words, "original", gcs_client)
work_url = save_transcript_to_gcs(user_id, stem, words, "working", gcs_client)

# Store URLs in Episode metadata
# TODO: Update Episode.meta_json with transcript URLs
```

**Challenge**: Need `user_id` - must be passed to task or derived from filename

**2.2 Cloud Tasks Transcription** (DEV MODE)

**File**: `backend/infrastructure/tasks_client.py`

**Current Code** (lines 86-91):
```python
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
out_path = TRANSCRIPTS_DIR / f"{stem}.json"
if not out_path.exists():
    out_path.write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")
```

**Target Code**:
```python
from api.services.episodes.transcript_gcs import save_transcript_to_gcs

if not transcript_exists_in_gcs(user_id, stem, "working", gcs_client):
    gcs_url = save_transcript_to_gcs(user_id, stem, words, "working", gcs_client)
    print(f"DEV MODE saved transcript to GCS: {gcs_url}")
```

**2.3 Chunked Processor** (ASSEMBLY AI)

**File**: `backend/worker/tasks/assembly/chunked_processor.py`

**Current Code** (line 296):
```python
json.dump(chunk_transcript, f, indent=2)
```

**Context Needed**: Read more of this file to understand full context

### Phase 3: Update Read Locations

**3.1 Intern Router** (CRITICAL)

**File**: `backend/api/routers/intern.py`

**Current Code** (line 204):
```python
tr_dir = TRANSCRIPTS_DIR
# ... reads transcript from tr_dir
```

**Target Code**:
```python
from api.services.episodes.transcript_gcs import load_transcript_from_gcs

transcript_data = load_transcript_from_gcs(user_id, stem)
if not transcript_data:
    raise HTTPException(status_code=404, detail="Transcript not found")
```

**3.2 Flubber Router** (CRITICAL)

**File**: `backend/api/routers/flubber.py`

**Current Uses** (lines 30, 110, 267, 484):
```python
# Line 30: TRANSCRIPTS_DIR import
# Line 110: tr_dir = TRANSCRIPTS_DIR
# Line 267: reads transcript from tr_dir
# Line 484: reads transcript from tr_dir
```

**Target**: Replace all TRANSCRIPTS_DIR usage with GCS reads

**3.3 Transcripts Service** (CORE)

**File**: `backend/api/services/episodes/transcripts.py`

**Current Functions**:
- `_has_local_transcript_for_stem()` - Checks /tmp for transcript files
- `transcript_endpoints_for_episode()` - Returns transcript URLs

**Target**: 
- Rewrite to check GCS instead of /tmp
- Return signed GCS URLs for transcript access

### Phase 4: Update Database Schema (Optional)

**Option A**: Store URLs in Episode.meta_json
```json
{
  "transcript_urls": {
    "original": "gs://bucket/user/transcripts/stem.original.json",
    "working": "gs://bucket/user/transcripts/stem.working.json"
  }
}
```

**Option B**: Add dedicated columns to Episode table
```sql
ALTER TABLE episodes 
ADD COLUMN transcript_original_url TEXT,
ADD COLUMN transcript_working_url TEXT;
```

**Recommendation**: Start with meta_json (no migration needed), consider dedicated columns later

### Phase 5: Testing & Validation

**Test Cases**:
1. Upload new media file → generates transcript → saves to GCS ✅
2. Intern "Review Intern Commands" → loads transcript from GCS ✅
3. Flubber review → loads transcript from GCS ✅
4. Multiple container instances → all can access same transcript ✅
5. Container restart → transcript still accessible ✅

**Rollback Plan**:
- Keep `/tmp` writes temporarily (dual-write pattern)
- Test GCS reads work correctly
- Once validated, remove `/tmp` writes
- Remove TRANSCRIPTS_DIR from paths.py

### Phase 6: Cleanup

**Remove**:
- TRANSCRIPTS_DIR from `backend/api/core/paths.py`
- All `TRANSCRIPTS_DIR.mkdir()` calls
- All `/tmp/transcripts/` references
- Legacy transcript mirroring logic (`.words.json` suffix handling)

**Add**:
- GCS lifecycle policy: Auto-delete transcripts older than 90 days
- Monitoring: Track GCS upload/download success rates
- Documentation: Update all transcript-related docs

## Migration Status

### Completed
- ✅ Created `transcript_gcs.py` with GCS storage functions
- ✅ Documented migration plan

### In Progress
- ⏳ Identifying all write locations
- ⏳ Identifying all read locations

### Not Started
- ❓ Update worker transcription task (needs user_id resolution)
- ❓ Update Cloud Tasks transcription
- ❓ Update intern router to use GCS
- ❓ Update flubber router to use GCS
- ❓ Update transcripts service core functions
- ❓ Add Episode metadata fields for transcript URLs
- ❓ Test with new upload
- ❓ Test intern review
- ❓ Test flubber review
- ❓ Remove /tmp writes
- ❓ Cleanup TRANSCRIPTS_DIR references

## Key Challenges

### 1. User ID Resolution

**Problem**: Worker tasks receive `filename` but need `user_id` for GCS path

**Options**:
- A) Pass `user_id` to task explicitly
- B) Derive from Episode lookup (query Episode by filename)
- C) Store user_id in filename pattern (e.g., `{user_id}_{original_name}.mp3`)
- D) Use MediaItem lookup (query MediaItem by filename, get user_id)

**Recommendation**: Option D (MediaItem lookup) - most reliable

### 2. Transcript Type Handling

**Current**: Multiple suffixes (.original.json, .words.json, .json, .original.words.json)

**Target**: Standardize on:
- `original` - Raw transcription output
- `working` - Editable version
- `final` - Published version

**Migration**: Map legacy suffixes to new types

### 3. Legacy Mirroring

**Current**: Code mirrors transcripts between `.words.json` and `.json` suffixes

**Target**: Remove mirroring, use single GCS storage

**Migration**: One-time migration of existing transcripts if needed

## Timeline Estimate

- **Phase 1**: ✅ Complete (30 min)
- **Phase 2**: 2-3 hours (update all write locations)
- **Phase 3**: 2-3 hours (update all read locations)
- **Phase 4**: 1 hour (metadata handling)
- **Phase 5**: 2 hours (testing & validation)
- **Phase 6**: 1 hour (cleanup)

**Total**: ~8-10 hours for complete transcript migration

## Dependencies

- ✅ GCSClient exists and works (used in intern snippet fix)
- ✅ GCS bucket `ppp-media-us-west1` accessible
- ✅ Pattern validated with intern snippets (revision 00528)
- ❓ User ID resolution strategy needed
- ❓ Episode metadata update strategy needed

## Next Steps

1. Check revision 00528 deployment status (intern fix)
2. Decide on user_id resolution strategy
3. Update worker transcription task (Phase 2.1)
4. Update Cloud Tasks transcription (Phase 2.2)
5. Test with new upload
6. Update intern/flubber routers (Phase 3)
7. Test with review flows
8. Complete cleanup (Phase 6)
