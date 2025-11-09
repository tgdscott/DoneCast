# Transcript Cross-Environment Fix

## Problem

When uploading files on dev and processing on production (or vice versa), transcripts cannot be found because:

1. **Different Buckets**: Dev and production may use different `TRANSCRIPTS_BUCKET` values
2. **Path Reconstruction**: Transcript lookup reconstructs paths from environment variables instead of using stored GCS URIs
3. **Stem Mismatch**: The filename stem used for lookup may differ between environments

## Root Cause

The transcript lookup code in `backend/worker/tasks/assembly/media.py` and `backend/api/services/transcripts.py`:

1. **Relies on environment variables** (`TRANSCRIPTS_BUCKET` or `MEDIA_BUCKET`)
2. **Reconstructs paths** from episode metadata (filename stems)
3. **Doesn't prioritize stored GCS URIs** from episode metadata

When a transcript is created, the GCS URI is stored in `episode.meta_json['transcripts']['gcs_json']`, but the lookup code often ignores this and tries to reconstruct the path.

## Current Storage Patterns

### Pattern 1: Flat Structure (transcription service)
- **Path**: `transcripts/{stem}.json`
- **Stored in**: Episode metadata as `gcs_json: "gs://bucket/transcripts/{stem}.json"`

### Pattern 2: User-Specific (transcript_gcs.py)
- **Path**: `{user_id}/transcripts/{stem}.{type}.json`
- **Stored in**: Episode metadata (if implemented)

## Solution

### Fix 1: Prioritize Stored GCS URIs

Update transcript lookup to:
1. **First**: Check `episode.meta_json['transcripts']['gcs_json']` or `episode.meta_json['transcripts']['gcs_uri']`
2. **Second**: Check `episode.meta_json['transcripts']['gcs_bucket']` + reconstruct path
3. **Third**: Fall back to environment-based lookup

### Fix 2: Store Complete GCS URI in Metadata

Ensure all transcript creation code stores the complete GCS URI:
```python
transcripts_meta = {
    "gcs_json": "gs://ppp-transcripts-us-west1/transcripts/episode_123.json",
    "gcs_bucket": "ppp-transcripts-us-west1",
    "bucket_stem": "episode_123",
    "gcs_key": "transcripts/episode_123.json"
}
```

### Fix 3: Use Same Bucket Across Environments

Ensure dev and production use the same transcript bucket:
- **Production**: `ppp-transcripts-us-west1`
- **Dev**: Should also use `ppp-transcripts-us-west1` (not a separate dev bucket)

## Implementation

### Step 1: ✅ Update Transcript Lookup to Prioritize Stored URIs (COMPLETED)

In `backend/worker/tasks/assembly/media.py`, added priority-based lookup:

1. **PRIORITY 1**: Download directly from stored GCS URI (`gcs_json` from metadata)
   - Parses `gs://bucket/path` format
   - Downloads directly from the exact bucket and key stored in metadata
   - Works even if environment uses different bucket

2. **PRIORITY 2**: Fall back to environment-based lookup
   - Only if stored URI doesn't work
   - Uses `TRANSCRIPTS_BUCKET` or `MEDIA_BUCKET` from environment
   - Tries multiple stem variants and suffixes

### Step 2: ✅ Ensure Metadata is Stored Correctly (ALREADY IMPLEMENTED)

The transcription service already stores complete GCS URI in metadata:

```python
transcripts = dict(meta.get("transcripts", {}))
transcripts["gcs_json"] = gcs_uri  # Full gs:// URI
transcripts["gcs_bucket"] = bucket
transcripts["bucket_stem"] = safe_stem
transcripts["gcs_key"] = key  # Path within bucket
meta["transcripts"] = transcripts
```

### Step 3: Update Environment Configuration

**CRITICAL**: Ensure both dev and production use the same transcript bucket:
- **Production**: `TRANSCRIPTS_BUCKET=ppp-transcripts-us-west1`
- **Dev**: Should also use `TRANSCRIPTS_BUCKET=ppp-transcripts-us-west1` (not a separate dev bucket)

**Why this matters**: Even though the fix prioritizes stored URIs, if dev and production use different buckets, transcripts uploaded on dev won't be accessible from production (and vice versa) unless both environments can access the same GCS bucket.

**Solution**: Use the same transcript bucket for both environments, or ensure both environments have read access to each other's buckets.

## Testing

1. **Upload file on dev**, verify transcript is created and GCS URI is stored in metadata
2. **Process episode on production**, verify transcript is found using stored GCS URI
3. **Check logs** for transcript lookup attempts and which method succeeded

## Expected Behavior After Fix

1. Transcript created on dev → stored with GCS URI in metadata
2. Episode processed on production → transcript lookup uses stored GCS URI first
3. If stored URI fails, fall back to environment-based lookup
4. Both environments can find transcripts regardless of where they were created

