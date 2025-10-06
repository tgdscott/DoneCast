# Intern Feature 404 Fix - Deployment Needed

## Problem
The frontend shows "Intern review unavailable - Unable to prepare intern commands right now" and logs show:
```
Failed to load resource: the server responded with a status of 404 ()
api.podcastplusplus.com/api/intern/prepare-by-file:1
```

## Root Cause
The `/api/intern/prepare-by-file` endpoint exists in the code (`backend/api/routers/intern.py` line 262) but the **current Cloud Run deployment (revision 00448-6pw) was created before this endpoint was added**.

The intern router was added in commit `b3dec6d` (October 4, 2025) but the deployed revision is older.

## Solution
Deploy the latest code to Cloud Run to include the intern router endpoints.

### Quick Deploy Command
```powershell
# Submit a build to Cloud Build which will deploy to Cloud Run
gcloud builds submit --config=cloudbuild.yaml --region=us-west1
```

### What Will Be Deployed
1. **Intern router** with endpoints:
   - `POST /api/intern/prepare-by-file` - Prepare intern command review data
   - `POST /api/intern/prepare-by-episode` - Prepare for existing episodes
   - `POST /api/intern/execute` - Execute approved intern commands

2. **Dependencies** (already in requirements.txt):
   - `python-jose[cryptography]` - JWT authentication
   - `passlib[bcrypt]==1.7.4` - Password hashing
   - `pydub` - Audio processing
   - All other required packages

### Verification After Deployment
1. Wait for deployment to complete (creates new revision like `00451-xxx` or `00452-xxx`)
2. Check the endpoint is available:
   ```powershell
   curl -X POST https://api.podcastplusplus.com/api/intern/prepare-by-file `
     -H "Content-Type: application/json" `
     -H "Authorization: Bearer YOUR_TOKEN" `
     -d '{"filename":"test.mp3"}'
   ```
3. Should return 400/422 (validation error) instead of 404 if endpoint exists

### Timeline
- **Current revision**: 00448-6pw (missing intern endpoints)
- **Intern router added**: Oct 4, 2025 (commit b3dec6d)
- **Action needed**: Deploy to get revision 00451+ with intern support

## Alternative: Check Why Previous Deploys Didn't Include It
If recent deploys happened but didn't include the intern router, check:
1. Cloud Build logs for `_safe_import` warnings
2. Missing dependencies causing import failures
3. Build caching issues preventing code updates

But most likely, **we just need to deploy** to get the latest code live.
