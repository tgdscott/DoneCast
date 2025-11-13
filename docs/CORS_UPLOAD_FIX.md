# CORS Upload Fix - Production Issue

## Problem

Users experiencing upload failures in production with the following errors:

1. **CORS Policy Error:**
   ```
   Access to XMLHttpRequest at 'https://storage.googleapis.com/ppp-media-us-west1/...' 
   from origin 'https://app.podcastplusplus.com' has been blocked by CORS policy: 
   Response to preflight request doesn't pass access control check: 
   No 'Access-Control-Allow-Origin' header is present on the requested resource.
   ```

2. **409 Conflict Errors:**
   ```
   Failed to load resource: the server responded with a status of 409 ()
   ```

3. **Network Errors:**
   ```
   Failed to load resource: net::ERR_FAILED storage.googleapis.com/...
   ```

## Root Cause

The Google Cloud Storage bucket CORS configuration was missing `https://app.podcastplusplus.com`, which is the production frontend domain. When the frontend attempts direct uploads to GCS (for files >25MB to avoid Cloud Run's 32MB limit), the browser blocks the request due to CORS policy.

The CORS configuration only included:
- `https://podcastplusplus.com`
- `https://getpodcastplus.com`

But the production app runs at `https://app.podcastplusplus.com`, which was not in the allowed origins list.

## Solution

Updated the GCS bucket CORS configuration to include all production domains:

### Files Updated:
1. **`gcs-cors-config.json`** - Main CORS configuration file
2. **`gcs-cors.json`** - Alternative CORS configuration file
3. **`scripts/configure_gcs_cors.ps1`** - Updated documentation in script output

### Changes:
Added the following origins to the CORS configuration:
- `https://app.podcastplusplus.com` (primary production domain)
- `https://www.podcastplusplus.com` (www variant)
- `https://www.getpodcastplus.com` (legacy www variant)

## Deployment Steps

### 1. Apply CORS Configuration to GCS Bucket

Run the PowerShell script to apply the updated CORS configuration:

```powershell
cd scripts
.\configure_gcs_cors.ps1
```

Or manually apply using gcloud:

```powershell
gcloud storage buckets update gs://ppp-media-us-west1 --cors-file="gcs-cors-config.json"
```

### 2. Verify CORS Configuration

Check that the CORS configuration was applied correctly:

```powershell
gcloud storage buckets describe gs://ppp-media-us-west1 --format="json(cors_config)"
```

You should see all production domains in the `origin` array:
- `https://app.podcastplusplus.com`
- `https://podcastplusplus.com`
- `https://www.podcastplusplus.com`
- `https://getpodcastplus.com`
- `https://www.getpodcastplus.com`

### 3. Test Upload

1. Navigate to `https://app.podcastplusplus.com`
2. Try uploading a file (especially one >25MB to test direct GCS upload)
3. Verify the upload completes without CORS errors
4. Check browser console for any remaining errors

## Expected Behavior After Fix

**Before:**
- Browser blocks direct GCS uploads with CORS error
- Upload fails with "Network connection issue" message
- Console shows CORS policy errors

**After:**
- Browser allows direct GCS uploads from `https://app.podcastplusplus.com`
- Uploads proceed normally
- No CORS errors in console

## Additional Notes

### 409 Errors
The 409 errors seen in the console may be related to:
- Duplicate file name conflicts during registration
- Race conditions in upload registration
- These are separate from the CORS issue and may need additional investigation if they persist after the CORS fix

### Direct Upload Flow
For files >25MB, the frontend uses a direct upload flow:
1. Frontend calls `/api/media/upload/{category}/presign` to get signed URL
2. Frontend uploads directly to GCS using the signed URL (requires CORS)
3. Frontend calls `/api/media/upload/{category}/register` to register the uploaded file

This flow bypasses Cloud Run's 32MB request body limit but requires proper CORS configuration.

## Related Files
- `gcs-cors-config.json` - Main CORS configuration
- `gcs-cors.json` - Alternative CORS configuration
- `scripts/configure_gcs_cors.ps1` - Deployment script
- `frontend/src/lib/directUpload.js` - Frontend direct upload implementation
- `backend/api/routers/gcs_uploads.py` - Backend presign endpoint

