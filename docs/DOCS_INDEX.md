# Documentation Index

**Podcast Plus Plus - Complete Documentation**  
**Last Updated:** October 11, 2025

---

## 🚀 Start Here

### New Users
- **[README](../README.md)** - Project overview and quick start
- **[User Manual](user-guides/USER_MANUAL.md)** - Complete user guide (recommended starting point)
- **[Quick Start Guide](user-guides/QUICK_START.md)** - Get started in 5 minutes
- **[FAQ](user-guides/FAQ.md)** - Frequently asked questions

### Developers
- **[Development Guide](development/DEVELOPMENT_GUIDE.md)** - Setup and conventions
- **[API Reference](development/API_REFERENCE.md)** - Complete API documentation
- **[Contributing Guide](development/CONTRIBUTING.md)** - How to contribute code
- **[Testing Guide](../tests/README.md)** - Running tests

### DevOps/Admins
- **[Deployment Guide](deployment/DEPLOYMENT_GUIDE.md)** - Production deployment
- **[Monitoring Guide](deployment/MONITORING.md)** - Logs, metrics, alerts
- **[Troubleshooting Guide](troubleshooting/TROUBLESHOOTING_GUIDE.md)** - Common issues

---

## 📖 Documentation by Category

### 👤 User Guides

**Getting Started:**
- [User Manual](user-guides/USER_MANUAL.md) - Comprehensive user guide
- [Quick Start](user-guides/QUICK_START.md) - 5-minute walkthrough
- [Onboarding Wizard Guide](user-guides/ONBOARDING_GUIDE.md) - First-time setup

**Features:**
- [Creating Episodes](user-guides/EPISODE_CREATION.md) - Step-by-step episode guide
- [Template System](user-guides/TEMPLATES_EXPLAINED.md) - Understanding templates
- [Audio Processing](user-guides/AUDIO_FEATURES.md) - Intern, Flubber, editing
- [AI Features](user-guides/AI_FEATURES.md) - AI assistant, content generation
- [Publishing & RSS](user-guides/PUBLISHING_GUIDE.md) - Distribution to platforms
- [Analytics](user-guides/ANALYTICS_GUIDE.md) - Tracking your audience

**Reference:**
- [FAQ](user-guides/FAQ.md) - Common questions and answers
- [Keyboard Shortcuts](user-guides/SHORTCUTS.md) - Speed up your workflow
- [Glossary](user-guides/GLOSSARY.md) - Terms and definitions

### 🔧 Features Documentation

**Core Features:**
- [Template System](features/TEMPLATES.md) - Reusable episode structures
- [Episode Assembly](features/ASSEMBLY.md) - How audio is processed
- [Media Library](features/MEDIA_LIBRARY.md) - File management
- [RSS Feed Generation](START_HERE_RSS_FEED.md) - Self-hosted feeds
- [Signed URLs](features/SIGNED_URLS.md) - 7-day expiration system

**AI Features:**
- [AI Assistant "Mike"](ai-assistant-implementation.md) - Context-aware help
- [Transcription](features/TRANSCRIPTION.md) - Assembly AI integration
- [Content Generation](features/AI_CONTENT_GENERATION.md) - Titles, descriptions
- [Intern Mode](features/INTERN.md) - Spoken editing commands
- [Flubber](features/FLUBBER.md) - Filler word removal
- [TTS Integration](features/TEXT_TO_SPEECH.md) - ElevenLabs voices

**Audio Processing:**
- [FFmpeg Assembly](features/FFMPEG_PROCESSING.md) - Segment stitching
- [Background Music](features/BACKGROUND_MUSIC.md) - Ducking and mixing
- [Normalization](features/AUDIO_NORMALIZATION.md) - Volume leveling
- [Format Support](features/AUDIO_FORMATS.md) - Supported file types

**Integrations:**
- [Stripe Billing](STRIPE_INDEX.md) - Payment system
- [OP3 Analytics](OP3_ANALYTICS_GUIDE.md) - Download tracking
- [Google OAuth](features/AUTHENTICATION.md) - User login
- [Cloud Storage](features/GCS_INTEGRATION.md) - Google Cloud Storage

**User Experience:**
- [Recurring Schedules](features/RECURRING_SCHEDULES.md) - Automatic publishing
- [Episode History](EPISODE_HISTORY_QUICK_REF.md) - Version tracking
- [Timezone Settings](TIMEZONE_SETTINGS_SUMMARY.md) - User-specific times
- [Upload Progress](UPLOAD_PROGRESS_IMPLEMENTATION.md) - Real-time feedback

### 🏗️ Architecture & Design

**System Architecture:**
- [System Overview](architecture/SYSTEM_ARCHITECTURE.md) - High-level design
- [Data Models](architecture/DATA_MODELS.md) - Database schema
- [API Design](architecture/API_DESIGN.md) - REST conventions
- [Authentication Flow](architecture/AUTH_FLOW.md) - JWT and OAuth

