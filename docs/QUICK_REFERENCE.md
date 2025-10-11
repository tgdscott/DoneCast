# Quick Reference Guide

**Podcast Plus Plus - Cheat Sheets**  
**Last Updated:** October 11, 2025

---

## 📍 Quick Navigation

- [API Endpoints](#api-endpoints-quick-reference)
- [CLI Commands](#cli-commands-quick-reference)
- [Common Tasks](#common-tasks-quick-reference)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Deployment Checklist](#deployment-checklist)
- [Testing Commands](#testing-commands)
- [Troubleshooting](#troubleshooting-quick-fixes)

---

## API Endpoints Quick Reference

### Episodes

```
GET    /api/episodes/                     # List all episodes
GET    /api/episodes/?podcast_id={uuid}   # Filter by podcast
GET    /api/episodes/{id}                 # Get single episode
POST   /api/episodes/                     # Create new episode
PUT    /api/episodes/{id}                 # Update episode
DELETE /api/episodes/{id}                 # Delete episode
POST   /api/episodes/{id}/publish         # Publish episode
POST   /api/episodes/{id}/assemble        # Assemble audio
```

### Templates

```
GET    /api/templates/                    # List templates
GET    /api/templates/{id}                # Get template
POST   /api/templates/                    # Create template
PUT    /api/templates/{id}                # Update template
DELETE /api/templates/{id}                # Delete template
```

### Media

```
GET    /api/media/                        # List media files
GET    /api/media/?category={cat}         # Filter by category
POST   /api/media/upload/{category}       # Upload file
GET    /api/media/{id}                    # Get file details
DELETE /api/media/{id}                    # Delete file
```

### AI Features

```
POST   /api/ai/suggest-title              # Generate title
POST   /api/ai/suggest-description        # Generate description
GET    /api/ai/transcript-ready           # Check transcript status
POST   /api/audio/prepare-intern-by-file  # Detect edit commands
POST   /api/audio/flubber                 # Remove filler words
```

### User & Auth

```
GET    /api/users/me                      # Current user info
POST   /api/auth/login                    # Login
POST   /api/auth/logout                   # Logout
GET    /api/health                        # Health check
```

### RSS & Distribution

```
GET    /feeds/podcast/{podcast_id}        # RSS feed URL
GET    /api/distribution-status/{podcast_id}  # Platform status
```

**Authentication:**
All endpoints require `Authorization: Bearer {token}` header (except public RSS feed)

---

## CLI Commands Quick Reference

### Local Development

```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Start API server (with auto-reload)
python -m uvicorn api.main:app --reload --host localhost --port 8000

# Start API with specific port
python -m uvicorn api.main:app --reload --port 8010

# Start frontend dev server
cd frontend
npm run dev

# Install dependencies
pip install -r requirements.txt  # Python
cd frontend; npm install         # Node.js

# Database migrations (auto on startup)
# No manual command needed - migrations run at startup
```

### Testing

```powershell
# Run all tests
pytest

# Run with minimal output
pytest -q

# Run specific test file
pytest tests/test_episodes.py

# Run tests with keyword filter
pytest -k "test_create_episode"

# Run integration tests
pytest -m integration

# Run with coverage
pytest --cov=backend/api --cov-report=html

# Run specific test
pytest tests/test_episodes.py::test_create_episode -v
```

### Production Deployment

```bash
# Deploy everything (API + Frontend)
gcloud builds submit --config=cloudbuild.yaml --region=us-west1 --project=podcast612

# Deploy only if specific changes
git push origin main  # Triggers Cloud Build automatically (if configured)

# Check deployment status
gcloud builds list --limit=5 --region=us-west1

# View latest build logs
gcloud builds log $(gcloud builds list --limit=1 --format="value(id)")

# List running services
gcloud run services list --region=us-west1 --project=podcast612

# Get service details
gcloud run services describe podcast-api --region=us-west1

# View logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api" --limit=50

# Rollback to previous revision
gcloud run services update-traffic podcast-api --to-revisions=REVISION=100 --region=us-west1
```

### Database

```powershell
# Connect to local database
# (Connection string from .env file)

# Connect to Cloud SQL
gcloud sql connect podcast-db --user=postgres --project=podcast612

# Run migration (auto on startup)
python -m api.startup_tasks

# Backup database
gcloud sql backups create --instance=podcast-db

# List backups
gcloud sql backups list --instance=podcast-db
```

### Cloud Storage

```bash
# List buckets
gsutil ls

# List files in bucket
gsutil ls gs://ppp-media-us-west1/

# Copy file to bucket
gsutil cp local-file.mp3 gs://ppp-media-us-west1/user-id/episodes/

# Set CORS policy
gsutil cors set gcs-cors.json gs://ppp-media-us-west1

# Make bucket public (DON'T DO THIS - use signed URLs)
# gsutil iam ch allUsers:objectViewer gs://bucket-name  # ❌ NEVER
```

---

## Common Tasks Quick Reference

### Create New Episode

**UI Method:**
1. Click "Create Episode"
2. Select template
3. Upload audio (drag & drop)
4. Wait for transcription (2-3 min/hr)
5. Click "AI Suggest Title"
6. Click "AI Suggest Description"
7. Click "Assemble & Review"
8. Click "Publish"

**API Method:**
```bash
# 1. Upload audio
curl -X POST https://api.podcastplusplus.com/api/media/upload/main_content \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@episode-audio.mp3"

# 2. Create episode
curl -X POST https://api.podcastplusplus.com/api/episodes/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "podcast_id": "uuid",
    "title": "Episode Title",
    "episode_number": 1,
    "template_id": "uuid",
    "main_content_filename": "episode-audio.mp3"
  }'

# 3. Publish
curl -X POST https://api.podcastplusplus.com/api/episodes/{id}/publish \
  -H "Authorization: Bearer $TOKEN"
```

### Create New Template

**UI Method:**
1. Go to Templates tab
2. Click "Create Template"
3. Name template
4. Add segments:
   - Click "Intro" button → Select file or TTS
   - Main Content always episode-specific
   - Click "Outro" button → Select file or TTS
5. Add background music (optional)
6. Configure AI settings
7. Click "Save Template"

### Check Episode Status

```bash
# API
curl -X GET https://api.podcastplusplus.com/api/episodes/{episode_id} \
  -H "Authorization: Bearer $TOKEN"

# Look for:
# - "status": "draft" | "processing" | "published" | "failed"
# - "error_message": null (or error description)
```

### Regenerate RSS Feed

**Trigger update:**
1. Edit any episode metadata
2. Save
3. RSS updates within 5 minutes

**Or programmatically:**
- RSS regenerates on every episode publish/update
- No manual trigger needed

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl + K` | Open Mike (AI Assistant) |
| `Ctrl + N` | New Episode |
| `Ctrl + S` | Save (in editor) |
| `Ctrl + /` | Focus search |
| `Space` | Play/Pause audio player |
| `←` / `→` | Skip backward/forward 5s |
| `Shift + ←/→` | Skip backward/forward 30s |
| `Esc` | Close dialog/modal |
| `Ctrl + F5` | Hard refresh (bypass cache) |

---

## Deployment Checklist

### Pre-Deployment

- [ ] All tests passing (`pytest -q`)
- [ ] Code reviewed and approved
- [ ] Environment variables configured
- [ ] Secrets exist in Secret Manager
- [ ] Database migrations tested locally
- [ ] No breaking API changes (or version bumped)
- [ ] Documentation updated
- [ ] Changelog updated

### Deployment

- [ ] Run deployment command
  ```bash
  gcloud builds submit --config=cloudbuild.yaml --region=us-west1
  ```
- [ ] Monitor build progress (Cloud Build console)
- [ ] Wait for deployment completion (~5-10 minutes)
- [ ] Check build logs for errors

### Post-Deployment

- [ ] Verify API health: `curl https://api.podcastplusplus.com/api/health`
- [ ] Check frontend loads: https://app.podcastplusplus.com
- [ ] Test login flow
- [ ] Create test episode (end-to-end)
- [ ] Check logs for errors (first 10 minutes)
  ```bash
  gcloud logging read "resource.type=cloud_run_revision" --limit=50
  ```
- [ ] Verify database migrations ran successfully
- [ ] Monitor error rates (Cloud Monitoring)
- [ ] Notify team of deployment completion

### Rollback (if needed)

```bash
# List revisions
gcloud run revisions list --service=podcast-api --region=us-west1

# Route traffic to previous revision
gcloud run services update-traffic podcast-api \
  --to-revisions=PREVIOUS_REVISION=100 \
  --region=us-west1
```

---

## Testing Commands

### Run Different Test Types

```powershell
# All tests (unit only, skips integration)
pytest

# All tests including integration
pytest -m "unit or integration"

# Only integration tests
pytest -m integration

# Exclude slow tests
pytest -m "not slow"

# Specific test file
pytest tests/test_episodes.py

# Specific test function
pytest tests/test_episodes.py::test_create_episode

# Pattern matching
pytest -k "episode"  # Runs all tests with "episode" in name
```

### Coverage

```powershell
# Run with coverage report
pytest --cov=backend/api

# HTML coverage report
pytest --cov=backend/api --cov-report=html
# Open htmlcov/index.html in browser

# Show missing lines
pytest --cov=backend/api --cov-report=term-missing
```

### Debugging Tests

```powershell
# Verbose output
pytest -v

# Show print statements
pytest -s

# Stop on first failure
pytest -x

# Debug on failure (drops into debugger)
pytest --pdb

# Run last failed tests only
pytest --lf

# Run failed tests first, then others
pytest --ff
```

---

## Troubleshooting Quick Fixes

### Platform Issues

| Problem | Quick Fix |
|---------|-----------|
| Can't log in | Clear cookies, try incognito mode |
| Page won't load | Hard refresh (Ctrl+F5) |
| Upload fails | Check file size (<500MB), format (MP3/WAV/M4A) |
| Transcript stuck | Refresh page, wait 2-3 min per hour of audio |
| Episode stuck processing | Refresh page, wait 2 min, contact support if >10 min |
| RSS not updating | Wait 5 min, force refresh in podcast app |

### Development Issues

| Problem | Quick Fix |
|---------|-----------|
| Import errors | Activate venv: `.\.venv\Scripts\Activate.ps1` |
| Port already in use | Kill process: `Stop-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess` |
| Database connection fails | Check .env DATABASE_URL, verify DB running |
| Tests failing | Run `pytest --lf -v` to see specific failure |
| Frontend won't start | Delete `node_modules`, run `npm install` |

### Production Issues

| Problem | Quick Fix |
|---------|-----------|
| 500 errors | Check Cloud Logging for stack traces |
| Slow responses | Check Cloud SQL connections, may need pool adjustment |
| Out of memory | Check Cloud Run memory allocation, may need increase |
| Build fails | Check Cloud Build logs, often missing secret |
| Can't connect to API | Verify Cloud Run service deployed, check IAM permissions |

---

## Environment Variables Reference

### Required (Production)

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Storage
GCS_BUCKET=ppp-media-us-west1
GCS_SIGNED_URL_EXPIRATION=604800  # 7 days in seconds

# APIs
GEMINI_API_KEY=...
ELEVENLABS_API_KEY=...
ASSEMBLY_AI_API_KEY=...

# Auth
SECRET_KEY=...  # Session encryption
SESSION_SECRET=...  # JWT signing
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# Billing
STRIPE_SECRET_KEY=...
STRIPE_PUBLISHABLE_KEY=...
STRIPE_WEBHOOK_SECRET=...

# App
APP_ENV=production
FRONTEND_URL=https://app.podcastplusplus.com
BACKEND_URL=https://api.podcastplusplus.com
CORS_ALLOWED_ORIGINS=https://app.podcastplusplus.com
```

### Optional

```bash
# Logging
SENTRY_DSN=...  # Error tracking

# Features
DISABLE_RATE_LIMITING=false
MAX_UPLOAD_SIZE_MB=500

# OP3 Analytics
OP3_PREFIX_URL=https://op3.dev/e/...
```

---

## Git Commit Message Format

```
type(scope): Short description

Longer description if needed.

- Bullet points for multiple changes
- Use present tense ("add" not "added")
- Capitalize first letter

Fixes #123
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Formatting, no code change
- `refactor`: Code restructure, no behavior change
- `test`: Adding tests
- `chore`: Maintenance (deps, build config)

**Examples:**
```
feat(episodes): Add scheduled publishing

Users can now schedule episodes for future publication.

- Added scheduled_for field to Episode model
- Created background task to publish at scheduled time
- Updated UI with date/time picker

Fixes #456

---

fix(transcription): Handle Assembly AI timeout

Transcription jobs now retry on timeout errors.

---

docs(api): Update endpoint documentation

Added examples for all episode endpoints.
```

---

## Contact & Support

**Documentation Issues:** docs@podcastplusplus.com  
**Technical Support:** support@podcastplusplus.com  
**Emergency (Production Down):** emergency@podcastplusplus.com

**Documentation:** [Full Index](../DOCS_INDEX.md)

---

**Last Updated:** October 11, 2025
