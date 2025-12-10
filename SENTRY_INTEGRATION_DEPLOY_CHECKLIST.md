# Sentry Integration - Deploy Checklist

## Pre-Deployment (5 minutes)

- [ ] Pull latest code: `git pull origin main`
- [ ] Verify SENTRY_DSN exists: `gcloud secrets versions access latest --secret=SENTRY_DSN --project=podcast612`
- [ ] Review changes:
  - `backend/api/config/logging.py` (enhanced Sentry init)
  - `backend/api/config/sentry_context.py` (NEW)
  - `backend/api/middleware/sentry.py` (NEW)
  - `backend/api/config/middleware.py` (register new middleware)
  - `backend/api/services/bug_reporter.py` (integration)

## Deploy to Staging (10 minutes)

```bash
# Run in dedicated terminal (user handles separately)
# Check with user first:
# "Ready to deploy? I have Sentry integration changes ready."

# User confirms, then:
gcloud builds submit --config=cloudbuild.yaml --region=us-west1 --project=podcast612
```

## Verify Staging (15 minutes)

**1. Check startup logs:**

```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=podcast612-api AND \
  textPayload=~'Sentry'" \
  --limit=5 --project=podcast612 --format=text
```

Should show:
```
[startup] Sentry initialized for env=staging (traces_sample_rate=0.1, breadcrumbs=100)
```

**2. Test upload success:**
- Go to staging frontend: `https://staging.donecast.com`
- Login
- Upload a valid audio file
- Verify it processes without error
- Check Sentry dashboard - NO error should appear (success, not an error)

**3. Test upload failure:**
- Try uploading invalid file (empty file, wrong format)
- Should get error message
- Wait 5 seconds
- Check Sentry Issues dashboard
- Verify error appears with:
  - [ ] User context (email, ID)
  - [ ] Request context (method, path, request-id)
  - [ ] Breadcrumbs (event trail)
  - [ ] Business tags (if applicable)

**4. Test filtering:**
- Try accessing non-existent endpoint: `/api/doesnt-exist`
- Should get 404
- Check Sentry - NO 404 should appear (filtered intentionally)

**5. Test alert:**
- If Slack alert rule configured, trigger error
- Verify Slack notification appears in #bugs channel
- Verify email notification sent (if configured)

## Deploy to Production (5 minutes)

```bash
# After staging verification passes

# User confirms:
# "Sentry working in staging. Ready for production?"

# User then deploys to production
gcloud builds submit --config=cloudbuild.yaml --region=us-west1 --project=podcast612
```

## Monitor Production (30 minutes)

**First 5 minutes:**
- Check Cloud Run logs for "Sentry initialized" message
- Should appear within 1-2 minutes of deployment

**First 30 minutes:**
- Watch Sentry Issues dashboard
- Real errors should start appearing
- Verify user context on errors
- Verify request_id tags
- No error spam (404s filtered)

**Check these dashboards:**
1. Cloud Run → Cloud Run Logs
2. Sentry → Issues
3. Cloud Monitoring → Error Rate
4. Slack (if alerts configured)

## Rollback Instructions (If Needed)

```bash
# If something breaks, rollback is simple:
# 1. Previous version still in Cloud Run
# 2. No dependencies changed
# 3. Sentry errors are non-blocking

# Either:
# a) Deploy previous version of code
# b) Or just unset SENTRY_DSN env var (disables Sentry)

gcloud run services update podcast612-api \
  --set-env-vars=SENTRY_DSN="" \
  --region=us-west1 \
  --project=podcast612
```

## Post-Deployment

- [ ] Monitor Sentry dashboard for 24 hours
- [ ] Check error patterns daily for first week
- [ ] Set up Slack/email alerts in Sentry UI
- [ ] Document Sentry setup in team wiki
- [ ] Train team on using Sentry dashboard

## Success Criteria

✅ Deployment is successful if:

1. No "Sentry init failed" errors in logs
2. Real errors appear in Sentry within 5 seconds
3. Each error has user context
4. Each error has request_id tag
5. Breadcrumbs show event sequence
6. 404 errors NOT appearing (filtered)
7. No performance degradation
8. Alerts working (if configured)

## Troubleshooting

### Sentry shows "disabled (missing DSN or dev/test env)"

✅ Expected in staging/dev (env is not "production")

To test in staging:
- Set env var: `SENTRY_ENABLE_STAGING=true` (if you implement it)
- Or wait for traffic to staging (more errors to test)

### Errors not appearing in Sentry

1. Check SENTRY_DSN is valid
2. Check Cloud Logging for "Sentry init" messages
3. Trigger a real error (upload invalid file)
4. Check Sentry Issues - should appear within 5s
5. Check event queue (Sentry might be rate-limiting)

### Too much spam in Sentry

- Update `before_send()` filter in `logging.py`
- Add more error patterns to ignore
- Check if legitimate errors or false positives

### Alert not working

1. Check Sentry alert rule exists
2. Test rule: Issues → Select issue → Alert → Test Alert
3. Verify Slack/email integration configured
4. Check permissions (Slack bot in channel, etc.)

---

## Files Changed Summary

```
Modified:
  backend/api/config/logging.py          (+51 lines, enhanced Sentry)
  backend/api/config/middleware.py       (+2 lines, register middleware)
  backend/api/services/bug_reporter.py   (+45 lines, Sentry integration)

Created:
  backend/api/config/sentry_context.py   (175 lines, helper functions)
  backend/api/middleware/sentry.py       (108 lines, context middleware)

Documented:
  SENTRY_INTEGRATION_SUMMARY.md          (300+ lines)
  SENTRY_INTEGRATION_COMPLETE_DEC9.md    (500+ lines)
  SENTRY_USAGE_GUIDE.md                  (400+ lines)
  SENTRY_INTEGRATION_DEPLOY_CHECKLIST.md (This file)
```

## Questions?

Refer to:
- **Quick overview:** `SENTRY_INTEGRATION_SUMMARY.md`
- **Full details:** `SENTRY_INTEGRATION_COMPLETE_DEC9.md`
- **How to use:** `SENTRY_USAGE_GUIDE.md`
- **Technical details:** Code comments in `sentry_context.py` and `middleware/sentry.py`

---

## Timeline

- **Code complete:** ✅ December 9, 2025
- **Ready for staging:** ✅ Now
- **Ready for production:** After staging verified
- **Monitoring:** 24 hours post-production

---

**This is a low-risk, high-impact change. All errors now properly contextualized and tracked.**
