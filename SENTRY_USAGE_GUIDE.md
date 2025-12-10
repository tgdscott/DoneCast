# Sentry Usage Guide - Quick Reference

## For Developers

### Automatic Error Capture (Already Happens!)

Just write normal exception handling. Sentry will automatically capture:

```python
from fastapi import APIRouter

router = APIRouter()

@router.post("/api/episodes")
async def create_episode(request: Request, data: dict):
    # If ANY exception is raised, Sentry captures it with:
    # - User context (who made the request)
    # - Request context (method, path, request ID)
    # - Full stack trace with local variables
    # - Breadcrumbs (what happened before)
    
    result = do_something_risky(data)  # Exception? Sentry captures it
    return result
```

### Adding Business Context

When processing podcasts/episodes, add context so errors can be filtered:

```python
from api.config.sentry_context import set_business_context, add_breadcrumb

@router.post("/api/episodes/{episode_id}/assemble")
async def assemble_episode(episode_id: str):
    # Tag this error context with business info
    set_business_context(episode_id=episode_id, action="assemble")
    
    # If error occurs, you can filter by episode_id in Sentry
    # Issues → filter tags:episode_id=123
    
    episode = await fetch_episode(episode_id)
    result = await do_assembly(episode)
    return result
```

### Adding Event Breadcrumbs

Breadcrumbs are helpful events leading up to an error. They show what the code was doing:

```python
from api.config.sentry_context import add_breadcrumb

async def process_upload(file: UploadFile):
    add_breadcrumb("Starting file validation", category="upload", level="info")
    
    # Validate file
    if not is_valid(file):
        add_breadcrumb("File validation failed", category="validation", level="warning")
        raise ValueError("Invalid file")
    
    add_breadcrumb("File validated, uploading to GCS", category="upload")
    
    # Upload
    url = await upload_to_gcs(file)
    
    add_breadcrumb("Upload complete", category="upload", data={"gcs_url": url})
    return url
```

### User-Facing Error Messages

When catching an exception, provide helpful error messages:

```python
try:
    result = risky_operation()
except TimeoutError as e:
    # Sentry automatically captures this with full context
    log.exception("Operation timed out")
    raise HTTPException(504, "Server is busy, please try again")
except ValueError as e:
    # Clear message for user
    log.exception("Invalid request data")
    raise HTTPException(400, f"Invalid data: {str(e)}")
```

---

## For Operators/Support Team

### Finding an Error by Request ID

When a user reports "my upload failed", they might provide a request ID from error messages.

**In Sentry:**
1. Go to Issues
2. Click the search box
3. Type: `request_id:"abc-123-def"`
4. See all errors from that request

### Finding All Errors for a User

**In Sentry:**
1. Go to Issues
2. Click the search box
3. Type: `user.email:user@example.com`
4. See all errors this user experienced

### Finding All Errors for a Podcast

**In Sentry:**
1. Go to Issues
2. Click the search box
3. Type: `tags.podcast_id:"123"`
4. See all errors related to this podcast

### Understanding an Error Report

**When you see an error in Sentry:**

1. **User** - Who caused it (avatar, email, name)
2. **Breadcrumbs** - Event timeline (what happened before the error)
3. **Tags** - Business context (podcast_id, episode_id, action)
4. **Stack trace** - Where in the code it failed
5. **Request** - HTTP method, path, status code
6. **Context** - Additional debugging info

**Example interpretation:**

```
Error: "GCS upload failed: 403 Forbidden"
├─ User: john@example.com (user-123)
├─ Request: POST /api/media/upload (request_id: abc-def-ghi)
├─ Tags: action=upload, podcast_id=456
├─ Breadcrumbs:
│  1. POST /api/media/upload (incoming request)
│  2. User authenticated as john@example.com
│  3. File validation passed
│  4. GCS upload started
│  5. GCS permission denied error
└─ Status: 403 Forbidden

Interpretation: John tried to upload a file. File validated fine, but GCS 
returned permission error. Could be: missing service account credentials,
wrong GCS bucket, or permissions issue.
```

### Setting Up Notifications

**In Sentry UI:**

1. Go to Project Settings → Alerts → Create Alert Rule
2. **Recommended:**
   - Alert on: Error events
   - Filter: `level:error AND tags.severity:critical`
   - Actions: Send to Slack #bugs, Send email, (Optional) PagerDuty

3. Save and test

**Will notify on:**
- Critical errors (upload failures, transcription failures, assembly crashes)
- But not on 404s or validation errors

---

## Deployment Checklist

- [ ] SENTRY_DSN configured in Secret Manager
- [ ] Cloud Run backend restarted (env var picked up)
- [ ] Test error captured in Sentry dashboard
- [ ] User context visible in Sentry
- [ ] Request ID visible in Sentry tags
- [ ] Slack alert rule created
- [ ] Email notifications configured
- [ ] Team trained on using Sentry dashboard

---

## Common Issues

### Sentry shows "No error" but user reported a crash

**Check:**
1. Was user in dev environment? (Sentry disabled in dev by default)
2. Error might not be captured (404s are filtered intentionally)
3. Check Cloud Logging for actual error

### Too many 404 errors in Sentry

**Why:** These are filtered out - they shouldn't appear

**Solution:** These are already filtered in `before_send()`. If you're seeing them:
1. Check Sentry filter settings
2. Update before_send filter in logging.py

### User context missing from error

**Cause:** User not authenticated, or context not set

**Check:** Sentry shows "no user" → request was unauthenticated

**Solution:** No problem - some endpoints are public. Anonymous errors are still tracked.

---

## Support Workflow

**When user reports an error:**

1. Get the request ID (from error message or Cloud Logging)
2. Search Sentry: `request_id:"user-id"`
3. View the error details:
   - What failed? (Error message)
   - Why? (Stack trace)
   - What was before? (Breadcrumbs)
   - What context? (Tags)
4. Reproduce locally if needed
5. File bug report with error details
6. Reference the Sentry link in the bug report

---

## FAQ

**Q: Will Sentry capture my production data?**  
A: No. Sentry captures error events only. Even then:
- Passwords and tokens are scrubbed
- Email addresses are masked (if configured)
- Custom PII is not logged

**Q: Will this slow down my app?**  
A: No. Sentry runs in the background:
- Error capture is non-blocking
- Sampling (10% of requests) keeps overhead low
- Only errors trigger notifications

**Q: What if Sentry is down?**  
A: App continues normally. Sentry errors are never blocking.
- If Sentry DSN is invalid, errors are logged locally
- Users still get email notifications (from database)

**Q: How much does Sentry cost?**  
A: Check your Sentry project settings. Pricing based on:
- Events per month (errors captured)
- Sessions tracked
- You get 5k events/month free

**Q: Can I test the integration without deploying?**  
A: Yes - use staging environment, trigger an error, verify it appears in Sentry.
