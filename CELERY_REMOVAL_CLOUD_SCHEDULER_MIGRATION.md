# Celery Removal and Cloud Scheduler Migration

**Date:** October 30, 2025  
**Status:** ✅ Complete - Ready for deployment

## Summary

Removed Celery task queue system and migrated maintenance tasks to Cloud Scheduler. This eliminates the need for RabbitMQ/Redis broker and reduces infrastructure costs by ~$80-150/month.

## Changes Made

### 1. Created HTTP Endpoints for Maintenance Tasks

**File:** `backend/api/routers/tasks.py`

Added two new endpoints:
- `POST /api/tasks/maintenance/purge-expired-uploads`
- `POST /api/tasks/maintenance/purge-episode-mirrors`

Both endpoints:
- Accept Cloud Scheduler OIDC tokens OR legacy TASKS_AUTH header
- Run synchronously (no background workers needed)
- Return JSON results with counts of items processed

### 2. Removed Celery from Dependencies

**File:** `backend/requirements.txt`

Removed:
- `celery==5.5.3` ❌

This also removes Celery's dependencies (kombu, amqp, billiard, vine).

### 3. Created Cloud Scheduler Setup Script

**File:** `scripts/setup_cloud_scheduler.ps1`

PowerShell script to create 2 Cloud Scheduler jobs:
1. **purge-expired-uploads** - Daily at 2:00 AM PT
2. **purge-episode-mirrors** - Daily at 2:00 AM PT

**Cost:** $0/month (first 3 jobs are free)

### 4. Fixed Dashboard React Import Issue

**File:** `frontend/src/components/dashboard.jsx`

Added missing `React` import (line 39) to fix "Cannot access 'L' before initialization" error.

**Before:**
```jsx
import { useState, useEffect, useMemo, useCallback, useRef, lazy, Suspense } from "react";
```

**After:**
```jsx
import React, { useState, useEffect, useMemo, useCallback, useRef, lazy, Suspense } from "react";
```

## Files That Can Be Safely Deleted

**DO NOT delete these yet - user will handle via git after testing:**

```
backend/worker/tasks/app.py              # Celery app configuration
backend/worker/tasks/maintenance.py      # Old Celery maintenance tasks (replaced by HTTP endpoints)
backend/worker/tasks/publish.py          # Unused Spreaker publish task (legacy)
```

**Keep these files (still used by production):**
```
backend/worker/tasks/__init__.py         # Has inline assembly fallback
backend/worker/tasks/transcription.py    # Referenced by some routes (not called)
backend/worker/tasks/assembly/           # Contains inline orchestrator (still used)
```

## Deployment Steps

### Step 1: Deploy Code Changes

```powershell
# Commit changes
git add .
git commit -m "Remove Celery, migrate to Cloud Scheduler"

# Build and deploy
gcloud builds submit --config=cloudbuild.yaml --region=us-west1
```

### Step 2: Setup Cloud Scheduler Jobs

**IMPORTANT:** Update `SERVICE_URL` in the script first!

```powershell
# Get your Cloud Run service URL
gcloud run services describe podcast-api --region=us-west1 --format="value(status.url)"

# Edit scripts/setup_cloud_scheduler.ps1 and update SERVICE_URL variable

# Run setup script
.\scripts\setup_cloud_scheduler.ps1
```

### Step 3: Verify Jobs Created

```powershell
# List jobs
gcloud scheduler jobs list --location=us-west1

# Test a job manually
gcloud scheduler jobs run purge-expired-uploads --location=us-west1

# Check Cloud Run logs for execution
gcloud logging read 'resource.type="cloud_run_revision" 
  AND resource.labels.service_name="podcast-api" 
  AND textPayload=~"\[purge\]"' 
  --limit=20 --format=json
```

### Step 4: Monitor First Execution

Wait until 2:00 AM PT the next day, then check logs:

```powershell
gcloud logging read 'resource.type="cloud_run_revision" 
  AND resource.labels.service_name="podcast-api" 
  AND jsonPayload.message=~"purge"' 
  --limit=50 --format=json
```

## Architecture Before & After

### Before (Celery)
```
User → API → Celery Task Queue → RabbitMQ → Celery Worker
                                   ↓
                              (Requires broker)
                              (~$50-100/month)
```

### After (Cloud Scheduler)
```
Cloud Scheduler → HTTP POST → API Endpoint → Runs synchronously
                               ↓
                        (No broker needed)
                        ($0/month - free tier)
```

## What Still Uses Background Processing?

- **Episode Assembly:** Cloud Tasks (not Celery)
- **Transcription:** Cloud Tasks (not Celery)
- **Chunk Processing:** Cloud Tasks (not Celery)

**Nothing uses Celery anymore.**

## Rollback Plan (if needed)

If maintenance tasks fail:

1. Restore `celery==5.5.3` to requirements.txt
2. Revert `backend/api/routers/tasks.py` changes
3. Redeploy
4. Run old Celery worker: `celery -A worker.tasks worker --loglevel=info`

But this should NOT be necessary - the new endpoints are simpler and more reliable.

## Cost Savings

- **Before:** ~$80-150/month (RabbitMQ + always-on worker)
- **After:** $0/month (Cloud Scheduler free tier)
- **Savings:** ~$960-1,800/year 💰

## Testing Checklist

- [ ] Deploy code changes
- [ ] Run `setup_cloud_scheduler.ps1` script
- [ ] Verify jobs created in Cloud Console
- [ ] Manually trigger one job: `gcloud scheduler jobs run purge-expired-uploads --location=us-west1`
- [ ] Check Cloud Run logs for `[purge]` messages
- [ ] Verify no errors in logs
- [ ] Wait for next scheduled run (2:00 AM PT)
- [ ] Check logs again the next morning
- [ ] Verify old recordings are being cleaned up (check database)

## Related Documentation

- Cloud Scheduler: https://cloud.google.com/scheduler/docs
- Cloud Run OIDC Auth: https://cloud.google.com/run/docs/authenticating/service-to-service
- Original Celery config: `backend/worker/tasks/app.py` (to be deleted after testing)

---

**Status:** Ready for testing in production. No users affected by this change (maintenance tasks run in background).
