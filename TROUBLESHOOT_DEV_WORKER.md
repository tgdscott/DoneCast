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

