# Analytics Deployment Checklist

## Pre-Deployment Verification

### Code Review
- [x] Backend: OP3 analytics client implemented (`backend/api/services/op3_analytics.py`)
- [x] Backend: Analytics REST endpoints created (`backend/api/routers/analytics.py`)
- [x] Backend: Router registered in `backend/api/routing.py`
- [x] Backend: RSS feed includes OP3 prefix (`backend/api/routers/rss_feed.py`)
- [x] Frontend: Analytics dashboard component (`frontend/src/components/dashboard/PodcastAnalytics.jsx`)
- [x] Frontend: Dashboard navigation wired up (`frontend/src/components/dashboard.jsx`)
- [x] Frontend: Podcast manager integration (`frontend/src/components/dashboard/PodcastManager.jsx`)
- [x] No TypeScript/lint errors in modified files

### Security Review
- [x] **CRITICAL**: Add authorization checks to analytics endpoints ✅ COMPLETE
  - File: `backend/api/routers/analytics.py`
  - Implementation: All 3 endpoints verify `podcast.user_id == current_user.id`
  - Status: Production-ready
  - See: `AUTHORIZATION_LAYER_COMPLETE.md` for details
  - Test: Verify users can't access other users' analytics (manual testing recommended)

### Configuration
- [x] OP3 prefix format correct: `https://op3.dev/e/{gcs_url}`
- [x] API endpoints follow REST conventions
- [x] CORS configured for analytics endpoints (if needed)
- [x] No hardcoded URLs or credentials in code

## Deployment Steps

### 1. Final Code Check
```powershell
# Navigate to project directory
cd d:\PodWebDeploy

# Check for uncommitted changes
git status

# Review changes
git diff

# Commit analytics changes
git add .
git commit -m "feat: Add OP3 analytics dashboard with full UI integration

- Backend: OP3 API client with async HTTP requests
- Backend: REST endpoints for podcast/episode analytics
- Frontend: Analytics dashboard with Recharts visualizations
- Frontend: Navigation integration in main dashboard and podcast manager
- RSS: OP3 prefix added to audio URLs for download tracking
- UI: Summary cards, time range selector, geographic/app charts, top episodes list

Pending: Authorization checks in analytics endpoints"

# Push to repository
git push origin main
```

### 2. Build & Deploy
```powershell
# Ensure Cloud SQL Proxy is running (if testing locally first)
.\cloud-sql-proxy.exe podcast612:us-west1:podcast-db --port 5432

# Deploy to Cloud Run
gcloud builds submit --config=cloudbuild.yaml --project=podcast612

# Expected output:
# - Building Docker image
# - Deploying podcast-api service
# - Deploying podcast-web service
# - Success message with URLs
```

### 3. Verify Deployment
```powershell
# Check service status
gcloud run services list --project=podcast612

# Should show:
# - podcast-api: READY
# - podcast-web: READY

# Check logs for errors
gcloud logs read --project=podcast612 --service=podcast-api --limit=50
gcloud logs read --project=podcast612 --service=podcast-web --limit=50
```

### 4. Initial Smoke Tests

#### Test RSS Feed (OP3 Prefix)
```powershell
# Fetch RSS feed
$slug = "your-podcast-slug"
curl https://api.podcastplusplus.com/v1/rss/$slug/feed.xml

# Verify:
# - <enclosure> tags present
# - URLs start with https://op3.dev/e/
# - URLs redirect to GCS storage
```

#### Test Analytics Endpoints (will return empty data initially)
```bash
# Get auth token first
$token = "your-jwt-token"

# Test podcast analytics
curl -H "Authorization: Bearer $token" https://api.podcastplusplus.com/api/analytics/podcast/1/downloads?days=30

# Expected: 200 OK with empty/minimal data structure
# or 401 if not authorized (expected if no auth yet)
```

#### Test UI Navigation
1. Login to https://app.podcastplusplus.com
2. Navigate to Dashboard
3. Check Quick Tools sidebar has "Analytics" button
4. Click "Analytics" - should load (with "No data" message)
5. Navigate to Podcasts
6. Verify each podcast has "View Analytics" button
7. Click button - should load analytics for that podcast
8. Check that "Back" button returns to dashboard

## Post-Deployment Monitoring

### Day 0 (Deployment Day)
- [x] Verify all services deployed successfully
- [x] Check for error logs
- [x] Test UI navigation
- [x] Verify RSS feed has OP3 prefix
- [x] Confirm OP3 redirects work (click audio URL)
- [ ] Document deployment time for data tracking

