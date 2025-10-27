# Podcast Plus Plus - AI Agent Instructions

## Project Overview
Self-hosted podcast creation platform with AI-powered features. Full-stack app: FastAPI backend + React frontend, deployed on Google Cloud Run.

**Production Domain**: `podcastplusplus.com` (primary), `getpodcastplus.com` (legacy, maintained for backward compatibility)  
**Key Tech:** Python 3.11+, FastAPI, SQLAlchemy 2.0/SQLModel, PostgreSQL, React 18, Vite, TailwindCSS, GCS, Cloud Tasks

## ⚠️ Critical Constraints

### NEVER Hallucinate, Assume, or Guess
**CRITICAL: Details matter. Accuracy is non-negotiable.**

- ❌ NEVER hallucinate instructions or specifications not explicitly given by the user
- ❌ NEVER assume how features should work without asking
- ❌ NEVER guess at implementation details
- ✅ If you're unsure, ASK the user for clarification
- ✅ Repeat back your understanding and ask for confirmation before implementing
- ✅ State exactly what you know vs. what you're inferring

**Example of correct behavior:**
- User: "Pro tier should use Auphonic"
- Agent: "To confirm: Pro tier → Auphonic pipeline. What about Free, Creator, and Unlimited tiers? Should they use AssemblyAI?"
- NOT: "I'll set Creator and Enterprise to use Auphonic too since they're premium tiers."

**When in doubt:** Ask, don't assume. Getting it wrong wastes time and creates bugs.

### NEVER Start Builds Without Permission
**ALWAYS ASK before running `gcloud builds submit`.** User manages builds in separate windows to avoid interruptions. Google charges heavily for builds, so each one must be intentional.

**What to do instead:**
- ✅ Prepare all code changes
- ✅ Run local tests
- ✅ Document what needs deploying
- ✅ ASK: "Ready to deploy? I have X changes ready."
- ❌ NEVER run `gcloud builds submit` automatically
- ❌ NEVER use `isBackground: true` for build commands

### Production First - BUT Fix Root Cause, Don't Rollback
**CRITICAL CONTEXT: Production is currently in TESTING PHASE - no general public users yet.**

**Deployment Philosophy:**
- ❌ **NEVER rollback just to "make it work"** - this hides problems
- ✅ **ALWAYS fix the underlying problem** - even if it takes longer
- ✅ **Production downtime is acceptable** during testing phase
- ✅ **Use failures as learning opportunities** to improve the system

