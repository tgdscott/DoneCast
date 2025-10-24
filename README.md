# Podcast Plus Plus

**A complete, self-hosted podcast creation and distribution platform**

[![Status](https://img.shields.io/badge/status-production-green)]() [![License](https://img.shields.io/badge/license-proprietary-blue)]()

---

## 🎯 What Is This?

Podcast Plus Plus is an AI-powered podcast hosting and production platform that enables creators to produce, edit, and distribute professional podcasts without expensive editors, hosting fees, or complex software. 

The platform combines:
- **Audio Processing** - Automated editing, enhancement, and assembly
- **AI Features** - Transcript generation, content suggestions, automated editing
- **Template System** - Reusable episode structures with intro/outro/music
- **Self-Hosted RSS** - Independent distribution to all podcast platforms
- **Media Management** - Cloud storage with automatic URL management
- **Analytics** - Episode tracking and listener insights

---

## 🏗️ Architecture

```
┌─────────────────────┐
│   React Frontend    │  ← User Interface (Vite + React)
│  (podcast-web)      │
└──────────┬──────────┘
           │
           ↓ HTTPS
┌─────────────────────┐
│   FastAPI Backend   │  ← API & Business Logic
│   (podcast-api)     │
└──────────┬──────────┘
           │
           ├─→ Cloud SQL (PostgreSQL) - Data persistence
           ├─→ Google Cloud Storage - Media files
           ├─→ Cloud Tasks - Async job queue
           ├─→ Assembly AI - Transcription
           ├─→ ElevenLabs - Text-to-speech
           └─→ Google AI (Gemini) - Content suggestions
```

### Technology Stack

**Frontend:**
- React 18 with Vite
- TailwindCSS + shadcn/ui components
- WaveSurfer.js for audio visualization
- React Hook Form for complex forms

**Backend:**
- Python 3.11+ with FastAPI
- SQLAlchemy 2.0 + SQLModel for ORM
- PostgreSQL (Cloud SQL)
- FFmpeg for audio processing
- Pydub for audio manipulation

**Infrastructure:**
- Google Cloud Run (containerized deployment)
- Google Cloud Storage (media hosting)
- Google Cloud Build (CI/CD)
- Google Secret Manager (credentials)
- Cloud Logging & Monitoring

---

## ✨ Key Features

### 🎙️ Episode Creation
- **Template System** - Define reusable episode structures
- **Multi-Segment Audio** - Intro, main content, outro, commercials
- **Background Music** - Automated ducking and mixing
- **Audio Upload** - Direct to cloud storage, up to 500MB
- **Cover Art** - Per-episode and show-level artwork
- **Metadata** - Title, description, tags, season/episode numbers

### 🤖 AI-Powered Features
- **Automatic Transcription** - Assembly AI integration with speaker diarization
- **Content Suggestions** - AI-generated titles, descriptions, and tags
- **Intern Mode** - Detect spoken editing commands ("insert intro here", "cut this out")
- **Flubber Detection** - Mark mistakes while recording by saying "flubber"
- **AI Assistant "Mike"** - Context-aware help system

### 🎵 Audio Processing
- **Automatic Assembly** - Stitch segments with crossfades
- **Music Ducking** - Lower music volume during speech
- **Normalization** - Consistent volume levels
- **Format Conversion** - Support for MP3, WAV, M4A, etc.
- **TTS Integration** - Generate audio from text scripts

### 📡 Distribution
- **Self-Hosted RSS** - iTunes/Spotify-compliant feeds
- **Signed URLs** - Secure 7-day media access
- **Episode Publishing** - Draft → Processing → Published workflow
- **Distribution Tracking** - Apple, Spotify, Google status
- **Embed Players** - Website integration code

### 📊 Analytics & Monitoring
- **OP3 Integration** - Prefix analytics for download tracking
- **Episode Performance** - Views, plays, and trends
- **User Quotas** - Monthly minute limits and usage tracking
- **Health Monitoring** - Cloud Logging and error tracking

### 💳 Billing & Subscriptions
- **Stripe Integration** - Embedded checkout
- **Tiered Plans** - Multiple subscription levels
- **Usage Tracking** - Minutes consumed per billing cycle
- **Overage Protection** - Soft and hard limits

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Google Cloud Project with billing enabled
- PostgreSQL database (local or Cloud SQL)
- Google Cloud Storage bucket

### Local Development Setup

1. **Clone and Setup Environment**
```powershell
cd D:\PodWebDeploy
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. **Configure Environment Variables**
```powershell
# Copy example env file
copy .env.example .env

# Edit .env with your credentials:
# - DATABASE_URL
# - GCS_BUCKET
# - GEMINI_API_KEY
# - ELEVENLABS_API_KEY
# - STRIPE_SECRET_KEY
# etc.
```

3. **Run Database Migrations**
```powershell
# Migrations run automatically on startup
python -m uvicorn api.main:app --reload
```

4. **Start Frontend Development Server**
```powershell
cd frontend
npm install
npm run dev
```

5. **Access Application**
- Frontend: http://localhost:5173
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Production Deployment

See [`docs/deployment/DEPLOYMENT_GUIDE.md`](docs/deployment/DEPLOYMENT_GUIDE.md) for complete deployment instructions.

Quick deploy:
```bash
gcloud builds submit --config=cloudbuild.yaml --region=us-west1
```

---

## 📚 Documentation

### For Users
- **[User Manual](docs/user-guides/USER_MANUAL.md)** - Complete user guide
- **[Quick Start Guide](docs/user-guides/QUICK_START.md)** - Get started in 5 minutes
- **[FAQ](docs/user-guides/FAQ.md)** - Common questions and answers
- **[Feature Guides](docs/features/)** - Detailed feature documentation

### For Developers
- **[Development Guide](docs/development/DEVELOPMENT_GUIDE.md)** - Development setup and conventions
- **[API Reference](docs/development/API_REFERENCE.md)** - Complete API documentation
- **[Architecture Guide](docs/architecture/SYSTEM_ARCHITECTURE.md)** - System design and data flow
- **[Contributing Guide](docs/development/CONTRIBUTING.md)** - How to contribute

### For DevOps
- **[Deployment Guide](docs/deployment/DEPLOYMENT_GUIDE.md)** - Production deployment
- **[Troubleshooting Guide](docs/troubleshooting/TROUBLESHOOTING_GUIDE.md)** - Common issues and solutions
- **[Monitoring Guide](docs/deployment/MONITORING.md)** - Logs, metrics, and alerts

### Index
📖 **[Full Documentation Index](docs/DOCS_INDEX.md)** - Browse all documentation

---

## 🧪 Testing

```powershell
# Run unit tests
pytest -q

# Run integration tests
pytest -q -m integration

# Run with coverage
pytest --cov=backend/api --cov-report=html

# Run specific test file
pytest tests/test_episodes.py -v
```

See [`tests/README.md`](tests/README.md) for detailed testing information.

---

## 📁 Project Structure

```
PodWebDeploy/
├── backend/
│   ├── api/                    # FastAPI application
│   │   ├── routers/            # API endpoints
│   │   ├── models/             # Database models
│   │   ├── services/           # Business logic
│   │   ├── workers/            # Background tasks
│   │   └── infrastructure/     # GCS, Cloud Tasks, etc.
│   └── tests/                  # Backend tests
├── frontend/
│   ├── src/
│   │   ├── components/         # React components
│   │   ├── pages/              # Page components
│   │   ├── lib/                # Utilities
│   │   └── hooks/              # Custom React hooks
│   └── public/                 # Static assets
├── docs/                       # Documentation
│   ├── user-guides/            # End-user documentation
│   ├── development/            # Developer guides
│   ├── deployment/             # DevOps documentation
│   ├── architecture/           # System design docs
│   ├── features/               # Feature specifications
│   └── troubleshooting/        # Problem resolution
├── scripts/                    # Utility scripts
├── cloudbuild.yaml             # Cloud Build config
├── Dockerfile.cloudrun         # Production container
└── docker-compose.yaml         # Local development
```

---

## 🔑 Key Concepts

### Templates vs Episodes
- **Template** = Reusable structure (like a recipe)
  - Defines segment types (intro, content, outro)
  - Music rules and timing
  - AI generation settings
- **Episode** = Single instance using a template (like a meal)
  - Fills in actual audio files and content
  - Inherits structure from template
  - Can override template settings

### Episode Assembly Pipeline
1. **Upload** - User uploads main content audio
2. **Transcribe** - Assembly AI generates transcript
3. **Process** - Apply Intern/Flubber edits
4. **Assemble** - Stitch segments with music
5. **Finalize** - Upload to GCS with metadata
6. **Publish** - Update RSS feed, notify platforms

### Media Categories
- `main_content` - Primary episode audio
- `intro` - Episode introductions
- `outro` - Episode endings  
- `background_music` - Music tracks for mixing
- `sound_effects` - SFX and jingles
- `ads` - Commercial/sponsorship audio

---

## 🤝 Support & Contact

### AI Assistant "Mike"
The platform includes an integrated AI assistant accessible from any page. Mike can:
- Answer questions about features
- Guide you through workflows
- Troubleshoot issues
- Highlight UI elements for navigation

### Documentation
For technical issues, consult:
1. **[Troubleshooting Guide](docs/troubleshooting/TROUBLESHOOTING_GUIDE.md)**
2. **[FAQ](docs/user-guides/FAQ.md)**
3. **[AI Knowledge Base](docs/AI_KNOWLEDGE_BASE.md)** (for Mike's context)

### Admin Panel
Administrators have access to advanced tools:
- User management
- Podcast oversight
- Database explorer
- Feature toggles
- Analytics dashboard

---

## 📜 License

Copyright © 2025 Podcast Plus Plus. All rights reserved.

This is proprietary software. Unauthorized copying, distribution, or use is strictly prohibited.

---

## 🗺️ Roadmap

### ✅ Completed (Current Version)
- Self-hosted RSS feed generation
- OP3 analytics integration
- Stripe billing and subscriptions
- AI assistant integration
- Template system
- Episode assembly pipeline
- User authentication and authorization

### 🚧 In Progress
- Advanced analytics dashboard
- Automatic episode scheduling
- Mobile-responsive UI improvements
- Performance optimization

### 📋 Planned Features
- Third-party platform auto-submission (Apple, Spotify APIs)
- Podcast website builder
- Advanced audio editing in browser
- Mobile apps (iOS/Android)
- Team collaboration features
- White-label options

See **[Full Roadmap](docs/FULL_PODCAST_HOST_ROADMAP.md)** for detailed feature status.

---

## 📊 Status

- **Production**: ✅ Live at https://app.podcastplusplus.com
- **API Health**: ✅ Monitored 24/7
- **Database**: ✅ Cloud SQL with automatic backups
- **Storage**: ✅ GCS with 99.95% availability
- **Uptime**: 99.9% (last 30 days)

Last Updated: October 11, 2025