**Infrastructure:**
- [Cloud Run Services](architecture/CLOUD_RUN.md) - Containerized deployment
- [Cloud SQL](architecture/DATABASE.md) - PostgreSQL setup
- [Cloud Storage](architecture/GCS.md) - Media bucket configuration
- [Cloud Tasks](architecture/BACKGROUND_JOBS.md) - Async processing

**Audio Pipeline:**
- [Assembly Pipeline](architecture/ASSEMBLY_PIPELINE.md) - Episode processing flow
- [Transcription Pipeline](architecture/TRANSCRIPTION_PIPELINE.md) - Speech-to-text
- [Audio Orchestrator](architecture/AUDIO_ORCHESTRATOR.md) - Processing engine

### 💻 Development

**Getting Started:**
- [Development Setup](development/DEVELOPMENT_GUIDE.md) - Local environment
- [Prerequisites](development/PREREQUISITES.md) - Required software
- [Environment Variables](development/ENV_VARS.md) - Configuration

**Development Practices:**
- [Code Style](development/CODE_STYLE.md) - Python and React conventions
- [Git Workflow](GIT_COMMIT_TEMPLATE.md) - Commit messages and branching
- [Testing Strategy](development/TESTING.md) - Unit, integration, e2e
- [Debugging](development/DEBUGGING.md) - Common debugging techniques

**API Development:**
- [API Reference](development/API_REFERENCE.md) - All endpoints
- [Adding Endpoints](development/NEW_ENDPOINTS.md) - How to add routes
- [Request Validation](development/VALIDATION.md) - Pydantic schemas
- [Error Handling](development/ERROR_HANDLING.md) - Standard responses

**Frontend Development:**
- [React Components](development/REACT_COMPONENTS.md) - Component structure
- [State Management](development/STATE_MANAGEMENT.md) - React hooks and context
- [UI Components](development/UI_COMPONENTS.md) - shadcn/ui usage
- [Styling](development/STYLING.md) - TailwindCSS conventions

**Database:**
- [Migrations](development/MIGRATIONS.md) - Alembic workflow
- [Models](development/DATABASE_MODELS.md) - SQLModel definitions
- [Queries](development/DATABASE_QUERIES.md) - SQLAlchemy patterns

### 🚀 Deployment

**Production Deployment:**
- [Deployment Guide](deployment/DEPLOYMENT_GUIDE.md) - Complete process
- [Cloud Build](cloud-run-deploy.md) - CI/CD pipeline
- [Environment Setup](deployment/PRODUCTION_ENV.md) - Cloud Run config
- [Secret Management](deployment/SECRETS.md) - Secret Manager usage

**Deployment Procedures:**
- [Pre-Deployment Checklist](deployment/PRE_DEPLOYMENT.md) - Before deploying
- [Deployment Steps](deployment/DEPLOYMENT_STEPS.md) - Step-by-step
- [Post-Deployment](deployment/POST_DEPLOYMENT.md) - Verification
- [Rollback Procedure](deployment/ROLLBACK.md) - Emergency rollback

**Monitoring & Operations:**
- [Monitoring Guide](deployment/MONITORING.md) - Cloud Logging and metrics
- [Health Checks](deployment/HEALTH_CHECKS.md) - Service monitoring
- [Alerting](deployment/ALERTING.md) - Alert configuration
- [Performance](startup-performance.md) - Optimization

**Historical Deployments:**
- [Deployment History](deployment/DEPLOYMENT_HISTORY.md) - Past deployments
- [Major Releases](deployment/MAJOR_RELEASES.md) - Version summaries

### 🔧 Troubleshooting

**Common Issues:**
- [Troubleshooting Guide](troubleshooting/TROUBLESHOOTING_GUIDE.md) - Comprehensive guide
- [Error Codes](troubleshooting/ERROR_CODES.md) - All error messages
- [FAQ](user-guides/FAQ.md) - Quick answers

**Specific Problems:**
- [Upload Issues](troubleshooting/UPLOAD_ISSUES.md) - File upload failures
- [Transcription Issues](troubleshooting/TRANSCRIPTION.md) - Stuck processing
- [Assembly Issues](troubleshooting/ASSEMBLY.md) - Episode assembly failures
- [RSS Feed Issues](troubleshooting/RSS_ISSUES.md) - Feed not updating
- [Authentication Issues](troubleshooting/AUTH_ISSUES.md) - Login problems

**Performance Issues:**
- [Slow Performance](troubleshooting/PERFORMANCE.md) - Speed issues
- [Database Issues](troubleshooting/DATABASE.md) - Connection problems
- [Memory Issues](troubleshooting/MEMORY.md) - Out of memory errors

**Historical Issues (Archived):**
- See [Archive](archive/) for resolved historical issues

