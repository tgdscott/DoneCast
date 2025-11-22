# System Reinforcement Guide - Zero Cost Improvements

**Date:** December 2024  
**Purpose:** Strengthen what you have without increasing costs

---

## What You Already Have (You're Not Starting From Zero!)

✅ **Circuit breakers** - Protect against external API failures  
✅ **Error handling** - User-friendly error messages  
✅ **Database connection pooling** - Prevents connection exhaustion  
✅ **Health checks** - Basic monitoring endpoints  
✅ **Stuck operation detection** - Automatic cleanup  
✅ **Request size limits** - Prevents resource exhaustion  
✅ **Performance monitoring** - Tracks slow requests  

**You're in good shape!** Now let's reinforce these foundations.

---

## Priority 1: Enhanced Visibility (Know What's Happening)

### 1.1 Add Circuit Breaker Status to Health Checks

**Why:** Know immediately if external services are failing

**File:** `backend/api/routers/health.py`

**Add this endpoint:**

```python
@router.get("/api/health/circuit-breakers")
def circuit_breaker_status() -> dict[str, Any]:
    """Get status of all circuit breakers."""
    from api.core.circuit_breaker import (
        _assemblyai_breaker,
        _gemini_breaker,
        _auphonic_breaker,
        _elevenlabs_breaker,
        _gcs_breaker,
    )
    
    breakers = {
        "assemblyai": _assemblyai_breaker.get_state(),
        "gemini": _gemini_breaker.get_state(),
        "auphonic": _auphonic_breaker.get_state(),
        "elevenlabs": _elevenlabs_breaker.get_state(),
        "gcs": _gcs_breaker.get_state(),
    }
    
    # Count how many are open
    open_count = sum(1 for b in breakers.values() if b["state"] == "open")
    
    return {
        "status": "degraded" if open_count > 0 else "healthy",
        "open_count": open_count,
        "breakers": breakers,
    }
```

**How to use:**
- Check `/api/health/circuit-breakers` to see if any services are down
- Monitor this endpoint to catch issues early

---

### 1.2 Add Error Rate Tracking

**Why:** Know if errors are increasing before users complain

**File:** `backend/api/middleware/error_tracking.py` (new)

**Create this:**

```python
"""Error rate tracking middleware."""
from collections import deque
from time import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from api.core.logging import get_logger

log = get_logger("api.middleware.error_tracking")

# Track errors in sliding window (last 5 minutes)
_error_window = deque(maxlen=1000)  # Store up to 1000 errors
_success_window = deque(maxlen=1000)  # Store up to 1000 successes


class ErrorTrackingMiddleware(BaseHTTPMiddleware):
    """Track error rates for monitoring."""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time()
        response = await call_next(request)
        duration = time() - start_time
        
        # Track errors (4xx, 5xx) and successes
        if response.status_code >= 400:
            _error_window.append({
                "timestamp": start_time,
                "status": response.status_code,
                "path": request.url.path,
                "method": request.method,
            })
            
            # Alert if error rate spikes
            if len(_error_window) >= 10:
                recent_errors = [e for e in _error_window if time() - e["timestamp"] < 60]
                if len(recent_errors) >= 10:
                    log.error(
                        "High error rate detected: %d errors in last 60 seconds",
                        len(recent_errors)
                    )
        else:
            _success_window.append({"timestamp": start_time})
        
        return response


def get_error_rate() -> dict[str, Any]:
    """Get current error rate statistics."""
    now = time()
    window_seconds = 300  # 5 minutes
    
    recent_errors = [e for e in _error_window if now - e["timestamp"] < window_seconds]
    recent_successes = [s for s in _success_window if now - s["timestamp"] < window_seconds]
    
    total = len(recent_errors) + len(recent_successes)
    error_rate = (len(recent_errors) / total * 100) if total > 0 else 0
    
    return {
        "error_count": len(recent_errors),
        "success_count": len(recent_successes),
        "total_requests": total,
        "error_rate_percent": round(error_rate, 2),
        "window_seconds": window_seconds,
    }
```

**Add to middleware:** `backend/api/config/middleware.py`

```python
from api.middleware.error_tracking import ErrorTrackingMiddleware
app.add_middleware(ErrorTrackingMiddleware)
```

**Add endpoint:** `backend/api/routers/health.py`

```python
@router.get("/api/health/error-rate")
def error_rate_stats() -> dict[str, Any]:
    """Get error rate statistics."""
    from api.middleware.error_tracking import get_error_rate
    return get_error_rate()
```

---

## Priority 2: Transaction Safety (Prevent Data Corruption)

### 2.1 Ensure All Critical Operations Use Retry Logic

**Why:** Database connection failures shouldn't lose data

**Check these files for missing retry logic:**

