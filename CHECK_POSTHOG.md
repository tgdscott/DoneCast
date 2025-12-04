# PostHog Diagnostic Steps

## Issue
PostHog returns 401 Unauthorized despite correct key in Secret Manager and successful deployment.

## Root Cause Analysis

### Duplicate Initialization Found
- ❌ `frontend/src/posthog.js` exists but is NOT imported (orphaned file)
- ✅ `frontend/src/main.jsx` uses `PostHogProvider` correctly

### Quick Browser Check

Open your browser console on the production site and run:
```javascript
// Check if PostHog is initialized
console.log('PostHog loaded:', window.posthog?.__loaded);

// Check what key is being used (first 10 chars only for security)
console.log('Key prefix:', window.posthog?.config?.token?.substring(0, 10));

// Expected: phc_7CVrQC
```

### If Key is Wrong or Undefined

This means the `VITE_POSTHOG_KEY` wasn't baked into the build. Verify:

1. **Check the build args were passed:**
   ```bash
   gcloud builds list --limit=1 --format="value(substitutions)"
   ```

2. **Verify the secret exists:**
   ```bash
   gcloud secrets versions access latest --secret="VITE_POSTHOG_KEY"
   ```

3. **Force rebuild the frontend:**
   Since the secret might not have been available during build time, you may need to rebuild just the frontend:
   ```powershell
   .\deploy-frontend-only.ps1
   ```

## Recommended Actions

1. **Delete orphaned file:** `frontend/src/posthog.js` (not currently used but could cause confusion)
2. **Check browser console** using the commands above
3. **If key is wrong/missing:** Redeploy frontend only to ensure fresh build with correct secret
