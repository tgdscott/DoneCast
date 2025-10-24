# Dev/Prod Parity Solution - Complete Analysis & Recommendations

**Date:** October 16, 2025  
**Problem:** Dev environment diverged from production, requiring frequent 10-15 minute Cloud Run builds for testing  
**Goal:** Achieve true dev/prod parity with fast iteration cycles

---

## Current State Analysis

### Production Environment
- **Platform:** Google Cloud Run (serverless containers)
- **Database:** Cloud SQL PostgreSQL 15 (`podcast612:us-west1:podcast-db`)
- **Connection:** Unix socket `/cloudsql/podcast612:us-west1:podcast-db`
- **Storage:** Google Cloud Storage (GCS) - SOLE source of truth
- **Secrets:** Secret Manager
- **Build Time:** 10-15 minutes (Docker build + push + deploy)
- **Domain:** `api.podcastplusplus.com` (API), `app.podcastplusplus.com` (frontend)

### Current Dev Environment
- **Platform:** Local Windows machine with PowerShell scripts
- **Database:** Local PostgreSQL via Docker Compose (localhost:5432)
- **Connection:** `postgresql+psycopg://podcast:local_password@localhost:5432/podcast`
- **Storage:** Mix of local files (`local_media/`) + GCS (with fallbacks causing issues)
- **Secrets:** `.env.local` file
- **Pain Points:**
  - ❌ Database schema drift between local Postgres and Cloud SQL
  - ❌ GCS behavior differs (local fallbacks don't match prod)
  - ❌ Migration scripts run only on prod deploy, not locally
  - ❌ Frequent deploys needed to test database changes
  - ❌ Local Docker Compose Postgres doesn't match Cloud SQL state

---

## Root Cause: The Three Divergence Points

### 1. **Database Divergence** (CRITICAL)
Your migration system runs on app startup (`api/startup_tasks.py`), which means:
- Production DB gets migrations automatically on deploy
- Local Docker Compose DB only gets migrations when you remember to restart the API
- No schema version tracking (not using Alembic)
- Result: **Schemas drift**, requiring prod deploys to test DB changes

### 2. **Storage Layer Mismatch**
- Production: GCS-only (enforced as of Oct 13)
- Dev: Mix of local files with GCS fallbacks
- Result: **Code paths differ**, local testing doesn't catch GCS failures

### 3. **Configuration Complexity**
- Production: Secret Manager + env vars in `cloudrun-api-env.yaml`
- Dev: `.env.local` with manual maintenance
- Result: **Config drift**, missing/outdated settings in dev

---

## Solution Options (Ranked by Effectiveness)

### 🥇 OPTION 1: Cloud SQL Proxy for Dev (RECOMMENDED)
**Connect your local dev environment directly to the production Cloud SQL database**

#### How It Works
```
Local Dev → Cloud SQL Proxy → Production Cloud SQL (us-west1)
```

#### Advantages
✅ **Perfect schema parity** - Using THE SAME database  
✅ **Zero migration hassle** - Prod deploys auto-update your dev DB  
✅ **Fast iteration** - No Docker builds needed  
✅ **Test with real data** - Debug production issues locally  
✅ **Multi-machine support** - Works from desktop AND laptop  
✅ **GCS already shared** - You're using the same buckets anyway  

#### Disadvantages
⚠️ Requires internet connection  
⚠️ Risk of accidentally breaking production data (mitigated with safeguards)  
⚠️ Slightly higher latency than local DB  

#### Implementation Steps
1. Install Cloud SQL Proxy on your dev machine
2. Update `.env.local` to point to proxy connection
3. Add safety checks to prevent destructive operations in dev mode
4. Remove Docker Compose Postgres entirely

**Time to implement:** 30 minutes  
**Ongoing maintenance:** None (auto-syncs with prod)

---

### 🥈 OPTION 2: Dedicated Dev Cloud SQL Instance
**Create a second Cloud SQL instance for development**

#### How It Works
```
Local Dev → Cloud SQL Proxy → Dev Cloud SQL (separate instance)
Production → Cloud SQL → Production Cloud SQL
```

#### Advantages
✅ **True isolation** - Can't accidentally break prod  
✅ **Fast iteration** - No Docker builds  
✅ **Multi-machine support**  
✅ **Cloud SQL features** (IAM, backups, etc.)  

#### Disadvantages
⚠️ **Costs ~$50-100/month** for always-on instance  
⚠️ **Schema drift returns** - Need to manually sync dev ↔ prod  
⚠️ **Data drift** - Dev data won't match production  

#### Implementation Steps
1. Create `podcast-db-dev` Cloud SQL instance (smaller machine type)
2. Use Cloud SQL Proxy to connect locally
3. Restore production backup to dev instance (weekly?)
4. Update `.env.local` connection string

**Time to implement:** 1 hour  
**Ongoing maintenance:** Weekly backup restores, schema sync scripts  
**Monthly cost:** $50-100

---

### 🥉 OPTION 3: Cloud Workstations (Overkill)
**Use Google Cloud Workstations as your dev environment**

This is essentially a cloud-hosted VS Code running in GCP. **Not recommended** - too complex for your needs.

---

### 🏠 OPTION 4: Home Server with Tailscale VPN
**Run a dedicated dev server on your spare computer**

#### How It Works
```
Laptop → Tailscale VPN → Home Server → Postgres + API
Desktop → Tailscale VPN → Home Server → Postgres + API
```

#### Advantages
✅ **No recurring costs**  
✅ **Full control**  
✅ **Multi-machine access** (via VPN)  

#### Disadvantages
⚠️ **High setup complexity** - Server OS, Postgres, Tailscale, SSL certs  
⚠️ **Maintenance burden** - You're now a sysadmin  
⚠️ **Single point of failure** - If server goes down, you can't work  
⚠️ **Schema drift returns** - Same as Option 2  

**Time to implement:** 4-8 hours  
**Ongoing maintenance:** High (OS updates, backups, monitoring)

---

## 🎯 RECOMMENDED SOLUTION: Option 1 (Cloud SQL Proxy)

### Why This Wins
1. **Solves your actual problem** - No more schema drift
2. **Fast implementation** - Working today
3. **Zero ongoing maintenance** - Set and forget
4. **Multi-machine ready** - Laptop and desktop both work
5. **No extra costs** - You're already paying for Cloud SQL

### Safety Measures (Critical!)
To prevent accidentally nuking production data:

1. **Read-only mode toggle** in `.env.local`:
   ```env
   DEV_MODE=true
   DEV_READ_ONLY=false  # Set to true for ultra-safe browsing
   ```

2. **Middleware checks** in `api/app.py`:
   ```python
   if settings.APP_ENV == "dev" and request.method in ["DELETE", "PUT", "PATCH"]:
       if settings.DEV_READ_ONLY:
           raise HTTPException(403, "Read-only mode enabled")
   ```

3. **User filtering** - Only interact with your test user accounts:
   ```python
   # Add to database queries in dev mode
   if settings.APP_ENV == "dev":
       query = query.where(User.email.in_(["test@example.com", "scott@scottgerhardt.com"]))
   ```

4. **Transaction rollback option** - Add manual commit for destructive ops:
   ```python
   if settings.APP_ENV == "dev" and is_destructive_operation():
       # Require manual confirmation
       confirm = input("Confirm destructive operation (yes/no): ")
       if confirm != "yes":
           session.rollback()
   ```

---

## Implementation Plan for Option 1

### Phase 1: Setup (30 minutes)

#### Step 1: Install Cloud SQL Proxy
```powershell
# Download proxy binary
curl -o cloud-sql-proxy.exe https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.8.2/cloud-sql-proxy.x64.exe

# Move to a permanent location
Move-Item cloud-sql-proxy.exe C:\Tools\cloud-sql-proxy.exe

# Test connection
C:\Tools\cloud-sql-proxy.exe podcast612:us-west1:podcast-db
```

#### Step 2: Create Startup Script
Create `scripts/start_sql_proxy.ps1`:
```powershell
$ErrorActionPreference = 'Stop'
Write-Host "Starting Cloud SQL Proxy..."
& C:\Tools\cloud-sql-proxy.exe `
    --address 127.0.0.1 `
    --port 5433 `
    podcast612:us-west1:podcast-db
```

**Why port 5433?** Avoids conflicts with any local Postgres on 5432

#### Step 3: Update `.env.local`
```env
# OLD (local Docker Compose)
# DATABASE_URL=postgresql+psycopg://podcast:local_password@localhost:5432/podcast

# NEW (Cloud SQL via proxy)
DATABASE_URL=postgresql+psycopg://PROD_USER:PROD_PASSWORD@localhost:5433/podcast

# Get credentials from Secret Manager:
# DB_USER from sm://podcast612/DB_USER
# DB_PASS from sm://podcast612/DB_PASS
# DB_NAME from sm://podcast612/DB_NAME (should be "podcast")
```

#### Step 4: Get Production Credentials
```powershell
# Retrieve from Secret Manager
gcloud secrets versions access latest --secret=DB_USER
gcloud secrets versions access latest --secret=DB_PASS
gcloud secrets versions access latest --secret=DB_NAME
```

Copy these values into `.env.local` (or create a script to auto-populate).

#### Step 5: Test Connection
```powershell
# Terminal 1: Start proxy
.\scripts\start_sql_proxy.ps1

# Terminal 2: Start API
.\scripts\dev_start_api.ps1
```

Should see logs: `[db] Using DATABASE_URL for engine (driver=postgresql+psycopg)`

#### Step 6: Remove Docker Compose (Optional)
```powershell
# No longer needed
docker-compose down -v
# Rename file to prevent accidental use
Move-Item docker-compose.yaml docker-compose.yaml.disabled
```

---

### Phase 2: Safety Enhancements (1 hour)

#### Add Dev Mode Safeguards

**File: `backend/api/core/config.py`**
```python
# Add after existing settings
DEV_READ_ONLY: bool = Field(default=False, description="Prevent destructive ops in dev")
DEV_TEST_USER_EMAILS: str = Field(
    default="scott@scottgerhardt.com,test@example.com",
    description="Comma-separated dev user emails (for filtering in dev mode)"
)

@property
def is_dev_mode(self) -> bool:
    return self.APP_ENV.lower() in {"dev", "development", "local"}

@property
def dev_test_users(self) -> list[str]:
    return [e.strip() for e in self.DEV_TEST_USER_EMAILS.split(",") if e.strip()]
```

**File: `backend/api/middleware/dev_safety.py` (NEW)**
```python
from fastapi import Request, HTTPException
from api.core.config import settings
import logging

log = logging.getLogger(__name__)

async def dev_read_only_middleware(request: Request, call_next):
    """Prevent destructive operations in dev read-only mode"""
    if settings.is_dev_mode and settings.DEV_READ_ONLY:
        if request.method in ["DELETE", "PUT", "PATCH", "POST"]:
            # Allow auth endpoints
            if not request.url.path.startswith("/api/auth"):
                log.warning(f"[DEV] Blocked {request.method} {request.url.path} (read-only mode)")
                raise HTTPException(
                    status_code=403,
                    detail="Read-only mode enabled in dev environment. Set DEV_READ_ONLY=false to allow writes."
                )
    return await call_next(request)
```

**Register middleware in `api/app.py`:**
```python
from api.middleware.dev_safety import dev_read_only_middleware

# Add after existing middleware
app.middleware("http")(dev_read_only_middleware)
```

---

### Phase 3: Developer Experience (30 minutes)

#### Create Unified Dev Start Script

**File: `scripts/dev_start_all.ps1` (NEW)**
```powershell
$ErrorActionPreference = 'Stop'

Write-Host "🚀 Starting Podcast Plus Plus Development Environment" -ForegroundColor Cyan
Write-Host ""

# Check if proxy is already running
$proxyRunning = Get-Process cloud-sql-proxy -ErrorAction SilentlyContinue
if (-not $proxyRunning) {
    Write-Host "📡 Starting Cloud SQL Proxy..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '.\scripts\start_sql_proxy.ps1'"
    Start-Sleep -Seconds 3
} else {
    Write-Host "✅ Cloud SQL Proxy already running" -ForegroundColor Green
}

Write-Host "🔧 Starting Backend API..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '.\scripts\dev_start_api.ps1'"
Start-Sleep -Seconds 5

Write-Host "🎨 Starting Frontend..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '.\scripts\dev_start_frontend.ps1'"

Write-Host ""
Write-Host "✨ All services starting!" -ForegroundColor Green
Write-Host "   API: http://127.0.0.1:8000" -ForegroundColor Gray
Write-Host "   Frontend: http://127.0.0.1:5173" -ForegroundColor Gray
Write-Host ""
Write-Host "⚠️  Using PRODUCTION database via Cloud SQL Proxy" -ForegroundColor Red
Write-Host "   Only modify test user data. Set DEV_READ_ONLY=true for safety." -ForegroundColor Red
```

---

## Database Management Best Practices

### Schema Changes Going Forward

#### Current Process (Problematic)
1. Write migration in `backend/migrations/`
2. Deploy to prod
3. Migration runs on startup
4. Dev environment outdated until next deploy

#### NEW Process (With Proxy)
1. Write migration in `backend/migrations/`
2. **Test locally** (migration runs against prod DB)
3. Restart local API to trigger migration
4. Deploy to prod (migration already applied, no-op)

**Result:** Migrations tested before deploy! 🎉

### Data Seeding for Dev

Create a script to populate test data:

**File: `backend/dev_seed_data.py`**
```python
"""Seed test data for development (safe for production DB)"""
from api.core.database import get_session
from api.models.user import User
from api.core.config import settings
import sys

def seed_dev_data():
    if not settings.is_dev_mode:
        print("ERROR: Only run in dev mode!")
        sys.exit(1)
    
    with get_session() as session:
        # Check if test user exists
        test_email = "devtest@example.com"
        user = session.query(User).filter(User.email == test_email).first()
        if not user:
            user = User(
                email=test_email,
                full_name="Dev Test User",
                # ... other fields
            )
            session.add(user)
            session.commit()
            print(f"✅ Created test user: {test_email}")
        else:
            print(f"ℹ️  Test user already exists: {test_email}")

if __name__ == "__main__":
    seed_dev_data()
```

---

## Addressing Your Specific Concerns

### "I don't even necessarily need local dev"
**Perfect!** With Cloud SQL Proxy, your dev environment IS semi-remote:
- Database: Remote (Cloud SQL)
- Storage: Remote (GCS)
- Code: Local (fast iteration)
- Compute: Local (no deploy wait)

Best of both worlds.

### "Can't wait 10-15 minutes every build"
**Eliminated!** With Cloud SQL Proxy:
- Code changes: Save file → Hot reload (2 seconds)
- DB schema changes: Restart API (10 seconds)
- No Docker builds needed for dev work

### "Could use spare computer as server"
**Not needed!** Cloud SQL Proxy gives you multi-machine support without the hassle:
- Desktop: Run proxy → connect → code
- Laptop: Run proxy → connect → code
Both talk to the same production database.

### "Postgres changes affect everything"
**Fixed!** There's now only ONE Postgres (production Cloud SQL). Schema changes are instant across all environments.

---

## Migration Path: Docker Compose → Cloud SQL Proxy

### Before (Current State)
```
Developer Machine:
├── Docker Compose (Postgres 15)
│   └── Local schema (drifted)
├── Local files (local_media/)
└── .env.local (local config)

Production:
├── Cloud SQL (Postgres 15)
│   └── Production schema (current)
├── GCS (ppp-media-us-west1)
└── Secret Manager (prod config)
```

### After (Proposed State)
```
Developer Machine:
├── Cloud SQL Proxy (port 5433)
│   └── → Production Cloud SQL
├── GCS client (same buckets)
└── .env.local (proxy config)

Production:
├── Cloud SQL (Postgres 15)
│   └── Production schema (shared with dev!)
├── GCS (ppp-media-us-west1)
└── Secret Manager (prod config)
```

---

## Cost Analysis

### Current State
- Cloud SQL: $X/month (existing)
- Cloud Run: $Y/month (existing)
- **Dev deploys:** Wasted time + build costs

### Option 1 (Cloud SQL Proxy)
- Cloud SQL: $X/month (no change)
- Cloud Run: $Y/month (no change)
- Proxy: **$0** (free, just connects)
- **Savings:** Reduced Cloud Build usage, developer time

### Option 2 (Dedicated Dev Instance)
- Production Cloud SQL: $X/month
- **Dev Cloud SQL: +$50-100/month**
- Total: $(X+50) to $(X+100)/month

**Winner:** Option 1 (no additional costs)

---

## Rollback Plan

If Cloud SQL Proxy doesn't work out:

1. **Immediate rollback:**
   ```powershell
   # Stop proxy
   Stop-Process -Name cloud-sql-proxy
   
   # Restore Docker Compose
   Move-Item docker-compose.yaml.disabled docker-compose.yaml
   docker-compose up -d
   
   # Restore .env.local
   git checkout backend/.env.local
   ```

2. **Restore local DB from backup:**
   ```powershell
   docker exec podcast-pro-db psql -U podcast -d podcast < local_backup.sql
   ```

**Risk:** Very low. Proxy only reads/writes, doesn't modify infrastructure.

---

## Next Steps

### Immediate (Today)
1. ✅ Review this document
2. ✅ Decide on Option 1 (Cloud SQL Proxy) or Option 2 (Dedicated Dev Instance)
3. ⏳ Implement chosen solution (see Phase 1 above)

### Short-term (This Week)
4. ⏳ Add dev mode safeguards (Phase 2)
5. ⏳ Create unified dev start script (Phase 3)
6. ⏳ Test full dev workflow (code change → test → deploy)

### Long-term (Ongoing)
7. ⏳ Document dev setup for future team members
8. ⏳ Consider CI/CD improvements (run tests against Cloud SQL before deploy)
9. ⏳ Monitor for any dev/prod issues

---

## Questions to Answer

Before implementing, consider:

1. **How often do you work offline?**
   - Rarely → Option 1 (proxy) is fine
   - Frequently → Option 2 (dedicated dev instance)

2. **How important is cost?**
   - Critical → Option 1 ($0/month)
   - Not a concern → Option 2 ($50-100/month)

3. **Risk tolerance for prod DB?**
   - Comfortable with safeguards → Option 1
   - Want total isolation → Option 2

4. **Multi-machine requirement?**
   - Desktop + Laptop → Both options work
   - Single machine → Either works

My recommendation: **Start with Option 1**. It's free, fast to implement, and you can always move to Option 2 later if needed.

---

## Conclusion

Your core problem is **database schema drift** caused by migrations running only in production. The Cloud SQL Proxy solution eliminates this by making your dev environment share the production database, giving you:

✅ **Zero schema drift** (same DB)  
✅ **Fast iteration** (no Docker builds)  
✅ **Multi-machine support** (laptop + desktop)  
✅ **No extra costs** (free proxy)  
✅ **Reduced deploy frequency** (test locally first)  

The 10-15 minute build cycle becomes a 2-second hot reload. Database changes are tested locally before deploy. And you can work from any machine without syncing databases.

**Ready to implement? Let me know and I'll help set up the Cloud SQL Proxy.**

---

*Document version: 1.0*  
*Last updated: October 16, 2025*