1. **Episode creation** - `backend/api/routers/episodes/write.py`
2. **Media uploads** - `backend/api/routers/media_write.py`
3. **User operations** - `backend/api/routers/users.py`
4. **Billing operations** - `backend/api/routers/billing.py`

**Pattern to use:**

```python
from worker.tasks.assembly.transcript import _commit_with_retry

# Instead of:
session.commit()

# Use:
if not _commit_with_retry(session):
    raise HTTPException(status_code=500, detail="Failed to save after retries")
```

**Action:** Audit all `session.commit()` calls and add retry logic to critical paths.

---

### 2.2 Add Transaction Timeout Protection

**Why:** Prevent long-running transactions from blocking others

**File:** `backend/api/core/database.py`

**Already exists:** `statement_timeout` is set to 5 minutes

**Verify it's working:**

```python
# Add to health check
@router.get("/api/health/db-timeout")
def db_timeout_check(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Check database timeout configuration."""
    from sqlalchemy import text
    result = session.execute(text("SHOW statement_timeout")).first()
    return {
        "statement_timeout": result[0] if result else "unknown",
        "configured": "300000ms" in str(result[0]) if result else False,
    }
```

---

## Priority 3: Resource Safety (Prevent Leaks)

### 3.1 Ensure All File Operations Are Cleaned Up

**Why:** Prevent disk space issues

**Check these areas:**

1. **Temporary files** - Ensure they're deleted even on errors
2. **GCS uploads** - Ensure failed uploads don't leave orphaned files
3. **Audio processing** - Clean up intermediate files

**Pattern to use:**

```python
from contextlib import contextmanager
from pathlib import Path

@contextmanager
def temp_file(suffix: str = ".tmp"):
    """Create temporary file that's always cleaned up."""
    import tempfile
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        yield Path(path)
    finally:
        try:
            os.close(fd)
            os.unlink(path)
        except Exception:
            pass  # Best effort cleanup

# Usage:
with temp_file(".mp3") as temp_path:
    # Do work with temp_path
    process_audio(temp_path)
    # File automatically deleted even if error occurs
```

---

### 3.2 Add Resource Usage Monitoring

**Why:** Know if you're running out of resources

**File:** `backend/api/routers/health.py`

**Add:**

```python
@router.get("/api/health/resources")
def resource_usage() -> dict[str, Any]:
    """Get current resource usage."""
    import psutil
    import os
    
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    
    return {
        "memory_mb": round(memory_info.rss / 1024 / 1024, 2),
        "memory_percent": process.memory_percent(),
        "cpu_percent": process.cpu_percent(interval=1),
        "open_files": len(process.open_files()),
        "threads": process.num_threads(),
    }
```

**Note:** Requires `psutil` package - add to `requirements.txt` if not present.

---

## Priority 4: Proactive Monitoring (Catch Issues Early)

### 4.1 Add Stuck Operation Alert Endpoint

**Why:** Get notified when operations get stuck

**File:** `backend/api/routers/admin/monitoring.py`

**Add:**

```python
@router.get("/stuck-operations")
def check_stuck_operations(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Check for stuck operations and optionally mark as error."""
    from worker.tasks.maintenance import detect_stuck_episodes, mark_stuck_episodes_as_error
    
    # Detect stuck operations
    stuck = detect_stuck_episodes(session, stuck_threshold_hours=2)
    
    return {
        "stuck_count": len(stuck),
        "stuck_episodes": stuck[:10],  # Limit to first 10
        "action_required": len(stuck) > 0,
    }

@router.post("/stuck-operations/cleanup")
def cleanup_stuck_operations(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Mark stuck operations as error."""
    from worker.tasks.maintenance import mark_stuck_episodes_as_error
    
    result = mark_stuck_episodes_as_error(session, dry_run=False)
    return result
```

---

### 4.2 Add Database Pool Monitoring

**Why:** Know before you hit connection limits

**File:** `backend/api/routers/health.py`

**Enhance existing endpoint:**

```python
@router.get("/api/health/pool")
def pool_stats(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Database connection pool statistics."""
    # ... existing code ...
    
    # Add utilization warning
    total_capacity = config["total_capacity"]
    checked_out = stats.get("checked_out", 0)
    utilization = (checked_out / total_capacity * 100) if total_capacity > 0 else 0
    
    return {
        "status": "ok",
        "current": stats,
        "configuration": config,
        "utilization_percent": round(utilization, 2),
        "warning": utilization > 80,  # Warn if > 80% utilized
    }
```

---

## Priority 5: Error Recovery (Help Users When Things Go Wrong)

### 5.1 Add Automatic Retry for Transient Errors

**Why:** Users shouldn't have to manually retry

**File:** `frontend/src/lib/apiClient.js` (or wherever you make API calls)

**Add retry logic:**