**When production breaks:**
1. **Investigate the root cause FIRST** - don't rush to rollback
2. **Fix the actual problem** - not just the symptoms
3. **Deploy the fix** - test in production (we're in testing phase)
4. **Only rollback** if the fix will take hours/days AND there's a critical demo

**Why this matters:**
- Rolling back = same bug will happen again later
- Rolling back = wastes time on the same problem twice
- Rolling back = we don't learn what's actually broken
- Testing phase = perfect time to find and fix these issues

**All fixes and features MUST prioritize production environment.** Local dev is nice-to-have but production stability is non-negotiable. If a change helps both, great. If it's a choice, production wins every time.

### Branding: NEVER Use "Podcast++"
**CRITICAL: Brand name must ALWAYS be "Podcast Plus Plus" or "Plus Plus" - NEVER "Podcast++"**

This is non-negotiable for URL clarity and brand consistency. The ++ notation creates confusion with URLs and looks unprofessional.

**Correct usage:**
- ✅ "Podcast Plus Plus" (full name)
- ✅ "Plus Plus" (short form)
- ✅ "Powered by Podcast Plus Plus"
- ✅ "Your Podcast Plus Plus RSS feeds"
- ❌ "Podcast++" (NEVER use this anywhere)
- ❌ "podcast++" (NEVER use this anywhere)

**This applies to:**
- UI text, labels, tooltips
- Documentation, comments, commit messages
- Error messages, logs
- Email templates
- RSS feed metadata
- Footer branding
- API responses

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

### Database Naming Convention (CRITICAL)
**Table names:** NO underscores (e.g., `podcast`, `episode`, `podcastwebsite`, `mediaitem`)  
**Column names:** YES underscores (e.g., `user_id`, `created_at`, `sections_order`)  
**Exceptions:** Assistant tables DO have underscores (`assistant_conversation`, `assistant_message`, `feedback_submission`, `assistant_guidance`)

**ALWAYS double-check table names before using in SQL or migrations.** Getting this wrong causes silent failures in PostgreSQL.

### Flubber Feature (CRITICAL - DO NOT CONFUSE WITH FILLER WORD REMOVAL)

**WHAT FLUBBER IS:**
- User says the word "flubber" DURING RECORDING when they make a blatant mistake (e.g., mispronounce a word, say the wrong name, stumble over a sentence)
- System detects the spoken keyword "flubber" in the transcript
- Analyzes the audio BEFORE the "flubber" marker to find repeated/incorrect words
- Cuts out several seconds (typically 5-30 seconds) of the "flub" section
- This is a MANUAL, USER-TRIGGERED editing tool for fixing specific mistakes

**WHAT FLUBBER IS NOT:**
- ❌ NOT automatic filler word removal ("um", "uh", "like", "you know")
- ❌ NOT AI-powered mistake detection
- ❌ NOT continuous throughout the episode
- ❌ NOT the same as Auphonic's automatic filler word cutting
- ❌ NOT silence removal
- ❌ NOT breath removal

**Example Flubber Use Case:**
1. User recording: "Welcome to episode 42 with our guest... uh... John... wait no... flubber... Welcome to episode 42 with our guest Sarah Johnson"
2. User said "flubber" to mark that they want to cut the mistake
3. System detects "flubber" keyword at timestamp 00:15
4. Analyzes words before "flubber", finds repeated phrase "Welcome to episode 42 with our guest"
5. Cuts from 00:10 to 00:15 (removes "John... wait no... flubber")
6. Final audio: "Welcome to episode 42 with our guest Sarah Johnson" (seamless)

**Code Location:**
- `backend/api/routers/flubber.py` - Flubber detection & cutting endpoints
- `backend/api/services/flubber_helper.py` - Audio cutting logic
- `backend/api/services/keyword_detector.py` - "flubber" keyword detection in transcript

**DO NOT:**
- ❌ Call Flubber "filler word removal"
- ❌ Compare Flubber to Auphonic's automatic filler word cutting (they are completely different)
- ❌ Assume Flubber removes "um" or "uh" (it doesn't - it only cuts sections marked with the keyword "flubber")
- ❌ Suggest Flubber as an alternative to automatic filler word removal tools

**Filler word removal (separate feature we DON'T have):**
- Automatic detection of "um", "uh", "like", "you know" throughout entire episode
- Removes these words automatically without user marking them
- Continuous processing, not keyword-triggered
- We currently DO NOT have this feature (would need to build or use Auphonic)

### Subscription Tier → Transcription Pipeline Routing (CRITICAL)

**PRODUCTION SPECIFICATION (DO NOT CHANGE WITHOUT USER APPROVAL):**

| Tier | Price | Transcription Pipeline | Audio Processing |
|------|-------|----------------------|------------------|
| **Pro** | $79/mo | **Auphonic** | Professional (denoise, leveling, EQ, filler removal) |
| **Free** | 30 min | **AssemblyAI** | Custom (manual cleanup, Flubber, Intern) |
| **Creator** | $39/mo | **AssemblyAI** | Custom (manual cleanup, Flubber, Intern) |
| **Unlimited** | Custom | **AssemblyAI** | Custom (manual cleanup, Flubber, Intern) |

**Key Implementation:**
- `backend/api/services/auphonic_helper.py::should_use_auphonic()` - Tier routing logic
- `backend/worker/tasks/assembly/orchestrator.py::_finalize_episode()` - Calls routing function
- Only Pro tier returns `True`, all other tiers return `False`

**CRITICAL RULES:**
- ❌ NEVER assume Creator or Unlimited tiers use Auphonic
- ❌ NEVER guess at tier behavior without checking the code
- ✅ Pro tier = Auphonic (handles transcription, filler removal, all processing)
- ✅ All other tiers = AssemblyAI + custom processing pipeline
- ✅ If in doubt, ASK the user before changing tier routing logic

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

### Database Migrations (Manual via PGAdmin)
- **CRITICAL: All migrations done manually by user via PGAdmin**
- **Your job:** Provide ONLY the SQL commands needed
- **DO NOT:**
  - ❌ Create Python migration files
  - ❌ Register migrations in `one_time_migrations.py`
  - ❌ Add to `startup_tasks.py`
  - ❌ Use Alembic or any automated migration system
- **DO:**
  - ✅ Generate clean SQL with idempotent checks (IF NOT EXISTS, DO $$ blocks)
  - ✅ Include verification queries at the end
  - ✅ Explain what each SQL statement does
  - ✅ Provide rollback SQL if applicable
- **Example output format:**
  ```sql
  -- Add new column with safety check
  DO $$
  BEGIN
      IF NOT EXISTS (
          SELECT 1 FROM information_schema.columns 
          WHERE table_name = 'users' AND column_name = 'new_field'
      ) THEN
          ALTER TABLE users ADD COLUMN new_field TEXT;
      END IF;
  END$$;
  
  -- Verify
  SELECT column_name, data_type FROM information_schema.columns 
  WHERE table_name = 'users' AND column_name = 'new_field';
  ```

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

### Email Notifications (Partially Fixed - Oct 19)
- **Status:** Episode assembly emails NOW FIXED ✅, raw file transcription emails still need investigation
- **Fixed:** Episode assembly completion emails now send via `worker/tasks/assembly/orchestrator.py::_finalize_episode()`
- **Remaining Problem:** Raw file transcription completion emails may not be working (needs verification)
- **Location to check:** `services/mailer.py`, `routers/media.py` (upload complete), transcription task email triggers
- **See:** `EPISODE_ASSEMBLY_EMAIL_FIX_OCT19.md` for completed fix details
- **Related:** Email service configuration, SMTP settings, async task execution

### Raw File Lifecycle Management (BACKEND COMPLETE - Oct 23)
- **Status:** ✅ Backend implementation complete, ⏳ awaiting frontend integration
- **Fixed:** "Safe to delete" notifications now created when auto-delete disabled
- **Implementation:**
  - Added `used_in_episode_id` field to MediaItem model (tracks which episode used the file)
  - Enhanced `_cleanup_main_content()` in orchestrator to create notifications when auto_delete=False
  - Migration 029 adds database column automatically on deployment
  - Notification created: "Your raw file 'X' was successfully used in 'Episode Y' and can now be safely deleted"
- **Files Modified:** 
  - `backend/api/models/podcast.py` - MediaItem model
  - `backend/worker/tasks/assembly/orchestrator.py` - Notification logic
  - `backend/migrations/029_add_mediaitem_used_in_episode.py` - Database migration
  - `backend/api/startup_tasks.py` - Migration registration
- **Frontend TODO:** Media Library needs badges showing "Used in Episode X" for files where `used_in_episode_id IS NOT NULL`
- **See:** `RAW_FILE_CLEANUP_NOTIFICATION_IMPLEMENTATION_OCT23.md` for complete technical details

### Raw File "Processing" State Bug (FIXED - Oct 23)
- **Problem SOLVED:** Raw files stuck in broken "processing" state when new build deployed
- **Root Cause:** Cloud Run ephemeral storage wiped on deployment, local transcript files lost
- **Solution:** Proactive transcript recovery at startup (`_recover_raw_file_transcripts()` in `startup_tasks.py`)
- **Implementation:** Queries `MediaTranscript` table, downloads missing transcripts from GCS, restores to local storage
- **Files Modified:** `backend/api/startup_tasks.py`
- **See:** `RAW_FILE_TRANSCRIPT_RECOVERY_FIX_OCT23.md` for complete technical details
- **Status:** ✅ Fixed - transcript recovery runs automatically on every deployment

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

### User Deletion 500 Error (FIXED - Oct 17)
- **Problem:** 500 Internal Server Error when deleting users via admin dashboard
- **Root Cause:** Database foreign key constraint violations - missing cascade deletion for child records
- **Solution:** Implemented comprehensive cascade deletion for all user-related tables (terms, verifications, subscriptions, notifications, assistant data, websites)
- **Files Fixed:** `backend/api/routers/admin/users.py`
- **See:** `ADMIN_USER_DELETE_500_FIX_OCT17.md`

### Admin Podcasts Tab (FIXED - Oct 17)
- **Problem:** Podcasts tab in admin dashboard completely broken
- **Root Cause:** Missing `useResolvedTimezone()` hook in `AdminPodcastsTab` component
- **Solution:** Added timezone hook and defensive date formatting with fallbacks
- **Files Fixed:** `frontend/src/components/admin-dashboard.jsx`
- **See:** `ADMIN_PODCASTS_TAB_FIX_OCT17.md`

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

### TERMS VERSION MANAGEMENT (Oct 22 - CRITICAL FIX)
- **Problem SOLVED**: Users forced to re-accept terms multiple times per day
- **Root Cause**: `TERMS_VERSION` bumped from "2025-09-01" to "2025-09-19" but existing users still had old version
- **Solution**: Automatic migration on startup (`backend/migrations/099_auto_update_terms_versions.py`)
- **Files Modified**: 
  - `backend/api/core/config.py` - Updated TERMS_VERSION with warning comments
  - `backend/api/startup_tasks.py` - Added auto-migration execution
  - `backend/migrations/099_auto_update_terms_versions.py` - NEW migration file
- **CRITICAL RULE**: Only bump `TERMS_VERSION` when terms content actually changes (not for deployments/dates)
- **See**: `TERMS_RE_ACCEPTANCE_BUG_FIX_OCT22.md` for complete fix documentation
- **See**: `TERMS_VERSION_MANAGEMENT_CRITICAL.md` for management guidelines
- **Status**: ✅ Fixed - auto-migration runs on every deployment

### OAuth Google Login Timeouts (FIXED - Oct 19)
- **Problem:** Intermittent 30-second timeout when clicking "Sign in with Google", works on refresh
- **Root Cause:** (1) OAuth client fetching Google metadata on EVERY request, (2) No retry logic for transient network failures
- **Solution:** Global OAuth client caching + automatic retry with cache invalidation on timeout
- **Files Modified:**
  - `backend/api/routers/auth/utils.py` - Added `_oauth_client_cache` global, cache OAuth client after first successful init
  - `backend/api/routers/auth/oauth.py` - Added 3-attempt retry loop with timeout detection in `login_google()` endpoint
- **Benefits:**
  - Metadata fetched ONCE per server lifetime (not per-request) = 99% of timeouts eliminated
  - Automatic retry (3 attempts) for transient failures = better UX
  - User-friendly 503 error message instead of generic 500
- **See:** `OAUTH_TIMEOUT_RESILIENCE_OCT19.md` for complete technical analysis
- **Status:** ✅ Fixed - awaiting production testing

*Update this section as issues are discovered or resolved - not in priority order*

## Recent UI Improvements

### Episode Creation Two-Button Interface (Oct 19)
- **Change:** Dashboard now shows TWO separate entry points for episode creation instead of one combined flow
- **Buttons:**
  - **"Record or Upload Audio"** (Mic icon) - Always visible, primary style, goes directly to recorder/uploader
  - **"Assemble New Episode"** (Library icon) - Conditional visibility (only when ready audio exists), outline style, goes to Step 2 with preuploaded mode
- **Visibility Logic:** "Assemble New Episode" only shows when `preuploadItems.some((item) => item?.transcript_ready) === true`
- **Files Modified:**
  - `frontend/src/components/dashboard.jsx` - Two-button implementation
  - `frontend/src/components/dashboard/hooks/usePodcastCreator.js` - Step 2 title changed to "Select Main Content"
  - `frontend/src/components/dashboard/podcastCreatorSteps/StepUploadAudio.jsx` - Removed confusing audio prep checklist
- **Rationale:** Separates "prepare audio" from "create episode" workflows to reduce cognitive load for users with ready audio
- **Icons:** lucide-react `Mic` and `Library` icons
- **Tour Impact:** Dashboard tour needs update - `data-tour-id="dashboard-new-episode"` no longer exists, now `dashboard-record-upload` and `dashboard-assemble-episode`
- **See:** `EPISODE_INTERFACE_SEPARATION_OCT19.md` for full implementation details
- **Status:** ✅ Implemented - awaiting production testing

---

*Last updated: 2025-10-19*
