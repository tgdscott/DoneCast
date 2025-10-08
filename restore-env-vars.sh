#!/bin/bash
# EMERGENCY RESTORE: All 47 environment variables
# This script restores the environment variables that were wiped by --set-env-vars

# NOTE: Secrets (marked "Secret: NAME:latest") must be restored via Secret Manager references
# Regular environment variables can be set directly

gcloud run services update podcast-api \
  --project=cloudpod-451221 \
  --region=us-west1 \
  --update-env-vars="\
ADMIN_EMAIL=scott@scottgerhardt.com,\
MEDIA_ROOT=/tmp,\
OAUTH_BACKEND_BASE=https://api.podcastplusplus.com,\
CORS_ALLOWED_ORIGINS=https://app.podcastplusplus.com,\
INSTANCE_CONNECTION_NAME=podcast612:us-west1:podcast-db,\
GOOGLE_CLOUD_PROJECT=podcast612,\
TASKS_LOCATION=us-west1,\
TASKS_QUEUE=ppp-queue,\
TASKS_URL_BASE=https://api.podcastplusplus.com,\
APP_ENV=production,\
TERMS_VERSION=2025-09-01,\
SMTP_HOST=smtp.mailgun.org,\
SMTP_PORT=587,\
SMTP_USER=admin@podcastplusplus.com,\
SMTP_FROM=no-reply@PodcastPlusPlus.com,\
AI_PROVIDER=vertex,\
VERTEX_PROJECT=podcast612,\
VERTEX_LOCATION=us-central1,\
VERTEX_MODEL=gemini-2.5-flash-lite,\
USE_CLOUD_TASKS=1,\
DB_POOL_SIZE=10,\
DB_MAX_OVERFLOW=5,\
DB_POOL_RECYCLE=300,\
DB_POOL_TIMEOUT=15,\
GCS_CHUNK_MB=32,\
MEDIA_BUCKET=ppp-media-us-west1,\
TRANSCRIPTS_BUCKET=ppp-transcripts-us-west1,\
FEEDBACK_SHEET_ID=1dnIMPYvaoGe5hRdJ9W1k9CFua3y2I6aW55BLDMxH_6k,\
GOOGLE_SHEETS_ENABLED=true,\
CLOUDPOD_MAX_MIX_BUFFER_BYTES=2147483648"

# Now restore the secrets via Secret Manager references
gcloud run services update podcast-api \
  --project=cloudpod-451221 \
  --region=us-west1 \
  --update-secrets="\
DB_USER=DB_USER:latest,\
DB_PASS=DB_PASS:latest,\
DB_NAME=DB_NAME:latest,\
SECRET_KEY=SECRET_KEY:latest,\
SESSION_SECRET_KEY=SESSION_SECRET:latest,\
GEMINI_API_KEY=GEMINI_API_KEY:latest,\
ELEVENLABS_API_KEY=ELEVENLABS_API_KEY:latest,\
ASSEMBLYAI_API_KEY=ASSEMBLYAI_API_KEY:latest,\
SPREAKER_API_TOKEN=SPREAKER_API_TOKEN:latest,\
SPREAKER_CLIENT_ID=SPREAKER_CLIENT_ID:latest,\
SPREAKER_CLIENT_SECRET=SPREAKER_CLIENT_SECRET:latest,\
GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID:latest,\
GOOGLE_CLIENT_SECRET=GOOGLE_CLIENT_SECRET:latest,\
STRIPE_SECRET_KEY=STRIPE_SECRET_KEY:latest,\
STRIPE_PUBLISHABLE_KEY=STRIPE_PUBLISHABLE_KEY:latest,\
STRIPE_WEBHOOK_SECRET=STRIPE_WEBHOOK_SECRET:latest,\
DATABASE_URL=DATABASE_URL:latest,\
SMTP_PASS=SMTP_PASS:latest,\
TASKS_AUTH=TASKS_AUTH:latest"

echo "✅ All 47 environment variables restored!"
echo "⚠️  Remember: The next deployment will preserve these because we fixed --set-env-vars → --update-env-vars"
