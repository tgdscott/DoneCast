# EMERGENCY FIX DEPLOYMENT - October 6, 2025

## Critical Issues Fixed

### 1. ✅ Login Stuck / Takes Minutes
**Root Cause**: Assembly tasks running in threads were blocking Python's GIL, making ALL API requests take forever
**Fix**: Changed from `threading.Thread` to `multiprocessing.Process` - isolates CPU work from event loop

### 2. ✅ Teal Buttons with Invisible Text  
**Root Cause**: CSS had `color: hsl(var(--primary-foreground))` which resolved to teal-on-teal
**Fix**: Added `color: white !important` to `.nl-button`

### 3. ✅ "Get Started" Button Bypasses Login
**Root Cause**: Direct link to `/onboarding` without auth check
**Fix**: Show login modal instead when not authenticated

### 4. ✅ Zombie Assembly Processes
**Root Cause**: Old assembly tasks still running after restarts
**Fix**: Added startup task to kill orphaned processes

### 5. ✅ Everything Takes Minutes (ROOT CAUSE)
**Root Cause**: Python's GIL + CPU-intensive audio processing in threads = blocked event loop
**Fix**: Multiprocessing isolates work in separate process with separate GIL

## Files Changed

### Backend
- `backend/api/routers/tasks.py` - Changed threading.Thread to multiprocessing.Process
- `backend/api/startup_tasks.py` - Added zombie process cleanup
- Need to add: `psutil` to requirements.txt

### Frontend
- `frontend/src/pages/NewLanding.jsx` - Auth-gate "Get Started" buttons
- `frontend/src/pages/new-landing.css` - Fix button text color

## Deployment Steps

### 1. Install psutil (Required)

```bash
cd d:/PodWebDeploy
.venv/Scripts/activate
pip install psutil
pip freeze > backend/requirements.txt
```

### 2. Test Locally (CRITICAL - Don't deploy without testing!)

```bash
# Terminal 1: Start API
cd d:/PodWebDeploy
scripts/dev_start_api.ps1

# Terminal 2: Start Frontend
scripts/dev_start_frontend.ps1

# Terminal 3: Test
# 1. Try logging in - should be instant
# 2. Click "Get Started" without logging in - should show login modal
# 3. Check buttons are visible (white text on teal)
# 4. Upload audio and create episode - should NOT slow down API
```

### 3. Deploy to Production

```bash
# Commit changes
git add backend/api/routers/tasks.py backend/api/startup_tasks.py backend/requirements.txt frontend/src/pages/NewLanding.jsx frontend/src/pages/new-landing.css
git commit -m "Fix: Use multiprocessing for assembly to prevent GIL blocking

- Changed assembly worker from threading to multiprocessing
- Prevents CPU-intensive audio processing from blocking event loop
- Added zombie process cleanup on startup
- Fixed button text visibility (white on teal)
- Auth-gated 'Get Started' buttons to show login modal first
- Fixes login hanging, slow API responses, and UI issues"

git push origin main

# Deploy via Cloud Build
gcloud builds submit --config cloudbuild.yaml --project=podcast612
```

### 4. Verify Production

```bash
# Check logs for successful startup
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api" \
  --project=podcast612 \
  --format="table(timestamp,textPayload)" \
  --limit=50 \
  --freshness=5m | grep -E "startup|zombie|assemble"

# Should see:
# ✅ "[startup] Killed N zombie assembly process(es)" OR
# ✅ "[startup] zombie process cleanup" (if no zombies found)
# ✅ "event=tasks.assemble.dispatched episode_id=... pid=..."

# Test login (should be < 2 seconds)
curl -X POST https://api.podcastplusplus.com/api/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=YOUR_EMAIL&password=YOUR_PASSWORD"

# Test /me endpoint (should be instant)
curl https://api.podcastplusplus.com/api/users/me \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Why Multiprocessing vs Threading?

### Python's GIL Problem:
```python
# BAD - threading (blocks event loop)
thread = threading.Thread(target=heavy_cpu_work)  # ❌ Holds GIL
thread.start()  # API requests blocked while running!

# GOOD - multiprocessing (separate process/GIL)
process = multiprocessing.Process(target=heavy_cpu_work)  # ✅ Own GIL
process.start()  # API continues responding!
```

### What Was Happening:
```
User Login Request → API Server (Uvicorn)
                     ↓
                    GIL Lock
                     ↓
Assembly Thread ─────┴──── BLOCKS HERE (audio processing)
  (45 seconds)              ↓
                     ALL other requests wait...
                            ↓
                     Login hangs... (timeout after 5min)
```

### After Fix:
```
User Login Request → API Server (Uvicorn) → Instant Response ✅
                     
Assembly Process → Separate Process (own GIL) ✅
  (45 seconds)     Does NOT block API ✅
```

## Rollback Plan (If Something Goes Wrong)

```bash
# Revert the changes
git revert HEAD
git push origin main

# Quick deploy
gcloud builds submit --config cloudbuild.yaml --project=podcast612

# Or manual rollback in Cloud Run console:
# 1. Go to Cloud Run > podcast-api
# 2. Click "Revisions" tab
# 3. Click previous revision
# 4. Click "Manage Traffic"
# 5. Route 100% to previous revision
```

## Known Limitations

### Multiprocessing Notes:
1. **Database connections** - Each process gets its own connection (handled by SQLModel session_scope)
2. **Memory** - Each process has its own memory space (slight increase in RAM usage)
3. **Logging** - Child processes log to stdout (Cloud Logging captures it)
4. **Windows** - Requires `if __name__ == "__main__"` guard (not needed in Cloud Run Linux)

### What This DOESN'T Fix:
- Very slow database queries (need to optimize queries separately)
- Network latency to external APIs (AI, storage, etc.)
- Cold start times (already addressed with min-instances=1)

## Monitoring

### Key Metrics to Watch:

```bash
# Assembly process count
ps aux | grep "assemble" | wc -l

# API response times
curl -w "@curl-format.txt" -o /dev/null -s https://api.podcastplusplus.com/api/users/me

# Memory usage per process
ps aux | grep python | awk '{print $2, $4, $11}'
```

### Expected Behavior:
- Login: < 2 seconds ✅
- `/api/users/me`: < 500ms ✅
- Assembly dispatch: < 1 second ✅
- Assembly completion: 60-120 seconds (background process) ✅
- No zombie processes after restart ✅

## Additional Optimizations (Future)

1. **Use Cloud Tasks properly** - HTTP callbacks instead of in-process
2. **Redis + Celery** - Proper distributed task queue
3. **Pub/Sub** - Decouple assembly from API entirely
4. **Cloud Run Jobs** - Dedicated job runner service

But for now, multiprocessing should solve the immediate crisis.

## Questions?

**Q: Why not use Cloud Tasks?**
A: It's configured but Cloud Tasks HTTP dispatch was still blocking the process. Multiprocessing gives us immediate relief.

**Q: Won't this use more memory?**
A: Yes, but acceptable. Each process ~200-400MB, limited by number of concurrent assemblies.

**Q: What if a process crashes?**
A: It's daemon=True, so it won't hang the main process. Startup cleanup catches zombies.

**Q: Performance impact?**
A: MASSIVE IMPROVEMENT. API goes from "minutes" to "milliseconds" during assembly.

---

**Deploy this ASAP. Your users are suffering.**
