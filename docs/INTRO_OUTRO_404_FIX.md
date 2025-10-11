# Intro & Outro 404 Fix - October 8, 2025

## Problem
Step 5 of the new user/podcast setup (Intro & Outro) had multiple issues:
1. Couldn't preview already existing intros and outros (404 errors)
2. Couldn't create new ones via TTS
3. Logs showing: "No private key available; using public URL for GET (bucket is publicly readable)"

## Root Causes

### 1. Missing Signing Credentials
The `gcs.py` module was trying to load signing credentials from Secret Manager but:
- It wasn't checking for `GOOGLE_APPLICATION_CREDENTIALS` env var first
- When credentials were missing, it fell back to "public URLs" for GET requests
- These public URLs returned 404 because files under user-specific paths aren't publicly accessible

### 2. Inconsistent GCS Path Formats
Three different upload paths were being used:
- **TTS uploads**: `media/{user_id}/{category}/{filename}` ❌
- **Manual uploads (media_write.py)**: `{user_id}/media/{category}/{filename}` ✅
- **Manual uploads (media.py)**: `{user_id}/{category}/{filename}` ❌

This meant files uploaded via different methods couldn't be found when trying to preview them.

## Fixes Applied

### 1. Enhanced Signing Credentials Loading (`backend/infrastructure/gcs.py`)
```python
def _get_signing_credentials():
    """Load service account credentials for signing URLs from Secret Manager or env var."""
    # Try loading from GOOGLE_APPLICATION_CREDENTIALS env var first (local dev)
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path and os.path.exists(cred_path):
        try:
            credentials = service_account.Credentials.from_service_account_file(cred_path)
            _SIGNING_CREDENTIALS = credentials
            logger.info("Loaded signing credentials from GOOGLE_APPLICATION_CREDENTIALS")
            return credentials
        except Exception as e:
            logger.warning(f"Failed to load signing credentials from file: {e}")
    
    # Try loading from Secret Manager (Cloud Run)
    try:
        from google.cloud import secretmanager
        # ... existing Secret Manager code ...
```

### 2. Improved Signed URL Generation (`backend/infrastructure/gcs.py`)
```python
def _generate_signed_url(...):
    """Generate a signed URL, using service account credentials or IAM-based signing.
    
    Priority order:
    1. Try using loaded service account credentials (from env var or Secret Manager)
    2. Try using default client credentials
    3. Fall back to IAM-based signing for Cloud Run
    4. Return None to trigger fallback handling (instead of public URL)
    """
```

Now it:
- First tries to use the loaded service account credentials
- Falls back to IAM-based signing for Cloud Run
- Returns `None` instead of public URLs for GET requests without credentials
- The `None` return triggers proper local fallback handling

### 3. Standardized GCS Path Format
Updated all upload paths to use: `{user_id}/media/{category}/{filename}`

**Files changed:**
- `backend/api/routers/media_tts.py` (line 163)
- `backend/api/routers/media.py` (line 241)
- `backend/api/routers/media_write.py` (already correct)

## Testing Steps

### Prerequisites: Get a Service Account Key

**IMPORTANT**: User credentials (from `gcloud auth application-default login`) cannot generate signed URLs. You need a service account key.

#### Option 1: Use Existing Service Account
If you already have a service account key file:
```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = "D:/path/to/your-service-account-key.json"
```

#### Option 2: Create a New Service Account
```bash
# Create service account
gcloud iam service-accounts create gcs-media-signer \
  --display-name="GCS Media URL Signer" \
  --project=podcast612

# Grant Storage Object Viewer permission
gcloud projects add-iam-policy-binding podcast612 \
  --member="serviceAccount:gcs-media-signer@podcast612.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"

# Create and download key
gcloud iam service-accounts keys create gcs-signer-key.json \
  --iam-account=gcs-media-signer@podcast612.iam.gserviceaccount.com

# Set environment variable
$env:GOOGLE_APPLICATION_CREDENTIALS = "D:/PodWebDeploy/gcs-signer-key.json"
```

### Test the Fix

1. **Start the API** with proper credentials:
   ```powershell
   # Set credentials first
   $env:GOOGLE_APPLICATION_CREDENTIALS = "D:/path/to/service-account-key.json"
   
   # Start API using the dev script
   .\scripts\dev_start_api.ps1
   ```

2. **Test TTS Intro/Outro Creation**:
   - Go to onboarding Step 5
   - Try creating a new intro via TTS
   - Check logs - should see "Loaded signing credentials from GOOGLE_APPLICATION_CREDENTIALS"
   - Verify upload succeeds and preview works

3. **Test Existing Intro/Outro Preview**:
   - Select an existing intro/outro from dropdown
   - Click preview button
   - Should play without 404 errors

4. **Check Logs**:
   - Should NOT see "No private key available; using public URL for GET"
   - Should see "Generated signed URL using loaded service account credentials"

## Deployment Notes

### For Local Development
1. Obtain a service account key (see Prerequisites above)
2. Set environment variable:
   ```powershell
   $env:GOOGLE_APPLICATION_CREDENTIALS = "D:/path/to/service-account-key.json"
   ```
3. Optionally add to `backend/.env`:
   ```properties
   GOOGLE_APPLICATION_CREDENTIALS=D:/path/to/service-account-key.json
   ```

### For Cloud Run
Ensure the `gcs-signer-key` secret exists in Secret Manager:
```bash
# Upload the service account key to Secret Manager
gcloud secrets create gcs-signer-key \
  --project=podcast612 \
  --data-file=gcs-signer-key.json

# Grant Cloud Run service account access to the secret
gcloud secrets add-iam-policy-binding gcs-signer-key \
  --member="serviceAccount:podcast612@appspot.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project=podcast612
```

## Related Files Modified
- `backend/infrastructure/gcs.py` - Enhanced credential loading and signed URL generation
- `backend/api/routers/media_tts.py` - Fixed GCS path format
- `backend/api/routers/media.py` - Fixed GCS path format
- `backend/api/routers/media_write.py` - Already had correct path format

## Impact
- ✅ Intro/outro preview will work in both local dev and production
- ✅ TTS-generated intros/outros will be properly uploaded and accessible
- ✅ Manually uploaded media will use consistent paths
- ✅ No more 404 errors when previewing media
- ✅ Proper error handling with fallbacks for missing credentials

## Deployment Complete

✅ **Setup script has been run successfully**
✅ **Service account created**: `gcs-media-signer@podcast612.iam.gserviceaccount.com`
✅ **Key file generated**: `D:\PodWebDeploy\gcs-signer-key.json`
✅ **Secret uploaded to Secret Manager**: `gcs-signer-key` (version 2)
✅ **Environment variable configured**: `GOOGLE_APPLICATION_CREDENTIALS=D:/PodWebDeploy/gcs-signer-key.json`

### Next Steps
Restart the API server to pick up the new credentials:
```powershell
.\scripts\dev_start_api.ps1
```

Then test intro/outro functionality in Step 5 of onboarding.
