# Podcast Plus Plus - AI Agent Instructions

## Project Overview
Self-hosted podcast creation platform with AI-powered features. Full-stack app: FastAPI backend + React frontend, deployed on Google Cloud Run.

**Key Tech:** Python 3.11+, FastAPI, SQLAlchemy 2.0/SQLModel, PostgreSQL, React 18, Vite, TailwindCSS, GCS, Cloud Tasks

## ⚠️ Critical Constraints

### Production First
**All fixes and features MUST prioritize production environment.** Local dev is nice-to-have but production stability is non-negotiable. If a change helps both, great. If it's a choice, production wins every time.

### User-Facing URLs: Never Use UUIDs
**Public-facing URLs MUST use human-friendly identifiers** (slugs, readable IDs, names). This platform is designed for non-technical users - UUIDs in URLs are confusing and unprofessional.

**Examples:**
- ✅ `/podcasts/my-awesome-show/episodes/episode-42`
- ✅ `/rss/my-awesome-show.xml`
- ❌ `/podcasts/a7f3c8e9-1234-5678-90ab-cdef12345678`
- ❌ `/episodes/b8e4d9fa-2345-6789-01bc-def123456789`

### Secrets & Environment Variables
**NEVER delete, overwrite, or modify production secrets/env vars.** You can create NEW variables, but existing production configuration is off-limits. If a secret needs changing, document the requirement and let the human handle it.

**Safe operations:**
- ✅ Add new optional env var with default value
- ✅ Document required env var for new feature
- ❌ Change existing DATABASE_URL value
- ❌ Rotate API keys or tokens
- ❌ Modify cloudbuild.yaml substitution values

## Critical Architecture Patterns

### Directory Structure (Post-Rename)
- **`backend/api/`** - FastAPI application (formerly `podcast-pro-plus/api`)
- **`frontend/`** - React/Vite SPA
- **`conftest.py`** at project root adds `backend/` to sys.path so `from api...` imports work

### Backend Module Organization
- **`api/routers/`** - FastAPI endpoints (one file per resource, sometimes subdirs like `routers/episodes/`)
- **`api/services/`** - Business logic (e.g., `services/episodes/assembler.py` orchestrates episode assembly)
- **`api/models/`** - SQLModel table definitions (see `podcast.py` for core Episode/Podcast/Template models)
- **`api/infrastructure/`** - External integrations (currently minimal, GCS client imports may live in services)
- **`api/tasks/`** - Cloud Tasks queue helpers (`tasks/queue.py` has `enqueue_task()`)
- **`api/core/`** - Config (`config.py`), paths (`paths.py`), database (`database.py`), logging

### Safe Router Imports
`api/routing.py` uses `_safe_import()` to register routers defensively. Missing dependencies or import errors log warnings but don't crash startup. **Always** check routing.py when adding new routers.

### Episode Assembly Pipeline
1. User uploads main content audio → saved to GCS
2. Transcription via AssemblyAI (async, triggered via Cloud Tasks `/api/tasks/transcribe`)
3. Optional processing: Intern (detect spoken editing commands), Flubber (remove filler words)
4. Assembly: `services/episodes/assembler.py` → `assemble_or_queue()` dispatches to Cloud Tasks `/api/tasks/assemble` (prod) or inline executor (dev)
5. Publish: Updates RSS feed, generates signed GCS URLs (7-day expiry), updates episode status to `published`

**Key files:** 
- `services/episodes/assembler.py` - Assembly orchestration & queue dispatch
- `routers/tasks.py` - Task endpoints for transcription & assembly
- `routers/episodes/assemble.py` - User-facing assembly trigger
- `services/episodes/publisher.py` - RSS feed generation & publishing

### Media & GCS Integration
- All media uploads go to GCS bucket (defined in `settings.GCS_BUCKET`)
- Local dev: Files in `backend/local_media/` (see `api/core/paths.py` for `MEDIA_DIR` resolution)
- GCS paths: `gs://{bucket}/{filename}` or signed URLs for temporary access
- **Critical:** Transcripts migrated from local filesystem to GCS (see `TRANSCRIPT_MIGRATION_TO_GCS.md`)