### 📊 Analytics & Monitoring

- [OP3 Integration](OP3_INTEGRATION_COMPLETE.md) - Download tracking
- [Analytics Dashboard](ANALYTICS_USER_GUIDE.md) - User guide
- [Analytics Deployment](ANALYTICS_DEPLOYMENT_CHECKLIST.md) - Setup guide
- [Analytics Quick Reference](ANALYTICS_QUICK_REFERENCE.md) - Commands

### 💳 Billing & Subscriptions

**Stripe Integration:**
- [Stripe Index](STRIPE_INDEX.md) - Overview and links
- [Stripe Setup](STRIPE_SETUP_EXPLAINED.md) - Initial configuration
- [Stripe Keys Guide](STRIPE_KEYS_GUIDE.md) - Managing API keys
- [Stripe Migration Guide](STRIPE_LIVE_MIGRATION_GUIDE.md) - Test to live
- [Stripe Quick Reference](STRIPE_QUICK_REFERENCE.md) - Common tasks

**User Billing:**
- [Subscription Plans](features/SUBSCRIPTION_PLANS.md) - Available tiers
- [Usage Tracking](features/USAGE_TRACKING.md) - Minute calculation
- [Billing FAQ](user-guides/BILLING_FAQ.md) - Common billing questions

### 🎨 AI Assistant

