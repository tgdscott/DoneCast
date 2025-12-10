# Sentry Admin Dashboard - Quick Reference

## What's New?

Admin users can now view production errors directly from the admin dashboard without leaving the app.

## Where to Find It

**Admin Dashboard → System Errors (or Sentry section)**

## What You Can Do

### 1. View Recent Errors
- See all unresolved errors from the last 24 hours
- Shows error type, severity, affected users
- Sorted by most recent first

### 2. Filter by Severity
- **Fatal:** Application crashed
- **Error:** Feature broken, user impacted
- **Warning:** Potential issue, not blocking users
- **Info:** Diagnostic messages
- **Debug:** Development-level details

### 3. Click to See Details
- Full error traceback
- Recent events (last 10 occurrences)
- Affected user count
- First seen / last seen times
- Link to full Sentry dashboard for deeper analysis

### 4. Check Statistics
- Quick summary: Total unresolved, critical count, warnings
- Most recent error timestamp
- API health status

## Common Tasks

### "I see a critical error - what should I do?"
1. Click the error to see details
2. Check recent events to understand impact
3. Check affected user count
4. Click "View in Sentry" to get full context
5. Either:
   - Fix it immediately if quick
   - Create Jira ticket if complex
   - Assign to team member

### "Should we ignore this error?"
- **Yes, ignore if:**
  - User-caused (invalid input, old browser)
  - Third-party service issue (not our fault)
  - Already fixed in dev branch
  
- **No, don't ignore if:**
  - Affects multiple users
  - Breaks a core feature
  - Getting worse over time

### "How do I get more details?"
Click the error → Details view shows:
- Full error message and stack trace
- User information (anonymized)
- Request/response context
- Browser info
- Network requests that failed

Then click "View in Sentry" to access the Sentry dashboard with even more info.

### "Why aren't there any errors showing?"
1. Check that `api_available: true` in stats
2. Check if there are any unresolved issues in Sentry
3. Try expanding time range (days instead of hours)
4. Refresh page (might be caching)

## API Endpoints (For Developers)

### Get Recent Errors
```
GET /api/admin/feedback/sentry/events
  ?limit=20
  &hours_back=24
  &severity=error
```

### Get Statistics
```
GET /api/admin/feedback/sentry/stats
```

### Get Error Details
```
GET /api/admin/feedback/sentry/events/{issue_id}
```

## Configuration

### Prerequisites (Admin Setup)
- Sentry organization must have `SENTRY_ORG_TOKEN` configured
- Token needs `event:read` permission
- Token scope must be organization-level (all projects)

### Testing
```bash
# Check if API is working
curl http://your-app/api/admin/feedback/sentry/stats \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

Should return JSON with error statistics.

## Limitations

- ❌ Cannot resolve/ignore errors from admin dashboard (use Sentry.io for that)
- ❌ Cannot see resolved errors (only unresolved)
- ❌ Cannot search by specific error type (only severity filter)
- ❌ No real-time updates (refresh page to see new errors)
- ✅ Can drill down into any error for full context
- ✅ Affects user count for each error
- ✅ Links to Sentry for advanced analysis

## Future Features

Planned improvements:
- [ ] Real-time error notifications
- [ ] Search by error message/type
- [ ] Trend charts (errors over time)
- [ ] Link to user reports (same issue reported in feedback)
- [ ] Auto-create Jira tickets
- [ ] Slack notifications for critical errors

## Need Help?

**For Admin Users:**
- Dashboard not loading errors? Check backend logs
- API offline? Check `api_available` flag in stats
- Can't click through to details? Refresh page

**For Backend Team:**
- Want to customize error filtering?
- Need different stats displayed?
- Want to add features?

See `SENTRY_ADMIN_INTEGRATION_OCT24.md` for full technical details.

---

**TL;DR:** Go to admin dashboard → System Errors → see production issues in real-time. Click any error for details. Simples!