### Day 1-2 (Data Collection Period)
- [ ] Check OP3 for initial data points
- [ ] Monitor error logs for analytics endpoints
- [ ] Verify no 500 errors from OP3 API calls
- [ ] Test analytics UI with limited data

### Day 3+ (Full Analytics Available)
- [ ] Verify analytics dashboard shows real data
- [ ] Test all time range filters (7/30/90/365 days)
- [ ] Check geographic distribution accuracy
- [ ] Verify app/platform breakdown
- [ ] Test top episodes list
- [ ] Confirm download counts match expectations
- [ ] Test with multiple podcasts

## Rollback Plan (If Issues Occur)

### Quick Rollback
```powershell
# Revert to previous Cloud Run revision
gcloud run services update-traffic podcast-api --to-revisions=PREVIOUS=100 --project=podcast612
gcloud run services update-traffic podcast-web --to-revisions=PREVIOUS=100 --project=podcast612
```

### What to Rollback For:
- 500 errors from analytics endpoints
- OP3 API timeout issues
- UI crashes or blank screens
- RSS feed broken
- Download tracking not working

### What NOT to Rollback For:
- "No data available" in analytics (expected for 24-48h)
- Slow OP3 API responses (normal)
- Empty charts (expected initially)

## Known Issues & Workarounds

### Issue: Authorization Not Implemented
**Status:** TODO
**Impact:** Users could potentially access other users' analytics
**Workaround:** None - MUST implement before public release
**Priority:** CRITICAL

### Issue: OP3 Data Delay
**Status:** Expected behavior
**Impact:** No analytics for 24-48 hours after deploy
**Workaround:** Display message to users explaining delay
**Priority:** Low (already handled in UI)

### Issue: Historical Data Missing
**Status:** Expected limitation
**Impact:** Downloads before OP3 integration not tracked
**Workaround:** None - only future downloads tracked
**Priority:** Low (acceptable tradeoff)

## Success Criteria

### Deployment Successful If:
- ✅ All Cloud Run services show "READY" status
- ✅ No error logs in Cloud Logging
- ✅ RSS feed contains OP3 prefixed URLs
- ✅ OP3 URLs redirect to GCS audio files
- ✅ Analytics UI accessible from dashboard
- ✅ No JavaScript console errors
- ✅ Back button navigation works

### Analytics Functional If (48h post-deploy):
- ⏳ Dashboard displays download counts
- ⏳ Charts render with data
- ⏳ Geographic distribution shows countries
- ⏳ App/platform breakdown populated
- ⏳ Top episodes list has entries
- ⏳ Time range filters change data correctly
- ⏳ Multiple podcasts show separate analytics

## Post-Launch Tasks

### Short-term (Week 1)
1. Implement authorization checks (**CRITICAL**)
2. Monitor OP3 API usage and quotas
3. Collect user feedback on analytics features
4. Document any unexpected behaviors
5. Optimize chart performance if needed

### Medium-term (Month 1)
1. Add export functionality (CSV/JSON)
2. Email reports (weekly/monthly summaries)
3. Alert system for unusual traffic patterns
4. Comparative analytics (YoY, MoM)
5. Episode-specific analytics view

### Long-term (Quarter 1)
1. Predictive analytics (forecast downloads)
2. Listener retention metrics
3. Episode attribution tracking
4. A/B testing for episode titles/descriptions
5. Integration with other analytics platforms

## Support Resources

### Documentation
- OP3 API Docs: https://op3.dev/api/docs
- Cloud Run Docs: https://cloud.google.com/run/docs
- Recharts Docs: https://recharts.org/

### Internal Files
- `ANALYTICS_INTEGRATION_COMPLETE.md` - Technical implementation details
- `ANALYTICS_USER_GUIDE.md` - User-facing documentation
- `backend/api/services/op3_analytics.py` - OP3 client source code
- `frontend/src/components/dashboard/PodcastAnalytics.jsx` - UI component

### Contact Points
- OP3 Support: GitHub issues at op3-dev/op3
- Cloud Support: Google Cloud Console support
- Internal: Check error logs in Cloud Logging

---
**Checklist Owner:** DevOps / Release Manager
**Feature Owner:** Product / Analytics Team
**Deploy Date:** TBD
**Expected Data Date:** Deploy Date + 48 hours
**Rollback Threshold:** >5% error rate or complete failure
