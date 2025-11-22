# Quick Start: Monitoring Your System

**5-Minute Setup Guide**

---

## What You Can Check Right Now

### 1. Circuit Breaker Status (30 seconds)

**Check if external services are failing:**

```bash
curl http://localhost:8000/api/health/circuit-breakers
```

**What to look for:**
- `"status": "healthy"` = All services working ✅
- `"status": "degraded"` = Some services down ⚠️
- `"open_count": 0` = No services failing ✅
- `"open_count": > 0` = Services are down, check which ones ⚠️

**Example response:**
```json
{
  "status": "healthy",
  "open_count": 0,
  "breakers": {
    "gemini": {"state": "closed", "failure_count": 0},
    "assemblyai": {"state": "closed", "failure_count": 0}
  }
}
```

---

### 2. Database Pool Status (30 seconds)

**Check if you're running out of database connections:**

```bash
curl http://localhost:8000/api/health/pool
```

**What to look for:**
- `"utilization_percent": < 80` = Healthy ✅
- `"utilization_percent": > 80` = Approaching limit ⚠️
- `"warning": false` = No issues ✅
- `"warning": true` = Need to monitor closely ⚠️

**Example response:**
```json
{
  "status": "ok",
  "utilization_percent": 45.0,
  "warning": false,
  "current": {
    "checked_out": 9,
    "checked_in": 11
  },
  "configuration": {
    "total_capacity": 20
  }
}
```

---

### 3. Stuck Operations (30 seconds)

**Check if any operations are stuck:**

```bash
curl http://localhost:8000/api/admin/monitoring/stuck-operations
```

**What to look for:**
- `"stuck_count": 0` = No stuck operations ✅
- `"stuck_count": > 0` = Operations need cleanup ⚠️
- `"action_required": false` = Everything fine ✅
- `"action_required": true` = Run cleanup ⚠️

**If stuck operations found:**
```bash
# Clean them up
curl -X POST http://localhost:8000/api/admin/monitoring/stuck-operations/cleanup
```

---

### 4. Deep Health Check (30 seconds)

**Check all critical systems:**

```bash
curl http://localhost:8000/api/health/deep
```

**What to look for:**
- All `"ok"` = Everything healthy ✅
- Any `"fail"` = That system has issues ⚠️

**Example response:**
```json
{
  "db": "ok",
  "storage": "ok",
  "broker": "ok"
}
```

---

## Daily Monitoring Routine (2 minutes)

### Morning Check (Before Users Start)

1. **Circuit breakers:**
   ```bash
   curl http://localhost:8000/api/health/circuit-breakers | jq '.status'
   ```
   - Should be `"healthy"`

2. **Database pool:**
   ```bash
   curl http://localhost:8000/api/health/pool | jq '.utilization_percent'
   ```
   - Should be < 80

3. **Stuck operations:**
   ```bash
   curl http://localhost:8000/api/admin/monitoring/stuck-operations | jq '.stuck_count'
   ```
   - Should be 0

4. **Deep health:**
   ```bash
   curl http://localhost:8000/api/health/deep
   ```
   - All should be "ok"

---

## When Things Go Wrong

### Circuit Breaker is OPEN

**What it means:** External service (Gemini, AssemblyAI, etc.) is failing

**What to do:**
1. Check which service is open (look at `breakers` object)
2. Wait 60 seconds - circuit breaker will test recovery automatically
3. If still open, check service status page
4. Users will see clear error message, can retry

**No action needed** - Circuit breaker protects your system automatically

---

### Database Pool > 80% Utilized

**What it means:** Approaching connection limit

**What to do:**
1. Monitor closely
2. Check for long-running queries
3. If consistently > 90%, consider increasing DB connections (costs money, do later)

**Short-term:** Monitor, no immediate action needed

---

### Stuck Operations Found

**What it means:** Episodes stuck in "processing" state > 2 hours

**What to do:**
1. Check stuck operations:
   ```bash
   curl http://localhost:8000/api/admin/monitoring/stuck-operations
   ```
2. Review stuck episodes (check if they're actually processing)
3. Clean up if needed:
   ```bash
   curl -X POST http://localhost:8000/api/admin/monitoring/stuck-operations/cleanup
   ```

**This is safe** - Only marks truly stuck operations as error

---

## Quick Health Dashboard

**Create a simple monitoring script:**

```bash
#!/bin/bash
# health-check.sh

echo "=== System Health Check ==="
echo ""

echo "Circuit Breakers:"
curl -s http://localhost:8000/api/health/circuit-breakers | jq -r '.status'

echo ""
echo "Database Pool Utilization:"
curl -s http://localhost:8000/api/health/pool | jq -r '.utilization_percent'

echo ""
echo "Stuck Operations:"
curl -s http://localhost:8000/api/admin/monitoring/stuck-operations | jq -r '.stuck_count'

echo ""
echo "Deep Health:"
curl -s http://localhost:8000/api/health/deep | jq '.'
```

**Run it:**
```bash
chmod +x health-check.sh
./health-check.sh
```

---

## What Each Check Tells You

| Check | What It Means | Action If Bad |
|-------|---------------|---------------|
| Circuit Breakers | External services status | Wait for recovery (automatic) |
| Database Pool | Connection availability | Monitor, increase if needed |
| Stuck Operations | Failed/stuck episodes | Run cleanup |
| Deep Health | Overall system health | Investigate failing component |

---

## Summary

**You now have 4 key monitoring endpoints:**

1. ✅ `/api/health/circuit-breakers` - External service status
2. ✅ `/api/health/pool` - Database connection health
3. ✅ `/api/admin/monitoring/stuck-operations` - Stuck operation detection
4. ✅ `/api/health/deep` - Overall system health

**Check these daily** (takes 2 minutes) and you'll catch problems before users do.

**All zero cost** - Just monitoring endpoints, no infrastructure changes.

---

*Start monitoring today - it takes 5 minutes to set up and gives you peace of mind!*