```javascript
async function fetchWithRetry(url, options, maxRetries = 3) {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const response = await fetch(url, options);
      
      // Check if error is retryable
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        if (error.error?.retryable && attempt < maxRetries - 1) {
          // Wait with exponential backoff
          const delay = Math.pow(2, attempt) * 1000; // 1s, 2s, 4s
          await new Promise(resolve => setTimeout(resolve, delay));
          continue;
        }
      }
      
      return response;
    } catch (error) {
      if (attempt < maxRetries - 1) {
        const delay = Math.pow(2, attempt) * 1000;
        await new Promise(resolve => setTimeout(resolve, delay));
        continue;
      }
      throw error;
    }
  }
}
```

---

### 5.2 Add User-Friendly Error Messages

**Why:** Users should know what to do when errors happen

**Already done:** Error messages are user-friendly ✅

**Enhance:** Add action buttons in frontend

```javascript
// In your error display component
function ErrorDisplay({ error }) {
  if (error.retryable) {
    return (
      <div>
        <p>{error.message}</p>
        <button onClick={retry}>Retry</button>
      </div>
    );
  }
  return <p>{error.message}</p>;
}
```

---

## Quick Wins (Do These First)

### ✅ 1. Add Circuit Breaker Status Endpoint (5 minutes)
- Copy code from Priority 1.1
- Test: `curl http://localhost:8000/api/health/circuit-breakers`

### ✅ 2. Add Error Rate Tracking (10 minutes)
- Copy code from Priority 1.2
- Monitor: `curl http://localhost:8000/api/health/error-rate`

### ✅ 3. Add Stuck Operations Check (5 minutes)
- Copy code from Priority 4.1
- Check: `curl http://localhost:8000/api/admin/monitoring/stuck-operations`

### ✅ 4. Enhance Pool Stats (2 minutes)
- Add utilization warning to existing endpoint
- Check: `curl http://localhost:8000/api/health/pool`

---

## What to Monitor Daily

### Morning Checklist (2 minutes)

1. **Check circuit breakers:**
   ```
   GET /api/health/circuit-breakers
   ```
   - Any "open" = external service is down
   - Action: Check service status, wait for recovery

2. **Check error rate:**
   ```
   GET /api/health/error-rate
   ```
   - Error rate > 1% = investigate
   - Action: Check logs for patterns

3. **Check database pool:**
   ```
   GET /api/health/pool
   ```
   - Utilization > 80% = approaching limit
   - Action: Monitor closely, consider increasing connections

4. **Check stuck operations:**
   ```
   GET /api/admin/monitoring/stuck-operations
   ```
   - Any stuck = operations need cleanup
   - Action: Run cleanup endpoint

---

## What Each Improvement Does

### Visibility Improvements
- **Know immediately** when external services fail
- **Track error rates** before users complain
- **Monitor resource usage** before hitting limits

### Safety Improvements
- **Prevent data loss** with transaction retries
- **Prevent resource leaks** with proper cleanup
- **Prevent corruption** with timeout protection

### Recovery Improvements
- **Automatic retry** for transient errors
- **Clear guidance** for users when errors occur
- **Proactive cleanup** of stuck operations

---

## Implementation Order

### Week 1: Visibility
1. ✅ Circuit breaker status endpoint
2. ✅ Error rate tracking
3. ✅ Enhanced pool monitoring

### Week 2: Safety
1. ✅ Audit transaction retry usage
2. ✅ Add resource cleanup patterns
3. ✅ Verify timeout protection

### Week 3: Recovery
1. ✅ Add automatic retry in frontend
2. ✅ Enhance error messages
3. ✅ Add stuck operation cleanup

---

## Testing Your Improvements

### Test Circuit Breaker Status
```bash
# Should show all breakers as "closed" (healthy)
curl http://localhost:8000/api/health/circuit-breakers
```

### Test Error Rate Tracking
```bash
# Make some requests, then check error rate
curl http://localhost:8000/api/health/error-rate
```

### Test Stuck Operations
```bash
# Check for stuck operations
curl http://localhost:8000/api/admin/monitoring/stuck-operations
```

---

## Summary

**You're not starting from zero!** You already have:
- ✅ Circuit breakers
- ✅ Error handling
- ✅ Database pooling
- ✅ Health checks
- ✅ Monitoring

**What we're adding:**
- 🔍 **Better visibility** - See problems before they become critical
- 🛡️ **More safety** - Prevent data loss and resource leaks
- 🔄 **Better recovery** - Help users when things go wrong

**All zero cost** - Just code improvements, no infrastructure changes.

**Start with Quick Wins** - They take 5-10 minutes each and give immediate value.

---

*This guide focuses on reinforcing what you have, not adding new infrastructure. Everything here is code-only and costs nothing.*


