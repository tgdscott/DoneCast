# Permanent GCS Upload Fix

## Problem
Files larger than ~25MB were failing to upload due to Cloud Run's 32MB request body limit. The multipart/form-data encoding adds overhead, so even 28MB files exceeded the limit.

## Root Cause
Cloud Run has a hard 32MB limit on HTTP request bodies. When files are uploaded via standard multipart/form-data, the encoding overhead (headers, boundaries, base64 encoding) pushes the total request size over this limit.

## Permanent Solution

### 1. Direct GCS Upload with Signed URLs
Implemented a direct upload flow that bypasses Cloud Run for the file transfer:
- Frontend requests a signed URL from the backend (`/api/media/upload/{category}/presign`)
- Backend generates a signed URL using service account credentials from Secret Manager
- Frontend uploads directly to GCS using the signed URL
- Frontend registers the upload with the backend (`/api/media/upload/{category}/register`)

### 2. Service Account Key Configuration
The backend uses a service account key stored in Secret Manager to sign URLs:
- **Secret name**: `gcs-signer-key`
- **Service account**: `gcs-media-signer@podcast612.iam.gserviceaccount.com`
- **Environment variable**: `GCS_SIGNER_KEY_JSON` (mounted from Secret Manager in Cloud Run)

### 3. Credential Loading
The code attempts to load credentials in this order:
1. `GOOGLE_APPLICATION_CREDENTIALS` (local development)
2. `GCS_SIGNER_KEY_JSON` environment variable (Cloud Run - resolved from Secret Manager)
3. Direct Secret Manager access (fallback)

### 4. Signing Method
- **Primary**: Service account key with private key (from Secret Manager)
- **Fallback**: IAM-based signing (requires `iam.serviceAccountTokenCreator` role)

## Configuration Status

✅ **Secret exists**: `gcs-signer-key` in Secret Manager
✅ **Secret is valid**: Contains service account key JSON with private key
✅ **Cloud Run has access**: Service account `524304361363-compute@developer.gserviceaccount.com` can access the secret
✅ **Service account has permissions**: `gcs-media-signer@podcast612.iam.gserviceaccount.com` has `storage.objectAdmin` role
✅ **Cloud Run is configured**: `GCS_SIGNER_KEY_JSON` is mounted as environment variable

## Implementation Details

### Backend Changes

#### `backend/infrastructure/gcs.py`
- Enhanced `_get_signing_credentials()` with better logging and error handling
- Updated `_generate_signed_url()` to support custom headers and use loaded credentials
- Improved IAM-based signing fallback with header support

#### `backend/api/routers/media.py`
- Updated `presign_upload()` endpoint to:
  - Check if credentials are available before attempting to sign
  - Use PUT method for direct uploads (simpler than resumable)
  - Provide detailed error messages and logging
  - Return 501 (Not Implemented) if signing fails, allowing frontend to fall back

### Frontend Changes
- `frontend/src/lib/directUpload.js` already handles direct upload flow
- Automatically prefers direct upload for files >25MB
- Falls back to standard upload if direct upload is not available

## Testing

### Verify Secret
```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_gcs_signer_secret.ps1
```

### Verify Configuration
```powershell
powershell -ExecutionPolicy Bypass -File scripts/fix_gcs_upload_complete.ps1
```

### Test Upload
1. Upload a file >25MB through the web UI
2. Check Cloud Run logs for:
   - `✅ Signing credentials loaded successfully`
   - `✅ Generated signed URL using loaded service account credentials`
   - `✅ Successfully generated PUT upload URL`

## Deployment

The fix is already configured in `cloudbuild.yaml`:
```yaml
--set-secrets="...,GCS_SIGNER_KEY_JSON=gcs-signer-key:latest,..."
```

After deploying, the service will automatically use the secret for signing URLs.

## Troubleshooting

### If uploads still fail with 501:

1. **Check Cloud Run logs** for credential loading errors:
   ```bash
   gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api" --limit=50 --format=json | jq '.[] | select(.textPayload | contains("GCS_SIGNER_KEY_JSON"))'
   ```

2. **Verify secret is accessible**:
   ```bash
   gcloud secrets versions access latest --secret=gcs-signer-key --project=podcast612
   ```

3. **Check service account permissions**:
   ```bash
   gcloud projects get-iam-policy podcast612 --flatten="bindings[].members" --filter="bindings.members:serviceAccount:gcs-media-signer@podcast612.iam.gserviceaccount.com"
   ```

4. **Restart Cloud Run service** to pick up new secret:
   ```bash
   gcloud run services update podcast-api --region=us-west1 --project=podcast612 --no-traffic
   gcloud run services update-traffic podcast-api --region=us-west1 --project=podcast612 --to-latest
   ```

### Common Issues

- **"Signed URL generation returned None"**: Credentials not loaded - check `GCS_SIGNER_KEY_JSON` is set
- **"No private key available"**: Secret doesn't contain private key - verify secret content
- **"IAM-based signing failed"**: Service account doesn't have `iam.serviceAccountTokenCreator` role

## Benefits

1. **Bypasses Cloud Run limit**: Files are uploaded directly to GCS, not through Cloud Run
2. **Supports large files**: PUT signed URLs work for files up to ~5GB
3. **Secure**: Uses signed URLs with expiration (1 hour)
4. **Reliable**: Falls back to standard upload if direct upload is unavailable
5. **Permanent**: Uses service account key from Secret Manager, not temporary workarounds

## Future Improvements

- Consider implementing resumable uploads for files >100MB (better for unreliable networks)
- Add progress tracking for direct uploads
- Implement chunked uploads for very large files (>5GB)

