# Cloud Run Deployment Checklist

1. **Provision Postgres**: create or identify the Cloud SQL (PostgreSQL) instance and database. Collect the connection string in SQLAlchemy form `postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME`. If you use a socket/Cloud SQL proxy, adapt the URL accordingly.
2. **Store secrets**: add the connection string to Cloud Build / GitHub Actions secrets (`_DATABASE_URL` substitution or `CLOUDRUN_DATABASE_URL` GitHub secret). Keep `SESSION_SECRET`, Stripe keys, etc. in Secret Manager or GH secrets as you prefer.
3. **Create storage buckets**: provision
   * a private media bucket (example: `gsutil mb -l us-west1 gs://ppp-media-us-west1`) for audio uploads and artwork. Grant the Cloud Run service account `roles/storage.objectAdmin` (or narrower `roles/storage.objectCreator` plus `roles/storage.objectViewer`) for that bucket and record the bucket name for `MEDIA_BUCKET`.
   * a public transcripts bucket (example: `gsutil mb -l us-west1 gs://ppp-transcripts-us-west1`) that will hold the JSON transcripts. Grant anonymous read access so episode transcript links can be shared: `gsutil iam ch allUsers:objectViewer gs://ppp-transcripts-us-west1`. Set `TRANSCRIPTS_BUCKET` to this bucket name.
4. **Deploy with env vars**:
   ```bash
   gcloud run deploy podcast-web \
     --image=<region>-docker.pkg.dev/<project>/cloud-run/podcast-web:latest \
     --region=us-west1 \
     --platform=managed \
     --allow-unauthenticated \
     --set-env-vars=APP_ENV=production,ADMIN_EMAIL=scott@scottgerhardt.com,MEDIA_ROOT=/tmp \
     --set-secrets=DATABASE_URL=<secret-name>:latest

   gcloud run deploy podcast-api \
     --image=<region>-docker.pkg.dev/<project>/cloud-run/podcast-api:latest \
     --region=us-west1 \
     --platform=managed \
     --allow-unauthenticated \
  --set-env-vars=APP_ENV=production,ADMIN_EMAIL=scott@scottgerhardt.com,MEDIA_ROOT=/tmp,MEDIA_BUCKET=<your-media-bucket>,TRANSCRIPTS_BUCKET=<your-transcripts-bucket>,OAUTH_BACKEND_BASE=https://api.podcastplusplus.com,\
       CORS_ALLOWED_ORIGINS=https://app.podcastplusplus.com\,https://podcastplusplus.com\,https://www.podcastplusplus.com \
     --set-secrets=DATABASE_URL=<secret-name>:latest,SECRET_KEY=<secret-name>:latest,SESSION_SECRET=<secret-name>:latest
   ```
   Replace `<secret-name>` with the Secret Manager entries that hold your configuration secrets and `<your-media-bucket>` with the bucket from step 3. If you prefer direct values, swap `--set-secrets` for `--set-env-vars=...`. If you serve the SPA on additional domains (apex or www), add them to `CORS_ALLOWED_ORIGINS` as well (separate with semicolons like `https://example.com;https://www.example.com`).
   Remember to include your SMTP configuration (for example `SMTP_HOST=smtp.sendgrid.net,SMTP_PORT=587,SMTP_USER=apikey`) either as env vars or secrets so transactional email works outside of local development.
5. **Verify runtime**: after deploy, hit `/api/users/me`, run `scripts/login_and_me.py`, try an RSS import, upload a media file, and confirm the Postgres-backed instance handles reads/writes while media uploads land in Cloud Storage.
6. **Validate mailer connectivity**: check the Cloud Run logs for `SMTP host '...' resolved` / `SMTP connectivity probe succeeded` messages emitted on startup. If you see DNS failures or firewall warnings, run `nslookup smtp.sendgrid.net` in the deploy pipeline or open the Cloud Run troubleshooting shell to make sure outbound SMTP is permitted.
7. **First-time DB bootstrap**: the API auto-creates tables on startup. If you need to backfill admin data, run `scripts/create_test_user.py` against the new API or add manual entries through psql.

Keep `MEDIA_ROOT=/tmp` so FastAPI writes transient scratch files into Cloud Run's writable space. With a GCS bucket in place, long-term assets (intros/outros/music) persist under `gs://<your-media-bucket>/` as expected.
