# Frontend-Only Deployment Guide

## When to Use Frontend-Only Deployment

Use frontend-only deployment when:
- ✅ You've only changed React/Vite frontend code
- ✅ You want faster deployments (skips API rebuild)
- ✅ Backend is stable and doesn't need redeployment
- ❌ **DON'T** use if you changed backend code or dependencies

## Option 1: Cloud Build (Recommended for Production)

**Best for:** Production deployments, CI/CD pipelines

```powershell
# Deploy frontend only using Cloud Build
gcloud builds submit --config=cloudbuild-frontend-only.yaml --region=us-west1
```

**Advantages:**
- Uses Cloud Build infrastructure
- Same build environment as full deployments
- Automatic logging and audit trail
- Handles secrets from Secret Manager

**Time:** ~3-5 minutes

## Option 2: Local PowerShell Script

**Best for:** Quick local testing, development iterations

```powershell
# Run the PowerShell deployment script
.\deploy-frontend-only.ps1
```

**Advantages:**
- Faster for local development
- No Cloud Build quota usage
- Direct control over build process

**Requirements:**
- Docker Desktop running
- `gcloud` CLI authenticated
- Permissions to push to Artifact Registry

**Time:** ~2-4 minutes (depending on Docker cache)

## Full Deployment (Both Frontend + Backend)

When you need to deploy both services:

```powershell
# Full deployment (API + Web)
gcloud builds submit --config=cloudbuild.yaml --region=us-west1
```

**Use when:**
- Backend code changed
- Database migrations needed
- Python dependencies updated
- Secrets or environment variables changed

**Time:** ~8-12 minutes

## Deployment Comparison

| Method | Time | Use Case | Rebuilds API? | Rebuilds Frontend? |
|--------|------|----------|---------------|-------------------|
| **Frontend-Only (Cloud Build)** | 3-5 min | React changes only | ❌ No | ✅ Yes |
| **Frontend-Only (PowerShell)** | 2-4 min | Quick local test | ❌ No | ✅ Yes |
| **Full Deployment** | 8-12 min | Backend + Frontend changes | ✅ Yes | ✅ Yes |

## What Gets Deployed

### Frontend Service (`podcast-web`)
- **Service URL:** https://app.podcastplusplus.com
- **Tech:** React 18 + Vite + TailwindCSS
- **Build:** Multi-stage Dockerfile (`frontend/Dockerfile`)
- **Runtime:** Nginx serving static files
- **Build Args:**
  - `VITE_GOOGLE_CLIENT_ID` - Google OAuth client ID
  - `VITE_API_BASE` - API base URL (https://api.podcastplusplus.com)

### Not Deployed
- Backend API service (`podcast-api`)
- Database changes
- Cloud Tasks or background workers

## Troubleshooting

### "Docker build failed"
- Ensure Docker Desktop is running
- Check `frontend/Dockerfile` syntax
- Verify `frontend/package.json` exists

### "Failed to push image"
- Check `gcloud auth login` is active
- Verify permissions: `roles/artifactregistry.writer`
- Check project ID is correct (`podcast612`)

### "Cloud Run deployment failed"
- Verify service exists: `gcloud run services list --region=us-west1`
- Check permissions: `roles/run.admin`
- View logs: `gcloud logging read "resource.type=cloud_run_revision"`

### Frontend shows old version after deploy
- Clear browser cache (Ctrl+Shift+R)
- Check service URL points to new revision:
  ```powershell
  gcloud run services describe podcast-web --region=us-west1 --format="value(status.url,status.latestCreatedRevisionName)"
  ```
- Wait 1-2 minutes for CDN cache invalidation

## Verification Steps

After deployment:

1. **Check service is running:**
   ```powershell
   gcloud run services describe podcast-web --region=us-west1 --format="value(status.conditions.status)"
   ```
   Should show: `True True True`

2. **Get service URL:**
   ```powershell
   gcloud run services describe podcast-web --region=us-west1 --format="value(status.url)"
   ```

3. **Test frontend:**
   - Open https://app.podcastplusplus.com
   - Check browser console for errors
   - Verify intro/outro continue button works (recent fix)

4. **View logs:**
   ```powershell
   gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=podcast-web" --limit=50
   ```

## Recent Frontend Changes

### Oct 14, 2025 - Intro/Outro Continue Button Fix
- **File:** `frontend/src/pages/Onboarding.jsx`
- **Change:** Fixed validation logic for intro/outro step
- **Deploy:** Frontend-only deployment is sufficient
- **See:** `INTRO_OUTRO_CONTINUE_FIX_OCT14.md`

## Files

- **`cloudbuild-frontend-only.yaml`** - Cloud Build config for frontend-only deployment
- **`deploy-frontend-only.ps1`** - PowerShell script for local deployment
- **`cloudbuild.yaml`** - Full deployment (API + Frontend)
- **`frontend/Dockerfile`** - Multi-stage build for React app

## Notes

- Frontend builds are **stateless** - no database changes
- Images are tagged with `:latest` and `:BUILD_ID`
- Build ID format: `manual-YYYYMMDD-HHmmss` (local) or Cloud Build ID
- All frontend env vars are **build-time** (baked into static files)

---

**Need help?** Check the main `README.md` or project documentation.
