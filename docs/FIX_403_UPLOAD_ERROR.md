# Fix 403 Upload Error - Production

## Problem
Users getting **403 Forbidden** error when uploading audio files to production.

**Error in browser console:**
```
Failed to load resource: storage.googleapis.com/... - 403 (Forbidden)
```

## Root Cause

The upload flow is:
1. Frontend calls `/api/media/upload/{category}/presign`
2. Backend generates a signed URL using IAM-based signing
3. Frontend tries to PUT file to signed GCS URL
4. **GCS rejects with 403 Forbidden**

**Why 403?**
The Cloud Run service account doesn't have permission to:
- Sign blobs via IAM Credentials API (`iam.serviceAccounts.signBlob`)
- Or the signed URL is being generated incorrectly

## Solution

### Step 1: Grant IAM Permissions to Cloud Run Service Account

Get your Cloud Run service account email:
```bash
gcloud run services describe podcast-api --region=us-west1 --format="value(spec.template.spec.serviceAccountName)"
```

If it returns nothing, it's using the default compute service account:
```
{PROJECT_NUMBER}-compute@developer.gserviceaccount.com
```

For project `podcast612`, check:
```bash
gcloud projects describe podcast612 --format="value(projectNumber)"
```

### Step 2: Add Required IAM Roles

```bash
# Replace with your actual service account email
SERVICE_ACCOUNT="524304361363-compute@developer.gserviceaccount.com"
PROJECT_ID="podcast612"

# Allow signing blobs via IAM Credentials API
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/iam.serviceAccountTokenCreator"

# Ensure storage permissions (may already have these)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/storage.objectAdmin"
```

Or add at bucket level:
```bash
BUCKET_NAME="ppp-media-us-west1"

gsutil iam ch serviceAccount:$SERVICE_ACCOUNT:roles/storage.objectAdmin \
  gs://$BUCKET_NAME
```

### Step 3: Verify Permissions

```bash
# Check project-level IAM
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:$SERVICE_ACCOUNT"

# Check bucket-level IAM
gsutil iam get gs://$BUCKET_NAME | grep $SERVICE_ACCOUNT
```

### Step 4: Alternative - Use Service Account Key (Not Recommended)

If IAM signing still doesn't work, use a service account key stored in Secret Manager:

```bash
# Create a service account with signing ability
gcloud iam service-accounts create gcs-signer \
  --display-name="GCS URL Signer"

# Grant it storage permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:gcs-signer@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# Create key
gcloud iam service-accounts keys create secrets/gcs-signer-key.json \
  --iam-account=gcs-signer@$PROJECT_ID.iam.gserviceaccount.com

# Store in Secret Manager
gcloud secrets create gcs-signer-key --data-file=secrets/gcs-signer-key.json

# Grant Cloud Run access to secret
gcloud secrets add-iam-policy-binding gcs-signer-key \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor"

# Delete local key file
rm secrets/gcs-signer-key.json
```

The code already checks Secret Manager for `gcs-signer-key` (see `backend/infrastructure/gcs.py` lines 40-77).

## How to Test

### After applying IAM permissions:

1. **Restart Cloud Run service** (to pick up new permissions):
```bash
gcloud run services update podcast-api --region=us-west1 --no-traffic
```

2. **Try uploading** a file through the web UI

3. **Check logs** for errors:
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api" \
  --limit=50 --format=json | jq '.[] | select(.textPayload | contains("sign"))'
```

### Expected log messages (success):
```
[INFO] No private key available; using IAM-based signing for PUT
[DEBUG] Generated signed URL using IAM signer
```

### Error log messages to watch for:
```
[ERROR] IAM-based signing failed: Permission denied on IAM Credentials API
[ERROR] Failed to sign URL for gs://ppp-media-us-west1/...: 403
```

## Verify the Fix

1. Upload should complete successfully
2. No 403 errors in browser console
3. File appears in GCS bucket
4. MediaItem created in database

Check GCS:
```bash
gsutil ls gs://ppp-media-us-west1/{USER_ID}/main_content/
```

## Fallback: Disable Direct Upload

If IAM signing can't be fixed immediately, force the system to use standard upload:

Edit `backend/api/routers/media.py` - in the `presign_upload` function, change line 646:

```python
# Force 501 to always use standard upload
if True:  # Change this to disable presign
    raise HTTPException(
        status_code=501,
        detail="Direct upload not available, use standard upload"
    )
```

This will make ALL uploads go through the standard multipart endpoint, which works but has a 32MB limit.

## Status

- [ ] Grant IAM permissions to Cloud Run service account
- [ ] Test upload functionality
- [ ] Verify in logs that IAM signing is working
- [ ] Confirm file appears in GCS and database

## Additional Notes

**Why IAM signing?**
- Cloud Run uses Compute Engine credentials
- These don't include private keys
- IAM Credentials API signs blobs remotely
- Requires `iam.serviceAccountTokenCreator` role

**Why not just use public URLs?**
- Public URLs work for GET (bucket is readable)
- Public URLs DON'T work for PUT/POST (no write permission)
- Signed URLs needed for uploads

**Direct upload benefits:**
- No 32MB Cloud Run request limit
- Faster uploads (direct to GCS)
- Less server load
- Progress tracking still works