### Database Models & Status Flow
- **Episode statuses:** `pending` → `processing` → `processed` → `published` (see `EpisodeStatus` enum in `models/podcast.py`)
- **Templates:** Reusable episode structures (`PodcastTemplate`) with segments (intro/outro/music), TTS prompts, AI settings
- **Music:** `MusicAsset` table for global/user-owned background music; `BackgroundMusicRule` defines ducking & mixing
- **Billing:** Stripe integration, `Subscription` model tracks plans, `UsageRecord` tracks monthly minutes consumed

### Environment & Configuration
- `.env.local` (backend dev), `.env.production` (frontend prod build)
- **Backend settings:** `api/core/config.py` uses pydantic-settings with alias support (e.g., `APP_ENV`, `ENV`, `PYTHON_ENV` all map to same field)
- **Key vars:** `DATABASE_URL`, `GCS_BUCKET`, `GEMINI_API_KEY`, `STRIPE_SECRET_KEY`, `ASSEMBLYAI_API_KEY`
- **Auth:** JWT tokens (HS256, 30-day expiry), session cookies for Google OAuth flows

### Testing Philosophy
- **pytest** with `-m "not integration"` by default (see `pytest.ini`)
- **HTTP mocking:** `requests-mock` blocks all outbound calls except localhost (see `tests/README.md`)
- **Test location:** `tests/` (project root) and `backend/api/tests/` (both scanned)
- **Fixtures:** `conftest.py` provides `db` (session), `user`, `podcast`, `episode`, `authed_client`
- Run: `pytest -q` (fast unit), `pytest -q -m integration` (integration tests)

## Development Workflows

### Local Dev Setup (Windows PowerShell)
```powershell
# 1. Activate venv
.\.venv\Scripts\Activate.ps1

# 2. Start backend (runs migrations on startup)
.\scripts\dev_start_api.ps1
# → FastAPI at http://127.0.0.1:8000, docs at /docs

# 3. Start frontend (separate terminal)
.\scripts\dev_start_frontend.ps1
# → Vite dev at http://127.0.0.1:5173, proxies /api → :8000
```

**Script behavior:**
- `dev_start_api.ps1`: Resolves `backend/.env.local`, checks ADC (Application Default Credentials), runs uvicorn with hot reload
- `dev_start_frontend.ps1`: Auto-runs `npm install` if `node_modules/` missing, starts Vite dev server
- Both scripts use absolute paths and handle working directory correctly

### VS Code Tasks
Several background tasks available (see `.vscode/tasks.json`):
- `Start API (dev)` - Runs backend in background
- `Start Frontend (dev)` - Runs frontend in background
- Use PowerShell task runner, not direct `npm` commands

### Adding New Endpoints
1. Create router file in `api/routers/` (e.g., `new_feature.py`)
2. Define FastAPI router: `router = APIRouter(prefix="/api/new-feature", tags=["new-feature"])`
3. Import & register in `api/routing.py` using `_safe_import()` pattern
4. Add route to `attach_routers()` call (order matters for precedence)
5. Test with `pytest -q tests/api/test_new_feature.py`

### Database Migrations (Additive Only)
- **No Alembic:** Migrations are Python functions in `backend/migrations/` (numbered like `001_add_slug_column.py`)
- Execute in `api/startup_tasks.py` → `run_startup_tasks()` (runs in background thread on app start)
- **Pattern:** Check if change exists before applying (e.g., column exists check via SQLAlchemy inspector)
- Migrations run automatically on deploy; no manual `alembic upgrade` needed

### Cloud Tasks Queue (Production Pattern)
- **Local dev:** Tasks may run inline or via local emulator (controlled by `CELERY_AUTO_FALLBACK` env var)
- **Production:** `infrastructure.tasks_client.enqueue_http_task()` posts to `/api/tasks/{task_name}`
- **Auth:** Tasks endpoints check `X-Tasks-Auth` header (set via `TASKS_AUTH` env var)
- **Endpoints:** `/api/tasks/transcribe`, `/api/tasks/assemble` (see `routers/tasks.py`)

## Frontend Patterns

