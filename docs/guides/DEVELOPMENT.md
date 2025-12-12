

# DEV_SCRIPTS_AUTH_CHECK_OCT17.md

# Dev Scripts Auth Check Improvement - October 17, 2025

## Problem
Development startup scripts were **always** prompting for Google Cloud authentication, even when credentials were still valid. This was exhausting when restarting services frequently during development.

### Symptoms
- Every `dev_start_api.ps1` run → browser auth flow
- Every `dev_start_all.ps1` run → browser auth flow  
- Every `start_sql_proxy.ps1` run → browser auth flow
- Multiple restarts per hour = multiple auth prompts

## Solution: Smart Auth Check

### Before
```powershell
# ALWAYS authenticate (even if already logged in)
& gcloud auth application-default login --quiet
```

### After
```powershell
# Check if credentials exist and are valid
$adcPath = "$env:APPDATA\gcloud\application_default_credentials.json"
$needsAuth = $true

if (Test-Path $adcPath) {
    # Test if credentials are still valid
    $authTest = & gcloud auth application-default print-access-token 2>&1
    if ($LASTEXITCODE -eq 0 -and $authTest -match '^ya29\.') {
        Write-Host "   Existing credentials are valid" -ForegroundColor Green
        $needsAuth = $false
    }
}

if ($needsAuth) {
    # Only authenticate if needed
    & gcloud auth application-default login --quiet
}
```

## How It Works

1. **Check credentials file**: Look for `application_default_credentials.json` in AppData
2. **Test validity**: Try to get an access token using existing credentials
3. **Verify token format**: Ensure token starts with `ya29.` (Google OAuth2 format)
4. **Skip if valid**: Don't prompt for auth if credentials work
5. **Re-auth if needed**: Only launch browser if credentials expired or missing

## Files Modified
1. **`scripts/dev_start_api.ps1`** - API startup script
2. **`scripts/dev_start_all.ps1`** - Unified dev environment startup
3. **`scripts/start_sql_proxy.ps1`** - Cloud SQL Proxy startup

## User Experience

### Scenario 1: Fresh Start (No Credentials)
```
Checking Google Cloud authentication...
   Authenticating with Google Cloud...
   (Browser opens for OAuth flow)
   Google Cloud authentication successful
```

### Scenario 2: Valid Credentials Exist
```
Checking Google Cloud authentication...
   Existing credentials are valid ✓
(Script continues immediately, no browser)
```

### Scenario 3: Expired Credentials
```
Checking Google Cloud authentication...
   Existing credentials are expired
   Authenticating with Google Cloud...
   (Browser opens for re-authentication)
   Google Cloud authentication successful
```

## Benefits
- **No more unnecessary auth prompts** during frequent restarts
- **Faster script execution** (no browser launch overhead)
- **Still secure**: Validates credentials before use
- **Developer-friendly**: Only prompts when actually needed

## Testing Commands

Test the improved scripts:
```powershell
# Test API startup (should skip auth if valid)
.\scripts\dev_start_api.ps1

# Test unified startup (should skip auth if valid)
.\scripts\dev_start_all.ps1

# Test SQL proxy (should skip auth if valid)
.\scripts\start_sql_proxy.ps1
```

## Technical Notes

### Token Validation
- Uses `gcloud auth application-default print-access-token` to test credentials
- Validates token format (starts with `ya29.`) to ensure it's a valid Google OAuth2 token
- Captures stderr/stdout to prevent noise when credentials invalid

