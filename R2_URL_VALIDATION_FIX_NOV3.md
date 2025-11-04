# R2 Storage URL Validation Fix - Nov 3, 2025

## Problem
Orchestrator was validating cloud storage URLs with hardcoded check for `gs://` prefix, which breaks when using R2 storage (returns `https://` URLs instead).

## Root Cause
When `STORAGE_BACKEND=r2` is set:
1. ✅ R2 upload succeeds → returns `https://ppp-media.{account_id}.r2.cloudflarestorage.com/...`
2. ❌ Orchestrator validates: `if url.startswith("gs://")` → **FALSE**
3. ❌ Raises RuntimeError → **Assembly fails completely**

## Fix Applied
Changed URL validation to accept BOTH formats:
- GCS: `gs://bucket-name/path/to/file`
- R2: `https://bucket.account.r2.cloudflarestorage.com/path/to/file`

### Files Modified
**`backend/worker/tasks/assembly/orchestrator.py`**

#### Audio Upload Validation (line ~943)
```python
# OLD:
if not gcs_audio_url or not str(gcs_audio_url).startswith("gs://"):
    raise RuntimeError(f"[assemble] CRITICAL: GCS upload returned invalid URL: {gcs_audio_url}")

# NEW:
url_str = str(gcs_audio_url) if gcs_audio_url else ""
if not url_str or not (url_str.startswith("gs://") or url_str.startswith("https://")):
    raise RuntimeError(f"[assemble] CRITICAL: Cloud storage upload returned invalid URL: {gcs_audio_url}")
```

#### Cover Image Upload Validation (line ~993)
```python
# OLD:
if not gcs_cover_url or not str(gcs_cover_url).startswith("gs://"):
    raise RuntimeError(f"[assemble] CRITICAL: Cover cloud storage upload failed - returned invalid URL: {gcs_cover_url}")

# NEW:
cover_url_str = str(gcs_cover_url) if gcs_cover_url else ""
if not cover_url_str or not (cover_url_str.startswith("gs://") or cover_url_str.startswith("https://")):
    raise RuntimeError(f"[assemble] CRITICAL: Cover cloud storage upload failed - returned invalid URL: {gcs_cover_url}")
```

## About the `gcs_audio_path` Field Name

**Q: Should we rename `gcs_audio_path` to something storage-agnostic?**

**A: NO - Leave it as is.** Here's why:

### Reasons to Keep `gcs_audio_path` Name:

1. **Database migration complexity** - Renaming column requires migration on production DB
2. **Backward compatibility** - Existing code/queries reference this field
3. **Storage abstraction already works** - The field stores URLs from ANY backend (GCS or R2)
4. **"GCS" is just legacy naming** - Common pattern (like GitHub uses `git_` prefix even though they support other VCS)
5. **No runtime confusion** - Code uses `storage.upload_fileobj()` abstraction, field name doesn't matter

### Field Actually Stores:
- **With GCS:** `gs://ppp-media-us-west1/user-id/episodes/episode-id/audio/file.mp3`
- **With R2:** `https://ppp-media.account-id.r2.cloudflarestorage.com/user-id/episodes/episode-id/audio/file.mp3`

Both are valid URLs, both work with the storage abstraction layer.

### If You Really Want to Rename (Future):
1. Add new field: `storage_url` or `cloud_audio_url`
2. Backfill existing data: `UPDATE episodes SET storage_url = gcs_audio_path WHERE gcs_audio_path IS NOT NULL`
3. Update all code references
4. Deprecate `gcs_audio_path` after transition period
5. Eventually drop old column

**Verdict:** Not worth the effort right now. The abstraction layer (`infrastructure/storage.py`) already makes this seamless.

## Related Architecture

### Storage Abstraction Layer
**File:** `backend/infrastructure/storage.py`

Routes operations based on `STORAGE_BACKEND` env var:
```python
def _get_backend() -> str:
    backend = os.getenv("STORAGE_BACKEND", "gcs").lower()
    if backend not in ("gcs", "r2"):
        return "gcs"
    return backend

def upload_fileobj(...):
    backend = _get_backend()
    if backend == "r2":
        return r2.upload_fileobj(...)  # Returns https:// URL
    else:
        return gcs.upload_fileobj(...)  # Returns gs:// URL
```

### Current Configuration
**File:** `backend/.env.local`
```bash
STORAGE_BACKEND=r2
R2_BUCKET=ppp-media
```

This routes ALL storage operations to Cloudflare R2 (zero egress fees, built-in CDN).

## Testing Checklist
- [ ] Upload raw audio file → transcription works
- [ ] Assemble episode → no URL validation errors
- [ ] Check episode record `gcs_audio_path` → contains valid R2 URL
- [ ] RSS feed generation → audio URLs work
- [ ] Playback in frontend → audio loads from R2

## Status
✅ **FIXED** - Nov 3, 2025

URL validation now accepts both GCS and R2 formats, allowing seamless storage backend switching.
