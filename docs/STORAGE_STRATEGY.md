# Storage Strategy: GCS vs R2

## CRITICAL ARCHITECTURAL DECISION

**This is a fundamental architectural decision that MUST be followed. Violating this will cause production failures.**

## Storage Rules

### GCS (Google Cloud Storage) - Production Files
**GCS is used for files that are used in the PRODUCTION/CONSTRUCTION of episodes.**

Files that go to GCS:
- ✅ **Music files** - Used during episode assembly/construction
- ✅ **Intro/Outro audio** - Used during episode assembly
- ✅ **SFX files** - Used during episode assembly
- ✅ **User-uploaded main content** - Used during episode assembly
- ✅ **TTS-generated audio** - Used during episode assembly
- ✅ **Production transcripts (JSON)** - Used during episode assembly (flubber, intern mode, word timestamps)
- ✅ **Any intermediate/production files**

Files that go to R2:
- ✅ **Final assembled episodes** - Ready for distribution
- ✅ **Final episode cover images** - Ready for distribution
- ✅ **Final transcripts (human-readable)** - Formatted, production-ready transcripts for distribution
- ✅ **Any file that is the FINAL output, not used in construction**

**Note on Transcripts:**
- **Production transcripts (JSON)** → GCS (used during assembly for flubber, intern mode, word timestamps)
- **Final transcripts (formatted .txt)** → R2 (human-readable, production-ready, distributed with episodes)

**Note on Cover Art:**
- **Episode covers** (uploaded separately) → R2 (final assets, not used in audio assembly)
- **Podcast covers** (show artwork) → Can be in GCS or R2 depending on usage

### R2 (Cloudflare R2) - Distribution Files
**R2 is used ONLY for final, production-ready files that are distributed to users.**

Files that go to R2:
- ✅ **Final assembled episodes** - Ready for distribution
- ✅ **Final podcast cover images** - Ready for distribution
- ✅ **Any file that is the FINAL output, not used in construction**

## Why This Matters

1. **Episode Assembly**: The worker servers need access to music, intros, outros, and other assets during episode construction. These MUST be in GCS.

2. **Performance**: GCS is optimized for frequent access during production. R2 is optimized for distribution/CDN.

3. **Data Integrity**: Mixing storage backends causes lookup failures and broken episodes.

4. **Cost**: Production files accessed frequently should be in GCS. Final distribution files accessed less frequently can be in R2.

## Implementation Requirements

### Music Files
- **MUST** be uploaded to GCS (`gs://` paths)
- **MUST NOT** be uploaded to R2 (`r2://` paths)
- Preview endpoints should ONLY check GCS
- Upload endpoints should ONLY write to GCS

### Transcripts

**Production Transcripts (JSON with word timestamps):**
- **MUST** be uploaded to GCS (`gs://` paths)
- **MUST NOT** be uploaded to R2 (`r2://` paths)
- Used during episode construction (flubber, intern mode, word timestamps)
- Even if `STORAGE_BACKEND=r2`, production transcripts should still go to GCS
- Upload endpoints should ONLY write to GCS

**Final Transcripts (Human-readable formatted .txt):**
- **MUST** be uploaded to R2 (`https://` URLs)
- Created after episode assembly completes
- Human-readable formatted versions for distribution
- Stored in R2 alongside final episodes and covers
- Uploaded automatically during episode finalization

### Episode Assembly
- All assets referenced during assembly MUST be in GCS
- Worker servers download from GCS during construction
- Final assembled episode is uploaded to R2 for distribution

### Code Examples

#### ✅ CORRECT: Music Upload to GCS
```python
# backend/api/routers/admin/music.py
bucket = os.getenv("MEDIA_BUCKET")  # GCS bucket
key = f"music/{uuid.uuid4().hex}_{base}"
stored_uri = gcs_upload_fileobj(bucket, key, fileobj, content_type)
filename_stored = stored_uri if stored_uri.startswith("gs://") else f"/static/media/{Path(stored_uri).name}"
```

#### ❌ WRONG: Music Upload to R2
```python
# DO NOT DO THIS FOR MUSIC FILES
bucket = os.getenv("R2_BUCKET")  # WRONG!
stored_uri = r2_upload_fileobj(bucket, key, fileobj)  # WRONG!
```

#### ❌ WRONG: Transcript Upload to R2
```python
# DO NOT DO THIS FOR TRANSCRIPTS
storage_backend = os.getenv("STORAGE_BACKEND", "gcs").lower()
if storage_backend == "r2":
    bucket = os.getenv("R2_BUCKET")  # WRONG! Transcripts must be in GCS
    stored_uri = r2_upload_bytes(bucket, key, content)  # WRONG!
```

#### ✅ CORRECT: Music Preview from GCS
```python
# backend/api/routers/music.py
if filename.startswith("gs://"):
    # Download from GCS
    data = storage.download_bytes(bucket, key)
elif filename.startswith("r2://"):
    # ERROR: Music should not be in R2
    raise HTTPException(500, "Music files must be in GCS, not R2")
```

#### ✅ CORRECT: Final Episode to R2
```python
# After episode assembly is complete
r2_bucket = os.getenv("R2_BUCKET")
r2_key = f"episodes/{episode_id}/{final_filename}"
r2_upload_fileobj(r2_bucket, r2_key, final_audio_file)
episode.final_audio_url = f"r2://{r2_bucket}/{r2_key}"
```

## Error Handling

If you see errors like:
- `Music asset incorrectly stored in R2`
- `Transcript storage returned non-GCS URL`
- `R2 object not found: music/...` or `transcripts/...`
- `GCS download returned None for gs://.../music/...` or `gs://.../transcripts/...`

This indicates a data integrity issue:
1. Check where the file was uploaded (should be GCS)
2. Check the database record (should have `gs://` path)
3. Migrate any incorrectly stored files from R2 to GCS
4. Update database records to point to GCS paths
5. Verify `STORAGE_BACKEND` env var is not forcing R2 for production files

## Migration Checklist

If you find production files incorrectly stored in R2 (music, transcripts, etc.):

1. ✅ Identify all affected records in database
2. ✅ Download files from R2
3. ✅ Upload files to GCS
4. ✅ Update database records with new `gs://` paths
5. ✅ Verify preview/access endpoints work
6. ✅ Test episode assembly with migrated files
7. ✅ Check `STORAGE_BACKEND` env var - should be "gcs" or unset for production files

## Documentation References

- Music upload: `backend/api/routers/admin/music.py`
- Music preview: `backend/api/routers/music.py`
- Transcript upload: `backend/api/services/transcription/__init__.py`
- Transcript usage: `backend/worker/tasks/assembly/transcript.py`
- Episode assembly: `backend/worker/tasks/assembly/`
- Storage utilities: `backend/infrastructure/gcs.py`, `backend/infrastructure/r2.py`

## Questions?

If you're unsure which storage to use, ask:
- **Is this file used during episode construction?** → GCS
- **Is this the final output ready for distribution?** → R2
- **Is this an intermediate/production file?** → GCS
- **Is this a user-facing final product?** → R2

**When in doubt, use GCS. It's safer to have production files in GCS than to break episode assembly.**