### Credential Location
- **Windows**: `%APPDATA%\gcloud\application_default_credentials.json`
- File contains OAuth2 refresh token that can generate access tokens
- Expires after ~7 days of inactivity (Google's default)

### Exit Codes
- **0**: Credentials valid, token generated successfully
- **Non-zero**: Credentials missing/expired, need re-authentication

---

**Status**: ✅ Implemented - Ready for immediate use
**Impact**: Dramatically improves dev workflow ergonomics
**Priority**: Quality of Life (makes frequent dev restarts much less painful)


---


# DEV_WORKER_SETUP.md

# Dev Server - Using Proxmox Worker for Testing

## Overview

This configuration allows the dev server to send assembly tasks directly to the Proxmox worker server instead of running them locally. This is useful for testing the worker server without deploying to production.

## Setup

### 1. Add Environment Variables to Your Dev Environment

Add these to your `.env.local` or `.env` file in the `backend/` directory:

```bash
# Enable using worker server in dev mode
USE_WORKER_IN_DEV=true

# Worker server URL (your Proxmox server via Cloudflared)
WORKER_URL_BASE=https://assemble.podcastplusplus.com

# TASKS_AUTH must match the value on the worker server
TASKS_AUTH=<your-tasks-auth-secret>
```

### 2. Get TASKS_AUTH Value

Get the TASKS_AUTH value from Secret Manager:

```bash
gcloud secrets versions access latest --secret=TASKS_AUTH --project=podcast612
```

Or if you know it's the same as on the worker server, use that value.

### 3. Verify Worker Server is Accessible

Test that you can reach the worker server from your dev machine:

```bash
curl https://assemble.podcastplusplus.com/health
```

Should return: `{"status":"healthy","service":"worker"}`

### 4. Start Your Dev Server

Start your dev server as usual. Assembly tasks will now be sent to the worker server instead of running locally.

## How It Works

1. When `USE_WORKER_IN_DEV=true` is set, the dev server checks if `WORKER_URL_BASE` is configured
2. For assembly (`/api/tasks/assemble`) and chunk processing (`/api/tasks/process-chunk`) tasks, it makes a direct HTTP POST to the worker server
3. The request includes the `X-Tasks-Auth` header for authentication
4. The task runs on the worker server, and logs appear in the worker server logs

## Logging

You'll see these messages in your dev server console:

```
DEV MODE: Sending /api/tasks/assemble to worker server at https://assemble.podcastplusplus.com/api/tasks/assemble
DEV MODE: POST https://assemble.podcastplusplus.com/api/tasks/assemble with timeout 1800.0s
DEV MODE: Worker server responded with status 200
```

## Monitoring

### Dev Server Logs
Watch your dev server console for:
- `DEV MODE: Sending ... to worker server`
- `DEV MODE: Worker server responded with status ...`
- Any error messages if the worker call fails

### Worker Server Logs
On your Proxmox server, watch the worker logs:

```bash
docker-compose -f docker-compose.worker.yml logs -f worker
```

Or if running directly:
```bash
# Check application logs
tail -f /path/to/worker/logs
```

Look for:
- `event=worker.assemble.start` - Assembly started
- `event=worker.assemble.done` - Assembly completed
- `event=worker.assemble.error` - Assembly failed

## Troubleshooting

### Worker Server Not Responding

**Symptom**: Timeout or connection error

**Check**:
1. Worker server is running: `curl https://assemble.podcastplusplus.com/health`
2. Cloudflared tunnel is running on Proxmox
3. Worker service is listening on port 8080

### Authentication Failed

**Symptom**: `401 Unauthorized` error

**Check**:
1. `TASKS_AUTH` value matches between dev server and worker server
2. Worker server has `APP_ENV=production` set (so it requires auth)
3. Worker server has `TASKS_AUTH` environment variable set

### Wrong URL

**Symptom**: `404 Not Found` error

**Check**:
1. `WORKER_URL_BASE` is set correctly: `https://assemble.podcastplusplus.com`
2. No trailing slash in `WORKER_URL_BASE`
3. Worker server has the endpoint at `/api/tasks/assemble`

## Disabling

To disable and go back to local execution, either:

1. Remove `USE_WORKER_IN_DEV` from your `.env` file, or
2. Set `USE_WORKER_IN_DEV=false`

## Notes

- This only affects assembly and chunk processing tasks
- Transcription tasks still run locally in dev mode
- The HTTP call is made in a background thread to avoid blocking
- Timeout is set to 30 minutes (1800s) for assembly tasks
- This bypasses Cloud Tasks entirely - it's a direct HTTP call



---


# START-DEV.md

# Quick Start Guide for Development

## Starting Development Servers

You have **three easy options** to start the development servers:

### Option 1: Use Batch Files (Easiest - No PowerShell Issues)
Just double-click or run:
```batch
start-all.bat
```
Or individually:
```batch
start-frontend.bat
start-backend.bat
```

### Option 2: Run PowerShell with Bypass Flag
```powershell
powershell -ExecutionPolicy Bypass -File .\start-all.ps1
```
Or individually:
```powershell
powershell -ExecutionPolicy Bypass -File .\start-frontend.ps1
powershell -ExecutionPolicy Bypass -File .\start-backend.ps1
```

### Option 3: Set Execution Policy (Permanent Fix)
If you want to run PowerShell scripts directly without flags:

1. Open PowerShell as Administrator (or just regular PowerShell for CurrentUser scope)
2. Run:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
```
3. Then you can run:
```powershell
.\start-all.ps1
```

## What Each Script Does

- **start-all.bat / start-all.ps1**: Starts Cloud SQL Proxy, Backend API, and Frontend in separate windows
- **start-backend.bat / start-backend.ps1**: Starts only the Backend API server (http://127.0.0.1:8000)
- **start-frontend.bat / start-frontend.ps1**: Starts only the Frontend dev server (http://127.0.0.1:5173)

## Recommended: Use the Batch Files
The `.bat` files bypass all PowerShell execution policy issues and work immediately!




---


# TROUBLESHOOT_DEV_WORKER.md

# Troubleshooting Dev Worker Configuration

## Issue: USE_WORKER_IN_DEV not working

If you set `USE_WORKER_IN_DEV=true` but it's still processing locally, check these:

## 1. Verify .env.local File Location

The `.env.local` file should be in the `backend/` directory:

```
PodWebDeploy/
  backend/
    .env.local    ← Should be here
    api/
    infrastructure/
    ...
```

## 2. Verify Environment Variables Are Set

Check your `.env.local` file has these lines (no quotes needed):

```bash
USE_WORKER_IN_DEV=true
WORKER_URL_BASE=https://assemble.podcastplusplus.com
TASKS_AUTH=<your-secret-here>
```

**Common mistakes:**
- ❌ `USE_WORKER_IN_DEV="true"` (quotes not needed)
- ❌ `USE_WORKER_IN_DEV = true` (spaces around =)
- ❌ Missing `WORKER_URL_BASE`
- ❌ Wrong file location

## 3. Restart Your Dev Server

**IMPORTANT**: After adding/changing environment variables, you MUST restart your dev server for changes to take effect.

## 4. Check Debug Output

When you try to assemble, you should see in your console:

```
DEV MODE: Checking worker config - USE_WORKER_IN_DEV=true (parsed=True), WORKER_URL_BASE=https://assemble.podcastplusplus.com, path=/api/tasks/assemble
```

If you see:
- `USE_WORKER_IN_DEV=None` or `USE_WORKER_IN_DEV=false` → Environment variable not loaded
- `WORKER_URL_BASE=None` → WORKER_URL_BASE not set
- `path=/api/tasks/assemble` but `is_worker_task=False` → Path check issue

## 5. Verify .env.local is Being Loaded

Check your dev server startup logs for:

```
[config] Loaded .env.local from /path/to/backend/.env.local
```

If you don't see this, the .env.local file might not be in the right location.

## 6. Manual Test

You can test if the environment variable is loaded by adding this to your code temporarily:

```python
import os
print(f"USE_WORKER_IN_DEV={os.getenv('USE_WORKER_IN_DEV')}")
print(f"WORKER_URL_BASE={os.getenv('WORKER_URL_BASE')}")
```

## 7. Check File Format

Make sure your `.env.local` file:
- Uses `KEY=value` format (no spaces around =)
- No quotes around values (unless the value itself needs quotes)
- No trailing spaces
- Uses Unix line endings (LF, not CRLF)

Example:
```bash
# Good
USE_WORKER_IN_DEV=true
WORKER_URL_BASE=https://assemble.podcastplusplus.com

# Bad
USE_WORKER_IN_DEV = true
USE_WORKER_IN_DEV="true"
USE_WORKER_IN_DEV=true  
```

## 8. Verify Path Check

The code checks if the path contains `/assemble` or `/process-chunk`. The path should be `/api/tasks/assemble` when called from the assembler service.

If you see `is_worker_task=False` in the debug output, the path might be different than expected.

## Quick Fix Checklist

- [ ] `.env.local` is in `backend/` directory
- [ ] `USE_WORKER_IN_DEV=true` (no quotes, no spaces)
- [ ] `WORKER_URL_BASE=https://assemble.podcastplusplus.com` is set
- [ ] `TASKS_AUTH=<secret>` is set
- [ ] Dev server was restarted after adding env vars
- [ ] Check console output for debug messages
- [ ] Verify worker server is accessible: `curl https://assemble.podcastplusplus.com/health`

## Still Not Working?

Run the assembly again and check the console output. You should see:

```
DEV MODE: Checking worker config - USE_WORKER_IN_DEV=... WORKER_URL_BASE=... path=...
DEV MODE: Worker config invalid or not a worker task - will use local dispatch. use_worker_in_dev=... worker_url_base=... is_worker_task=...
```

Share that output to diagnose the issue.



---
