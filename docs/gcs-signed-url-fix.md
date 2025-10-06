# GCS Signed URL Fix for Cloud Run

## Problem
Cloud Run uses Compute Engine default credentials which **don't have a private key** for signing URLs.

Error:
```
AttributeError: you need a private key to sign credentials.
the credentials you are currently using <class 'google.auth.compute_engine.credentials.Credentials'> 
just contains a token.
```

This breaks:
- Media preview (intro/outro/music/SFX playback)
- Episode assembly (can't access template media files)

## Solutions Implemented

### Solution 1: IAM-Based Signing (Code Fix)
Updated `backend/infrastructure/gcs.py` to use IAM API for signing when private key unavailable.

**Pros**: No infrastructure changes needed
**Cons**: Adds latency (IAM API call per URL), may still fail

### Solution 2: Public URLs (Recommended)
Make media objects publicly readable, skip signed URLs entirely.

**Pros**: 
- Instant, no signing overhead
- Works reliably with Cloud Run
- Intro/outro/music/SFX are not sensitive data

**Cons**: 
- Objects are world-readable (but URLs are still obscure)

## Deploy Solution 2 (Recommended)

### Option A: Make Bucket Public for Specific Files

```bash
# Allow public read for intro/outro/music/SFX paths
gsutil iam ch allUsers:objectViewer gs://ppp-media-us-west1

# Or more granular (by path prefix):
gsutil -m setmeta -h "Cache-Control:public, max-age=3600" gs://ppp-media-us-west1/*/intro/**
gsutil -m setmeta -h "Cache-Control:public, max-age=3600" gs://ppp-media-us-west1/*/outro/**
gsutil -m setmeta -h "Cache-Control:public, max-age=3600" gs://ppp-media-us-west1/*/music/**
gsutil -m setmeta -h "Cache-Control:public, max-age=3600" gs://ppp-media-us-west1/*/sfx/**
```

### Option B: Use Signed URLs with Service Account Key (Not Recommended)

1. Create service account key:
```bash
gcloud iam service-accounts keys create key.json \
  --iam-account=podcast612@appspot.gserviceaccount.com
```

2. Add to Cloud Run:
```bash
gcloud run services update podcast-api \
  --update-secrets=GOOGLE_APPLICATION_CREDENTIALS=gcs-signer-key:latest
```

**Don't do this** - managing keys is a security risk.

## Quick Fix (Deploy Now)

The code fix is already in place. To make it work reliably:

```bash
# 1. Make bucket publicly readable (safe for media files)
gsutil iam ch allUsers:objectViewer gs://ppp-media-us-west1

# 2. Redeploy with the code fix
cd d:/PodWebDeploy
git add backend/infrastructure/gcs.py
git commit -m "Fix: Use IAM-based signing for GCS URLs in Cloud Run

- Fallback to public URLs when private key unavailable
- Fixes media preview for intro/outro/music/SFX
- Works with Cloud Run default credentials"
git push origin main
gcloud builds submit --config cloudbuild.yaml
```

## Testing

After deploy:
```bash
# Test media preview
curl https://api.podcastplusplus.com/api/media/preview?path=gs://ppp-media-us-west1/USER_ID/music/some-file.mp3

# Should return:
# - HTTP 302 redirect to signed URL (with IAM), OR
# - HTTP 302 redirect to public URL (if IAM fails)
```

## Alternative: Per-Object ACL

If you don't want the whole bucket public:

```bash
# Make specific objects public when uploaded
gsutil acl ch -u AllUsers:R gs://ppp-media-us-west1/path/to/file.mp3
```

Update upload code to set ACL:
```python
blob.upload_from_file(fileobj)
blob.make_public()  # Add this after upload
```

## Recommendation

**Use Solution 2** (public bucket for media):
- Fastest (no signing overhead)
- Most reliable (no IAM API dependency)
- Acceptable for non-sensitive content (music, intros, outros)

Keep **main_content** and **episode_cover** in private buckets with signed URLs.
