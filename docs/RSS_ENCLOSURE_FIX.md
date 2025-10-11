# RSS Feed Enclosure Fix

## Problem
RSS feed at `https://app.podcastplusplus.com/api/rss/cinema-irl/feed.xml` was generating valid XML with episode metadata BUT completely missing `<enclosure>` tags for audio files. This made the feed non-functional for podcast apps since they couldn't download/play episodes.

**Symptoms:**
- Feed returned 200 OK with 2275 lines of XML
- Episodes present with title, description, pubDate, iTunes metadata
- Zero `<enclosure>` tags in entire feed
- Database confirmed 196 episodes with `gcs_audio_path` populated

## Root Cause
The RSS feed generation code in `backend/api/routers/rss_feed.py` (lines 133-143) correctly checks for `episode.gcs_audio_path` and calls `get_public_audio_url()` to generate signed URLs. However:

1. `get_public_audio_url()` calls `_generate_signed_url()` 
2. `_generate_signed_url()` requires signing credentials (service account key) to create signed URLs
3. Cloud Run didn't have the GCS signing key configured
4. Without signing credentials, `_generate_signed_url()` returns `None`
5. RSS feed code checks `if audio_url:` and skips creating enclosures when it's `None`

**Key Code Flow:**
```python
# rss_feed.py lines 133-143
audio_url = None
if episode.gcs_audio_path:
    audio_url = get_public_audio_url(episode.gcs_audio_path, expiration_days=7)

if audio_url:  # <-- This was False because get_public_audio_url returned None
    file_size = getattr(episode, "audio_file_size", None) or 0
    ET.SubElement(item, "enclosure", {
        "url": audio_url,
        "type": "audio/mpeg",
        "length": str(file_size),
    })
```

## Solution
1. **Added Secret Loading**: Updated `backend/infrastructure/gcs.py` to check for `GCS_SIGNER_KEY_JSON` environment variable
2. **Configured Secret in Cloud Run**: Updated `cloudbuild.yaml` to mount the `gcs-signer-key` secret as environment variable
3. **Verified Secret Exists**: Confirmed `gcs-signer-key` secret exists in Secret Manager (created 2025-10-07)

### Code Changes

**File: `backend/infrastructure/gcs.py`** (lines 45-87)
Added support for `GCS_SIGNER_KEY_JSON` environment variable:
```python
# Try loading from GCS_SIGNER_KEY_JSON env var (Cloud Run with Secret Manager)
signer_key_json = os.getenv("GCS_SIGNER_KEY_JSON")
if signer_key_json:
    try:
        # Cloud Run will have already resolved sm:// to the actual JSON content
        key_dict = json.loads(signer_key_json)
        credentials = service_account.Credentials.from_service_account_info(key_dict)
        _SIGNING_CREDENTIALS = credentials
        logger.info("Loaded signing credentials from GCS_SIGNER_KEY_JSON env var")
        return credentials
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse GCS_SIGNER_KEY_JSON as JSON: {e}")
    except Exception as e:
        logger.warning(f"Failed to load signing credentials from GCS_SIGNER_KEY_JSON: {e}")
```

**File: `cloudbuild.yaml`** (line 191)
Added secret mounting to Cloud Run deployment:
```yaml
--update-secrets="GCS_SIGNER_KEY_JSON=gcs-signer-key:latest"
```

**File: `cloudrun-api-env.yaml`** (line 33)
Added env var configuration (note: this file isn't used in Cloud Build, but documents the config):
```yaml
GCS_SIGNER_KEY_JSON: "sm://podcast612/gcs-signer-key"
```

## Deployment Steps
```powershell
# Deploy the fix
gcloud builds submit --config=cloudbuild.yaml

# Verify deployment
gcloud run services describe podcast-api --region=us-west1 --format="value(spec.template.spec.containers[0].env)"

# Test RSS feed
Invoke-WebRequest "https://app.podcastplusplus.com/api/rss/cinema-irl/feed.xml" -OutFile "test_rss_feed.xml"
Select-String -Pattern "enclosure" test_rss_feed.xml
```

## Expected Result
After deployment, the RSS feed should contain enclosure tags like:
```xml
<enclosure 
  url="https://storage.googleapis.com/ppp-media-us-west1/...?X-Goog-Signature=..." 
  length="15627500" 
  type="audio/mpeg"/>
```

## Verification
1. RSS feed should have enclosure tags for all 196 episodes
2. Signed URLs should be valid for 7 days
3. Podcast apps should be able to download and play episodes
4. Feed should pass validation at https://podba.se/validate/

## Related Issues
- Spreaker migration completed successfully (190 episodes, 100% success)
- Database has correct `gcs_audio_path` and `audio_file_size` for all episodes
- Cover images still on Spreaker CDN (196 episodes) - separate task
- Transcripts not yet in feed - separate task

## Comparison with Spreaker
Spreaker's feed includes:
```xml
<enclosure url="https://dts.podtrac.com/redirect.mp3/op3.dev/e/api.spreaker.com/download/episode/68043737/..." length="15627500" type="audio/mpeg"/>
<podcast:transcript url="https://transcription.spreaker.com/..." type="application/x-subrip" language="en"/>
```

Our feed will now have enclosures. Transcript support is a separate enhancement.
