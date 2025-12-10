# Upload Completion Emails - Quick Implementation Guide

## What Users Get

### ✅ Upload Success
```
Subject: ✅ "My Interview" uploaded successfully

Email Body:
- Friendly audio name
- Quality assessment (Good/Fair/Poor with emoji)
- Processing method (Standard/Advanced)
- Audio metrics (loudness, duration, sample rate)
- Link to Media Library
```

### ❌ Upload Failure  
```
Subject: ❌ Upload failed: My Interview

Email Body:
- Error description
- Reference ID for support (bug report ID)
- Confirmation that bug was automatically reported
- Troubleshooting suggestions
- Support contact info
```

---

## What Gets Tracked

### Bug Reports Created For:
- ✅ Upload failures (GCS, file validation, size limits)
- ✅ Transcription errors (AssemblyAI timeout, service error, etc.)
- ✅ Transcription crashes
- ✅ Assembly failures
- ✅ Any unhandled exception in critical paths

### Bug Report Info Includes:
- User email & ID
- Error type & severity
- Full error message & stack
- Request ID for tracing
- User context (what they were doing)
- Timestamp

### Admin Notifications:
- Email sent immediately for CRITICAL bugs
- Email NOT sent for high/medium/low (but all still tracked in DB)
- Includes full error context in email
- Bug ID for linking and tracking

---

## Code Integration

### 1. Upload Success Email (media.py)
```python
# After successful upload and transcription task enqueue
send_upload_success_email(
    user=current_user,
    media_item=item,
    quality_label=item.audio_quality_label,  # From analyzer
    processing_type="advanced" if item.use_auphonic else "standard",
    audio_quality_metrics=metrics,  # Parsed JSON
)
```

### 2. Upload Failure Email & Bug Report
```python
# In error handler
report_upload_failure(
    session=session,
    user=current_user,
    filename=filename,
    error_message=str(exception),
    error_code="GCS_ERROR",
    request_id=request.headers.get("x-request-id"),
)

send_upload_failure_email(
    user=current_user,
    filename=filename,
    error_message=str(exception),
    error_code="GCS_ERROR",
    request_id=request_id,
)
```

### 3. Transcription Error Handling (tasks.py)
```python
# In _dispatch_transcription error handler
try:
    await loop.run_in_executor(None, transcribe_media_file, ...)
except Exception as exc:
    # Auto-report bug
    report_transcription_failure(
        session=session,
        user=user,
        media_filename=filename,
        transcription_service="AssemblyAI" or "Auphonic",
        error_message=str(exc),
        request_id=request_id,
    )
    
    # Send user notification
    send_upload_failure_email(
        user=user,
        filename=filename,
        error_message="Transcription failed...",
        request_id=request_id,
    )
```

---

## Environment Configuration

### Required (Already Set)
```bash
SMTP_HOST=smtp.mailgun.org
SMTP_PORT=587
SMTP_USER=...
SMTP_PASS=...
SMTP_FROM=no-reply@donecast.com
```

### Optional But Recommended
```bash
ADMIN_EMAIL=admin@donecast.com
# If set: Critical bugs email admin immediately
# If not set: Bugs still tracked in DB, just no email
```

---

## Testing Checklist

- [ ] Upload audio → Success email received within 10 seconds
- [ ] Email has friendly file name (no UUID)
- [ ] Email shows correct quality label (good/fair/poor)
- [ ] Email shows processing type (Standard/Advanced)
- [ ] Email metrics show correct LUFS and duration
- [ ] Email has working link to Media Library
- [ ] Failure scenario → Failure email received
- [ ] Failure email includes reference ID
- [ ] Failure email says "bug reported"
- [ ] Bug created in `feedback_submission` table
- [ ] Admin email sent (if ADMIN_EMAIL set)
- [ ] Admin email has full error context

---

## Monitoring

### Key Logs
```
[upload.email] Success notification sent: ...
[upload.email] Failure notification sent: ...
[bug_reporter] Created bug report: feedback_id=... severity=critical
[bug_reporter] Admin notification sent: feedback_id=...
```

### Metrics
- Email delivery success rate (target > 95%)
- Bug reports created per day (trend analysis)
- Time to admin notification (target < 1 min)

### Dashboard
- Admin can see all bugs in dashboard
- Filter by severity, category, date
- Add notes and assign to team
- Mark resolved when fixed

---

## Troubleshooting

### "Email not received"
1. Check spam folder
2. Verify email address in account
3. Check upload actually succeeded (Media Library)
4. Logs should show `[upload.email]` marker
5. Contact support with request ID if available

### "Bug not being reported"
1. Check `ADMIN_EMAIL` is set in environment
2. Verify `feedback_submission` table exists
3. Check Cloud Logging for `[bug_reporter]` errors
4. Verify error actually occurred (check other logs)

### "Emails not sending at all"
1. Verify SMTP configuration (test connectivity)
2. Check Cloud Logging for `[MAILER]` errors
3. Verify SMTP credentials are correct
4. Check firewall allows outbound SMTP

---

## Files Summary

| File | Lines | Purpose |
|------|-------|---------|
| `upload_completion_mailer.py` | 420 | Email templates & sending |
| `bug_reporter.py` | 450 | Bug tracking & admin notifications |
| `media.py` | +52 | Hook success email into upload flow |
| `tasks.py` | +89 | Hook bug report + failure email into transcription |
| `test_upload_completion_emails.py` | 350 | Comprehensive test suite |

---

## Deployment

1. **Code Review:** Review the 4 files above
2. **Local Testing:** Run `pytest -q backend/api/tests/test_upload_completion_emails.py`
3. **Commit:** Git commit all changes
4. **Deploy:** `gcloud builds submit --config=cloudbuild.yaml --region=us-west1`
5. **Monitor:** Watch logs for first 24 hours

---

## Important Notes

⚠️ **Critical Principles:**
- Failures in email/bug reporting NEVER fail uploads
- Uploads always succeed if files reach storage
- Emails are best-effort; non-critical if fail
- All errors are automatically reported (no exceptions)
- Admin gets notified immediately for critical bugs

✨ **User Experience:**
- Clear communication about what happened
- Reference ID for support tickets
- Reassurance that problems are being tracked
- Helpful suggestions for troubleshooting

🔍 **Operational:**
- All errors logged and tracked
- Admin dashboard for visibility
- Automatic email notifications
- Full error context for debugging

---

## Questions?

Check detailed docs:
- `UPLOAD_COMPLETION_EMAIL_AND_BUG_REPORTING_DEC9.md` - Full implementation details
- `backend/api/tests/test_upload_completion_emails.py` - Usage examples
- Source code comments in new service files

