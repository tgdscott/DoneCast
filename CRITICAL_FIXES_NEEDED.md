# CRITICAL FIXES NEEDED - October 6, 2025

## Problem Analysis

### Issue #1: Login Fails / Stuck on Front Page
**Root Cause**: After successful login, the frontend tries to fetch `/api/users/me` which is **TOO SLOW** (taking minutes instead of milliseconds). This causes:
- Login appears to succeed (token is saved)
- But `/api/users/me` request times out or takes forever
- User stays "stuck" with loading state
- 401 errors on `/api/auth/users/me/prefs` because user object never loads

**The REAL problem**: Something is blocking all API requests (see Issue #5)

### Issue #2: Teal Buttons with Hidden Text
**Root Cause**: CSS color contrast issue - teal button background with teal text = invisible

### Issue #3: Upper Right Button Goes to Wizard Without Login
**Root Cause**: "Get Started" button goes directly to `/app/onboard` without checking authentication

### Issue #4: Assembly Auto-Started After Deploy
**Root Cause**: There's a ZOMBIE assembly task that was queued BEFORE the fix was deployed. It's still running synchronously in the old code path.

### Issue #5: EVERYTHING Takes Minutes (ROOT CAUSE OF ALL ISSUES)
**Root Cause**: The background thread for assembly is **BLOCKING THE ENTIRE APPLICATION**

**WHY**: Python's GIL (Global Interpreter Lock) means CPU-intensive work in a thread BLOCKS THE EVENT LOOP

The assembly process:
- Loads audio files (~50MB)
- FFmpeg processing (CPU-intensive)
- AI calls (network I/O)
- All happening in a daemon thread on the SAME PROCESS

**This is starving Uvicorn's event loop**, making ALL requests slow:
- `/api/users/me` - timeout
- `/api/episodes` - minutes to load
- `/api/auth/users/me/prefs` - 401 because user never loads

## The Fix

### PROPER Solution: Use Multiprocessing or External Workers

The threading approach WON'T WORK for CPU-intensive tasks in Python. We need:

**Option A**: Use Cloud Tasks properly (already configured but not working)
**Option B**: Use multiprocessing.Process instead of threading.Thread
**Option C**: Use Celery with Redis (proper async workers)

I'm going with **Option B** (multiprocessing) as the quickest fix that will actually work.