### API Client (`lib/apiClient.js`)
- **Auto-origin detection:** Resolves API base from `VITE_API_BASE` or window.location (production) or uses Vite proxy (dev)
- **Helper:** `makeApi(token)` returns object with `.get()`, `.post()`, `.put()`, `.delete()` methods
- **Error handling:** Check `isApiError(e)` before displaying messages; backend returns `{detail: "..."}` or `{error: "..."}`

### Component Structure
- **shadcn/ui components:** `components/ui/` (Button, Dialog, etc.)
- **Feature components:** `components/dashboard/`, `components/media/`, `components/onboarding/`
- **Page routing:** React Router in `App.jsx` (no Next.js, plain SPA)
- **Auth context:** `AuthContext.jsx` provides `isAuthenticated`, `user`, `login()`, `logout()`

### Key UI Patterns
- **Waveform:** `Waveform.jsx` wraps WaveSurfer.js (see `vite.config.js` optimizeDeps for pre-bundling fix)
- **Admin check:** `isAdmin(user)` helper in `App.jsx` (checks `user.is_admin` or `user.role === 'admin'`, **no** hard-coded emails)
- **Toast notifications:** `useToast()` hook from `hooks/use-toast.js`, renders via `<Toaster />` in App

### Build & Deploy
- **Frontend build:** `npm run build` → `dist/` (static files served by Cloud Run web service)
- **Backend container:** `Dockerfile.cloudrun` (multi-stage build with Poetry/pip)
- **Cloud Build:** `cloudbuild.yaml` builds both services, pushes to Artifact Registry, deploys to Cloud Run
- **Secrets:** Retrieved from Secret Manager at deploy time (see `cloudbuild.yaml` preflight step)

## Common Pitfalls & Solutions

### Import Errors After Directory Rename
**Problem:** `from api...` imports fail because `backend/` not in sys.path  
**Solution:** `conftest.py` adds `backend/` to sys.path at test time; production uses PYTHONPATH or Docker WORKDIR

### Router Not Registered
**Problem:** New router endpoints return 404  
**Solution:** Check `api/routing.py` → ensure `_safe_import()` called and router passed to `attach_routers()`

### Transcription Not Starting
**Problem:** Upload succeeds but no transcript generated  
**Solution:** Check Cloud Tasks dispatch in `routers/media.py` (search for `enqueue_http_task`); verify `ASSEMBLYAI_API_KEY` set

### Episode Assembly Stuck in "Processing"
**Problem:** Episode never moves to `processed` status  
**Solution:** Check `/api/tasks/assemble` logs; verify Cloud Tasks auth header; confirm FFmpeg installed in container

### GCS Signed URL Expired
**Problem:** Audio playback 403s after 7 days  
**Solution:** Expected behavior; signed URLs expire. Re-generate via `/api/episodes/{id}/media-url` or trigger re-publish

### Test Failures Due to External Calls
**Problem:** Tests fail with "Connection refused" or timeout  
**Solution:** Add `requests_mocker.get(url, ...)` stub in test; see `tests/README.md` for HTTP mocking policy

### User Deletion Endpoint 405 Error
**Problem:** DELETE `/api/users/{user_id}` returns 405 Method Not Allowed  
**Solution:** Check `routers/users.py` or `routers/admin.py` for route registration; verify HTTP method decorator is `@router.delete()` not `@router.post()`; ensure route is included in `routing.py` attach list

### OP3 Analytics Issues
**Problem:** Download counts not updating, prefix not working, or stats not showing  
**Solution:** Check OP3 prefix configuration in RSS feed generation (`services/episodes/publisher.py`); verify `op3_analytics.py` service is correctly wrapping media URLs; confirm OP3 API credentials if using custom prefix

## File & Path Conventions

- **Local media:** `backend/local_media/` (dev only, .gitignored)
- **Temp files:** `backend/local_tmp/` (dev) or `/tmp/` (prod) (see `api/core/paths.py`)
- **Static assets:** `frontend/public/` → served at `/` root in production
- **API routes:** Always prefix with `/api/` (e.g., `/api/episodes`, not `/episodes`)
- **Env files:** `.env.local` (backend), `.env.production` (frontend), never commit real secrets

## Quick Reference Commands

