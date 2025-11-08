# Missing Environment Variables Analysis

## Summary
Your environment variables dropped from **65 to 33** - we lost **32 variables**. Here's the breakdown:

## 🔴 CRITICAL - Must Add Back Immediately

These are **required** for core functionality:

1. **TASKS_AUTH** (Secret) - ⚠️ **ALREADY MISSING** - Critical for Cloud Tasks authentication
2. **MEDIA_BUCKET** - Used for media storage operations
3. **TRANSCRIPTS_BUCKET** - Used for transcript storage
4. **SMTP_HOST, SMTP_PORT, SMTP_USER** - Email functionality (SMTP_PASS is secret)
5. **ADMIN_EMAIL** - Used for admin user identification and notifications
6. **OAUTH_BACKEND_BASE** - Used for OAuth callbacks
7. **MEDIA_ROOT** - Used for local media storage paths
8. **DB_CONNECT_TIMEOUT, DB_STATEMENT_TIMEOUT_MS** - Database connection timeouts
9. **DISABLE_STARTUP_MIGRATIONS** - Controls whether migrations run on startup

## 🟡 IMPORTANT - Should Add Back for Full Functionality

These are needed for specific features:

1. **GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET** (Secrets) - Google OAuth authentication
2. **STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET** (Secrets) - Billing/payments
3. **SPREAKER_API_TOKEN, SPREAKER_CLIENT_ID, SPREAKER_CLIENT_SECRET** (Secrets) - Spreaker integration
4. **GEMINI_MODEL** - AI model selection (falls back to VERTEX_MODEL if not set)
5. **FEEDBACK_SHEET_ID, GOOGLE_SHEETS_ENABLED** - Feedback logging to Google Sheets
6. **GCS_CHUNK_MB** - GCS upload chunk size (though you're using R2, might still be used)

## 🟢 OBSOLETE - Can Skip

These are no longer needed:

1. **USE_CLOUD_TASKS** - Code now uses `should_use_cloud_tasks()` function instead
2. **WORKER_BASE_URL** - Duplicate of `WORKER_URL_BASE` (already have WORKER_URL_BASE)
3. **TERMS_VERSION** - Not critical for functionality
4. **FORCE_RESTART** - Just for forcing restarts, not needed
5. **SESSION_SECRET_KEY** - Already have `SESSION_SECRET` (they're aliased in code)

## Missing Secrets

The following secrets are also missing from your current deployment:

1. **TASKS_AUTH** - ⚠️ **CRITICAL** - Already added to cloudbuild.yaml fix
2. **SMTP_PASS** - Email password
3. **GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET** - Google OAuth
4. **STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET** - Billing
5. **SPREAKER_API_TOKEN, SPREAKER_CLIENT_ID, SPREAKER_CLIENT_SECRET** - Spreaker

## Impact Assessment

### Immediate Impact (Breaking):
- ❌ **TASKS_AUTH missing** - Cloud Tasks authentication will fail (this is your current issue!)
- ❌ **MEDIA_BUCKET, TRANSCRIPTS_BUCKET missing** - Media operations may fail
- ❌ **SMTP settings missing** - Email functionality broken
- ❌ **ADMIN_EMAIL missing** - Admin user detection broken

### Functional Impact (Features Broken):
- ❌ **Google OAuth** - Users can't log in with Google
- ❌ **Stripe Billing** - Payment processing broken
- ❌ **Spreaker Integration** - Publishing to Spreaker broken
- ❌ **Feedback Logging** - Feedback not logged to Google Sheets

### Performance Impact:
- ⚠️ **DB_CONNECT_TIMEOUT, DB_STATEMENT_TIMEOUT_MS** - Using defaults (might be too short/long)
- ⚠️ **GCS_CHUNK_MB** - Using defaults (might affect upload performance)
- ⚠️ **DISABLE_STARTUP_MIGRATIONS** - Migrations run on every startup (slower)

## Action Plan

1. **Immediate**: Add back CRITICAL variables to cloudbuild.yaml
2. **Important**: Add back IMPORTANT variables for full functionality
3. **Verify**: Check that all secrets exist in Secret Manager
4. **Test**: Verify functionality after redeployment