**Configuration & Training:**
- [AI Assistant Implementation](ai-assistant-implementation.md) - Technical overview
- [AI Assistant Config](AI_ASSISTANT_CONFIG.md) - Configuration
- [AI Knowledge Base](AI_KNOWLEDGE_BASE.md) - **For AI context (Mike's training data)**
- [AI Character](AI_ASSISTANT_CHARACTER.md) - Personality and tone
- [AI Training Guide](AI_ASSISTANT_TRAINING_GUIDE.md) - Updating Mike

**Features:**
- [Highlighting](AI_ASSISTANT_HIGHLIGHTING.md) - UI element highlighting
- [Context Awareness](AI_ASSISTANT_ENHANCEMENTS.md) - Page-specific help
- [Onboarding Status](AI_ASSISTANT_ONBOARDING_STATUS.md) - First-time user help

### 🗺️ Roadmap & Planning

- [Full Roadmap](FULL_PODCAST_HOST_ROADMAP.md) - Complete feature status
- [Migration Roadmap](MIGRATION_VISUAL_ROADMAP.md) - Spreaker to self-hosted
- [Next Actions](NEXT_ACTIONS_AGENDA.md) - Upcoming tasks

### 🔄 Migrations & Updates

**Major Migrations:**
- [Spreaker Migration Guide](SPREAKER_MIGRATION_GUIDE.md) - From Spreaker to self-hosted
- [Self-Hosted Quick Start](SELF_HOSTED_QUICK_START.md) - Post-migration setup
- [RSS Schema Updates](RSS_SCHEMA_IMPLEMENTATION_COMPLETE.md) - Database changes

**Database Migrations:**
- [Running Migrations](development/MIGRATIONS.md) - How to migrate
- [RSS Database Schema](RSS_DATABASE_SCHEMA_UPDATES.md) - RSS fields

### 📜 Legal & Policies

- [Privacy Policy](privacy_policy_podcast_plus_draft_v_1.md) - User privacy
- [Terms of Use](terms_of_use_podcast_pro_plus_draft_v_1.md) - Service terms
- [Patent Notice](PATENT_NOTICE_IMPLEMENTATION.md) - Patent information

---

## 📁 Documentation by Location

### Root Directory (`/`)
- [README.md](../README.md) - Main project overview

### `/docs`

#### User Guides (`/docs/user-guides`)
- User Manual
- Quick Start
- FAQ
- Feature guides

#### Features (`/docs/features`)
- Feature specifications
- Implementation details
- User-facing documentation

#### Architecture (`/docs/architecture`)
- System design
- Data models
- Infrastructure

#### Development (`/docs/development`)
- Developer guides
- API reference
- Coding standards

#### Deployment (`/docs/deployment`)
- Deployment procedures
- Configuration
- Monitoring

#### Troubleshooting (`/docs/troubleshooting`)
- Common issues
- Error messages
- Resolution steps

#### Archive (`/docs/archive`)
- Historical documentation
- Resolved issues (October 2025)
- Deprecated features

### `/tests`
- [Testing README](../tests/README.md) - Test documentation

---

## 🔍 Documentation by Task

### "I want to..."

**...learn about the platform:**
→ [README](../README.md) → [User Manual](user-guides/USER_MANUAL.md)

**...create my first episode:**
→ [Quick Start](user-guides/QUICK_START.md) → [Episode Creation](user-guides/EPISODE_CREATION.md)

**...understand templates:**
→ [Templates Explained](user-guides/TEMPLATES_EXPLAINED.md) → [Template System](features/TEMPLATES.md)

**...set up development environment:**
→ [Development Guide](development/DEVELOPMENT_GUIDE.md) → [Prerequisites](development/PREREQUISITES.md)

**...deploy to production:**
→ [Deployment Guide](deployment/DEPLOYMENT_GUIDE.md) → [Pre-Deployment Checklist](deployment/PRE_DEPLOYMENT.md)

**...troubleshoot an issue:**
→ [Troubleshooting Guide](troubleshooting/TROUBLESHOOTING_GUIDE.md) → [Error Codes](troubleshooting/ERROR_CODES.md)

**...integrate Stripe billing:**
→ [Stripe Index](STRIPE_INDEX.md) → [Stripe Setup](STRIPE_SETUP_EXPLAINED.md)

**...understand OP3 analytics:**
→ [OP3 Guide](OP3_ANALYTICS_GUIDE.md) → [Analytics User Guide](ANALYTICS_USER_GUIDE.md)

**...add a new feature:**
→ [Contributing Guide](development/CONTRIBUTING.md) → [Adding Endpoints](development/NEW_ENDPOINTS.md)

**...migrate from Spreaker:**
→ [Spreaker Migration Guide](SPREAKER_MIGRATION_GUIDE.md) → [Self-Hosted Quick Start](SELF_HOSTED_QUICK_START.md)

---

## 📝 Quick Reference Cards

### API Quick Reference
**Most-used endpoints:**
```
GET    /api/episodes/              List episodes
POST   /api/episodes/              Create episode
POST   /api/episodes/{id}/publish  Publish episode
GET    /api/templates/             List templates
POST   /api/media/upload/{category} Upload audio
```

See [API Reference](development/API_REFERENCE.md) for complete list.

### CLI Quick Reference
**Development:**
```powershell
# Start API
python -m uvicorn api.main:app --reload

# Start frontend
cd frontend; npm run dev

# Run tests
pytest -q

# Run migrations
# (automatic on startup)
```

See [Development Guide](development/DEVELOPMENT_GUIDE.md) for more commands.

### Deployment Quick Reference
**Production deployment:**
```bash
# Deploy everything
gcloud builds submit --config=cloudbuild.yaml --region=us-west1

# Check status
gcloud run services list --region=us-west1

# View logs
gcloud logging read "resource.type=cloud_run_revision"
```

See [Deployment Guide](deployment/DEPLOYMENT_GUIDE.md) for complete process.

---

## 🆘 Get Help

### For Users
1. Check [FAQ](user-guides/FAQ.md)
2. Ask Mike (AI assistant in app)
3. Read [User Manual](user-guides/USER_MANUAL.md)
4. Email support@podcastplusplus.com

### For Developers
1. Check [Troubleshooting Guide](troubleshooting/TROUBLESHOOTING_GUIDE.md)
2. Search [this documentation index](#-documentation-by-category)
3. Review [API Reference](development/API_REFERENCE.md)
4. Check logs in Cloud Logging

### For DevOps/Admins
1. Check [Monitoring Guide](deployment/MONITORING.md)
2. Review [Deployment Guide](deployment/DEPLOYMENT_GUIDE.md)
3. Check Cloud Run dashboard
4. Escalate to engineering team

---

## 🔄 Keeping Documentation Updated

**When to update docs:**
- ✅ New feature added
- ✅ API endpoint changed
- ✅ Bug fix affects user workflow
- ✅ Deployment process changes
- ✅ New troubleshooting pattern discovered

**How to update:**
1. Edit relevant markdown file
2. Update this index if adding new doc
3. Update version history in file
4. Commit with descriptive message

**Documentation owners:**
- User guides: Product team
- Developer docs: Engineering team
- Deployment docs: DevOps team
- AI Knowledge Base: Product + Engineering

---

## 📊 Documentation Status

| Category | Coverage | Last Updated |
|----------|----------|--------------|
| User Guides | 🟢 Complete | 2025-10-11 |
| Features | 🟢 Complete | 2025-10-11 |
| Architecture | 🟡 Partial | 2025-10-10 |
| Development | 🟡 Partial | 2025-10-09 |
| Deployment | 🟢 Complete | 2025-10-11 |
| Troubleshooting | 🟢 Complete | 2025-10-11 |
| API Reference | 🟡 Partial | 2025-10-08 |

**Legend:**
- 🟢 Complete - Comprehensive, up-to-date
- 🟡 Partial - Exists but needs expansion
- 🔴 Missing - Needs to be created

---

## 📞 Contact

**Documentation Issues:**
- Report via GitHub issues
- Email: docs@podcastplusplus.com

**General Support:**
- Email: support@podcastplusplus.com
- Website: https://podcastplusplus.com

---

**Last Updated:** October 11, 2025  
**Documentation Version:** 2.0