```powershell
# Backend
pytest -q                          # Run fast unit tests
pytest -q -m integration           # Run integration tests
python -m uvicorn api.main:app --reload  # Start API manually

# Frontend
npm run dev                        # Start Vite dev server
npm run build                      # Production build
npm run preview                    # Preview production build

# Deploy
gcloud builds submit --config=cloudbuild.yaml --region=us-west1

# Database
# No manual migration commands - migrations auto-run on startup
```

## Key Files to Understand First

1. **`backend/api/app.py`** - FastAPI app initialization, middleware, startup tasks
2. **`backend/api/routing.py`** - Router registration & safe import pattern
3. **`backend/api/models/podcast.py`** - Core data models (Episode, Podcast, Template)
4. **`backend/api/core/config.py`** - Settings & environment variable handling
5. **`backend/api/services/episodes/assembler.py`** - Episode assembly orchestration
6. **`frontend/src/App.jsx`** - React app entry, routing, auth context
7. **`frontend/vite.config.js`** - Vite proxy, build config, WaveSurfer pre-bundling
8. **`cloudbuild.yaml`** - CI/CD pipeline, container builds, Cloud Run deployment
9. **`conftest.py`** - Test configuration, sys.path setup, fixtures

## When Things Break

1. **Check logs:** Cloud Logging (prod) or terminal output (dev) - **production logs take precedence**
2. **Verify env vars:** Missing API keys cause silent failures or 503s
3. **Test locally if time permits:** `pytest -q` should pass before pushing (but production fixes can't wait for full test coverage)
4. **Check routing:** New endpoints → update `routing.py`
5. **Migration issues:** Startup tasks run in background; check logs for SQL errors
6. **Frontend 404s:** Ensure Vite proxy config includes new API routes
7. **405 Method Not Allowed:** Check router HTTP method decorators match request method
8. **Remember:** If in doubt, prioritize getting production working. Dev environment is secondary.

## Known Active Issues

> **Note:** These are NOT in priority order - all need fixing as time permits

### Email Notifications (Broken)
- **Problem:** Email notifications don't send for: (1) raw files ready for assembly, (2) episode assembly complete
- **Location to check:** `services/mailer.py`, check for send triggers in `routers/media.py` (upload complete), `routers/tasks.py` or `services/episodes/assembler.py` (assembly complete)
- **Related:** Email service configuration, SMTP settings, async task execution

### Raw File Lifecycle Management (Missing Features)
- **Problem 1:** No "safe to delete" message after raw file used in successful episode
- **Problem 2:** No auto-delete setting for used raw files
- **Location to check:** `models/podcast.py` (MediaItem model), `routers/media.py`, need to track episode→raw_file relationship and add cleanup logic
- **Design note:** Need UI switch + backend job to mark/delete files after episode publish

### Raw File "Processing" State Bug (Critical for Dev)
- **Problem:** Raw files stuck in broken "processing" state when new build deployed
- **Symptom:** Very annoying during frequent rebuilds
- **Location to check:** `models/podcast.py` (MediaItem status field?), startup tasks that might need to reset orphaned processing states
- **Possible fix:** Add migration to reset stale "processing" states on startup, or timeout logic

### Flubber Audio Cutting (Needs Testing)
- **Status:** May be fixed but untested
- **Problem:** Flubber not actually making audio cuts (removing detected filler words/pauses)
- **Location to check:** `routers/flubber.py`, `services/flubber_helper.py`, check if detected segments are passed to FFmpeg correctly
- **Test:** Upload audio with obvious filler words, run Flubber, verify output audio is shorter

### Intern Audio Insertion (Broken)
- **Problem:** Spoken commands (e.g., "insert intro here") not inserting audio clips at detected locations
- **Location to check:** `routers/intern.py`, `services/intent_detection.py`, episode assembly logic that should respect Intern markers
- **Expected behavior:** Intern should mark timestamps, assembler should splice audio at those points

### Registration Flow Broken (FIXED - Oct 13)
- **Problem:** New users sent to Terms of Use page instead of onboarding wizard after email verification; users must log in twice
- **Root Cause:** (1) Terms acceptance during registration not recorded, (2) Race condition where App.jsx renders before AuthContext fetches fresh user data
- **Fixes Applied:**
  1. `backend/api/routers/auth/credentials.py` - Record terms acceptance during registration
  2. `frontend/src/pages/Verify.jsx` - Pre-fetch user data after auto-login
  3. `frontend/src/App.jsx` - Wait for AuthContext `hydrated` flag before routing decisions
- **Expected Behavior:** New users go directly to onboarding wizard after email verification, stay logged in
- **See:** `REGISTRATION_FLOW_CRITICAL_FIX_OCT13.md` for complete analysis
- **Status:** Code fix deployed, awaiting production testing

### Email Verification Codes (DEBUGGING - Oct 13)
- **Problem:** Six-digit verification codes always rejected as invalid when entered correctly
- **Status:** Diagnostic logging added, awaiting production test
- **Root Cause Hypothesis:** Type coercion issue between int→string conversion or PostgreSQL string comparison edge case
- **Files Modified:**
  1. `backend/api/routers/auth/credentials.py` - Explicit `str()` conversion for code generation, added `[REGISTRATION]` logging
  2. `backend/api/routers/auth/verification.py` - Type coercion for payload.code, extensive `[VERIFICATION]` debug logging with emoji markers
- **Debugging Approach:** Logs now show exact code types, repr(), and all pending codes for user to identify mismatch
- **Next Steps:** Deploy, test registration, check Cloud Run logs for `[REGISTRATION]` and `[VERIFICATION]` output
- **See:** `EMAIL_VERIFICATION_CODE_FIX_OCT13.md` for complete fix documentation
- **Test:** Register new account, enter verification code, check logs to see why comparison fails

### Spreaker Removal (In Progress)
- **Status:** Should be 100% gone for all users EXCEPT `scober@scottgerhardt.com` (temporary redundancy)
- **Location to check:** `routers/spreaker.py`, `routers/spreaker_oauth.py`, frontend components with Spreaker references
- **Whitelist logic:** Need to gate Spreaker features by user email check (temporary hack until migration complete)
- **See also:** `SPREAKER_REMOVAL_COMPLETE.md`, `SPREAKER_REMOVAL_VERIFICATION.md`

### Analytics Dashboard (Partially Working)
- **Problem:** Dashboard shows SOME analytics presence, but dedicated analytics section doesn't work
- **Location to check:** `routers/analytics.py`, `routers/dashboard.py` (what works), frontend `components/dashboard/` vs dedicated analytics page
- **OP3 Integration:** Related to OP3 prefix analytics issues (see below)

### AI Assistant Documentation (Needs Review)
- **Problem:** AI Assistant "Mike" may be misguiding or confusing users
- **Location to check:** `docs/AI_KNOWLEDGE_BASE.md`, `routers/assistant.py`, frontend `components/assistant/`
- **Action needed:** Review knowledge base for accuracy, update outdated workflows, test common user questions

### User Deletion 405 Error
- **Status:** Currently broken in production
- **Endpoint:** DELETE `/api/users/{user_id}` or admin equivalent
- **Symptom:** 405 Method Not Allowed
- **Location to check:** `routers/users.py`, `routers/admin.py`, `routing.py`

### OP3 Analytics Intermittent Issues
- **Status:** Ongoing reliability problems
- **Symptom:** Download counts not updating consistently
- **Location to check:** `services/op3_analytics.py`, RSS feed URL wrapping in `services/episodes/publisher.py`

### Manual Editor Audio Loading (FIXED - Oct 13)
- **Problem:** Manual Editor modal not loading audio waveforms (stuck showing "Loading..." with no waveform)
- **Root Cause:** `/api/episodes/{id}/edit-context` endpoint wasn't using proper GCS URL resolution
- **Fix Applied:** Changed to use `compute_playback_info()` function (same as episode history endpoint)
- **Location:** `backend/api/routers/episodes/edit.py`
- **See:** `MANUAL_EDITOR_AUDIO_FIX_OCT13.md` for full details
- **Status:** Code fix deployed, awaiting user testing

### Unscheduled Episodes Losing Audio (FIXED - Oct 13)
- **Problem:** Episodes show "No audio URL available" after being unscheduled from future publish date
- **Root Cause:** Unpublish function cleared `spreaker_episode_id`, removing the Spreaker stream URL fallback
- **Specific Case:** Episode 204 has no GCS path, no local file, and Spreaker ID was cleared → no audio sources left
- **Fixes Applied:**
  1. `backend/api/services/episodes/publisher.py` - Only clear `spreaker_episode_id` if successfully removed from Spreaker
  2. `backend/api/routers/episodes/publish.py` - Check for EITHER `final_audio_path` OR `gcs_audio_path` when publishing
  3. `frontend/src/components/dashboard/ManualEditor.jsx` - Better error messages and debug logging
- **See:** `EPISODE_204_AUDIO_MISSING_OCT13.md` for full technical analysis
- **Status:** Code fixes deployed, awaiting production verification

### GCS-ONLY ARCHITECTURE IMPLEMENTED (Oct 13) - BREAKING CHANGE
- **CRITICAL CHANGE:** GCS is now the SOLE source of truth for ALL media files - NO FALLBACKS
- **What Changed:**
  - GCS upload fails → Episode assembly FAILS (no "will rely on local files" warnings)
  - Local file checks REMOVED from `compute_playback_info()` 
  - Publishing REQUIRES `gcs_audio_path` (no local file fallback)
  - Spreaker is LEGACY ONLY (kept for old imported episodes)
  - Scheduled episodes can NOW be edited at any time (removed 7-day restriction)
- **Files Modified:**
  - `backend/worker/tasks/assembly/orchestrator.py` - Fail-fast GCS upload (no try/except fallback)
  - `backend/api/routers/episodes/common.py` - Removed local file Priority 2, only GCS + Spreaker legacy
  - `backend/api/routers/episodes/publish.py` - Require GCS path, reject local-only episodes
  - `frontend/src/components/dashboard/EpisodeHistory.jsx` - Allow editing scheduled episodes anytime
- **Breaking Changes:**
  - Dev environment MUST have GCS configured (no local file serving)
  - `playback_type` changed: "local" removed, "gcs" added
  - `local_final_exists` deprecated, replaced with `gcs_exists`
- **See:** `GCS_ONLY_ARCHITECTURE_OCT13.md` for complete architectural documentation
- **Status:** ✅ Implemented - ONE-WAY CHANGE, no rollback possible

### ONBOARDING GCS ENFORCEMENT (Oct 13) - CRITICAL FIX
- **Problem:** "Could not determine preview URL" error in onboarding Step 6 (intro/outro generation)
- **Root Cause:** Silent fallback to local files when GCS upload failed → breaks in production (ephemeral containers)
- **Solution:** Fail-fast enforcement for intro/outro/music/sfx/commercial categories
- **Files Modified:**
  - `backend/api/routers/media_tts.py` - TTS endpoint now fails if GCS upload doesn't return `gs://` URL
  - `backend/api/routers/media_write.py` - Manual upload endpoint now fails if GCS upload doesn't return `gs://` URL
  - Both endpoints clean up local files and raise clear HTTP 500 errors on GCS failure
- **Categories Enforced (fail-fast):**
  - `intro`, `outro`, `music`, `sfx`, `commercial` - **MUST** be in GCS
  - `main_content` - Still allows fallback (too large, needs separate migration)
- **Error Messages:**
  - "GCS upload failed - intro files must be in GCS for production use"
  - "Failed to upload music to cloud storage - this is required for production use"
- **See:** `ONBOARDING_GCS_FIX_OCT13.md` for complete technical details
- **Status:** ✅ Implemented - PRODUCTION CRITICAL (blocks onboarding flow)

### Intro/Outro Continue Button (FIXED - Oct 14)
- **Problem:** Continue button disabled on Intro/Outro onboarding step even when user has existing intro/outro selected
- **Root Cause:** Missing validation case for `introOutro` step in `nextDisabled` useMemo - button state was undefined
- **Solution:** Added proper validation that only blocks Continue if TTS/upload/record mode incomplete, allows Continue for 'existing' mode
- **File Modified:** `frontend/src/pages/Onboarding.jsx`
- **See:** `INTRO_OUTRO_CONTINUE_FIX_OCT14.md` for full details
- **Status:** ✅ Fixed - awaiting production verification

*Update this section as issues are discovered or resolved - not in priority order*

---

*Last updated: 2025-10-14*
