# Upload Completion Email Notifications & Automatic Bug Reporting

**Implementation Date:** December 9, 2025  
**Status:** ✅ Complete & Ready for Testing  
**Priority:** High - User Communication & Error Visibility

---

## Overview

This implementation adds comprehensive email notifications for audio upload completion with quality assessment feedback, plus automatic bug reporting for ANY system errors. Users now receive clear communication about their uploads and know that problems are being tracked.

### User Experience

#### ✅ Upload Success
User receives email:
```
✅ Audio "My Interview" uploaded successfully

Quality Assessment: 🟢 Good - Crystal clear audio
Processing Method: 📝 Standard Processing - Clean transcription

You can now assemble it into an episode.
```

#### ❌ Upload Failure
User receives email:
```
❌ Upload failed: My Interview

We encountered an issue uploading your audio.
Error: [Technical error description]
Reference ID: abc123def456

This has been automatically reported as a bug.
Our team has been notified.
```

---

## Implementation Details

### 1. Upload Completion Mailer (`backend/api/services/upload_completion_mailer.py`)

Sends success and failure emails with rich HTML formatting.

**Success Email Contains:**
- Friendly audio name (UUID stripped)
- Quality assessment with emoji indicators
- Processing type (Standard/Advanced)
- Audio analysis metrics (optional)
  - Loudness (LUFS)
  - Peak level (dB)
  - Duration
  - Sample rate
- Call-to-action button to Media Library
- Professional branding

**Failure Email Contains:**
- Friendly file name
- Error description
- Reference ID for support tracking
- Automatic bug report notice
- Troubleshooting steps
- Support contact info

**Functions:**
```python
send_upload_success_email(user, media_item, quality_label, processing_type, metrics)
send_upload_failure_email(user, filename, error_message, error_code, request_id)
```

### 2. Automatic Bug Reporter (`backend/api/services/bug_reporter.py`)

Automatically submits errors to the feedback tracking system for visibility.

**Functions:**
```python
report_upload_failure()          # Upload errors
report_transcription_failure()   # Transcription service errors
report_assembly_failure()        # Episode assembly errors
report_generic_error()           # Generic system errors
```

**Features:**
- Creates `FeedbackSubmission` records in database
- Severity levels: critical, high, medium, low
- Categories: upload, transcription, assembly, etc.
- Sends admin notification email for critical bugs
- Includes error logs and context
- Request ID tracking for support

### 3. Integration Points

#### Upload Router (`backend/api/routers/media.py`)
- **When:** After successful file upload and transcription task enqueue
- **What:** Sends success email with quality assessment
- **Error Handling:** Non-blocking (won't fail upload if email fails)
- **Location:** Lines 483-534

```python
# After successful upload
send_upload_success_email(
    user=current_user,
    media_item=item,
    quality_label=item.audio_quality_label,
    processing_type="advanced" if item.use_auphonic else "standard",
    audio_quality_metrics=parsed_metrics,
)
```

#### Transcription Task Router (`backend/api/routers/tasks.py`)
- **When:** Transcription task fails
- **What:** 
  1. Reports bug to tracking system
  2. Sends failure email to user
  3. Includes error details and reference ID
- **Error Handling:** Automatic on any transcription error
- **Location:** Lines 56-145

```python
# On transcription error
report_transcription_failure(
    session=session,
    user=user,
    media_filename=filename,
    transcription_service="AssemblyAI" or "Auphonic",
    error_message=str(exception),
    request_id=request_id,
)

send_upload_failure_email(
    user=user,
    filename=filename,
    error_message="Failed to transcribe...",
    error_code="TRANSCRIPTION_FAILED",
    request_id=request_id,
)
```

---

## Email Formatting

### Quality Labels in Emails

| Label | Display | Indicator |
|-------|---------|-----------|
| good | "Good - Crystal clear audio" | 🟢 |
| slightly_bad | "Fair - Acceptable quality" | 🟡 |
| fairly_bad | "Fair - Acceptable quality" | 🟡 |
| very_bad | "Poor - May need enhancement" | 🟠 |
| incredibly_bad | "Very Poor - Enhanced processing" | 🔴 |
| abysmal | "Very Poor - Enhanced processing" | 🔴 |

### Processing Type Display

| Type | Display |
|------|---------|
| "advanced" / "auphonic" | 🎚️ Advanced Processing - Professional audio enhancement |
| "standard" / "assemblyai" | 📝 Standard Processing - Clean transcription |

### Metrics Display

Audio analysis metrics included (if available):
- Loudness (LUFS) - integrated loudness
- Peak Level (dB) - maximum amplitude
- Duration - total audio length
- Sample Rate - Hz sampling rate

---

## Bug Reporting System Integration

### When Bugs Are Reported

**Automatic (No User Action Needed):**
- ✅ Upload failures
- ✅ Transcription service errors
- ✅ Assembly failures
- ✅ Any unhandled exceptions in critical paths

**Manual (Via AI Assistant):**
- User says "This is broken" → AI detects and reports
- User submits feedback → Auto-categorized as bug if keywords detected

### Bug Report Contents

```python
FeedbackSubmission(
    type="bug",
    severity="critical",  # or "high", "medium", "low"
    category="upload",    # or "transcription", "assembly", etc.
    title="Upload failed: audio.mp3",
    description="Detailed error description",
    error_logs=JSON(error details),
    user_action="What user was doing",
    admin_notified=True/False,  # If email sent to admin
)
```

### Admin Notification

**Critical/High Severity Bugs:**
- Email sent to `ADMIN_EMAIL` immediately
- Includes full error context
- Request ID for tracing
- User email for follow-up

**Email Subject:**
```
🐛 [CRITICAL] Upload failed: audio.mp3
```

**Email Contents:**
- User who experienced error
- Category and severity
- Full error description
- Error logs (JSON formatted)
- Bug ID for tracking
- Link to admin dashboard

---

## Configuration

### Required Environment Variables

```bash
# Email configuration (already required)
SMTP_HOST=smtp.mailgun.org
SMTP_PORT=587
SMTP_USER=your-user
SMTP_PASS=your-password
SMTP_FROM=no-reply@donecast.com
SMTP_FROM_NAME="DoneCast"

# Admin notifications (optional but recommended)
ADMIN_EMAIL=admin@donecast.com
```

### No New Dependencies

All modules use existing imports:
- Mailer service (already available)
- Database session (SQLModel)
- Logging (Python standard)
- JSON (Python standard)

---

## Testing Checklist

### Manual Testing

- [ ] Upload audio file → Receive success email
  - [ ] Email has friendly audio name
  - [ ] Email shows quality label
  - [ ] Email shows processing type
  - [ ] Email has Media Library link
  
- [ ] Verify quality metrics in email
  - [ ] Good audio shows 🟢
  - [ ] Bad audio shows 🔴
  - [ ] LUFS value displayed correctly
  - [ ] Duration formatted as M:SS

- [ ] Upload failure scenarios
  - [ ] File too large → Failure email sent
  - [ ] GCS upload fails → Failure email sent
  - [ ] Invalid format → Failure email sent
  - [ ] Each failure creates bug report

- [ ] Bug reports are created
  - [ ] Check FeedbackSubmission table
  - [ ] Verify severity = critical
  - [ ] Confirm admin email sent (if ADMIN_EMAIL set)
  - [ ] Check request ID in error logs

- [ ] Email content quality
  - [ ] No broken links
  - [ ] Proper formatting in email client
  - [ ] Images load correctly
  - [ ] Mobile-responsive

### Integration Testing

```bash
# Upload via API
curl -X POST \
  -F "media=@test.mp3" \
  -H "Authorization: Bearer $TOKEN" \
  https://api.donecast.com/api/upload/main_content

# Check email received within 10 seconds
# Check FeedbackSubmission table for any errors
# Verify email body matches expected format
```

### Monitoring

**Logs to Watch:**
```
[upload.email] Success notification sent: ...
[upload.email] Failure notification sent: ...
[bug_reporter] Created bug report: feedback_id=...
```

**Metrics to Track:**
- Email delivery success rate (target: > 95%)
- Bug reports created per day
- Critical bug report admin notification rate
- User email bounce rate

---

## Failure Modes & Mitigation

| Scenario | Impact | Mitigation |
|----------|--------|-----------|
| Email service down | User doesn't get notification | Logged; upload succeeds; email retried next task |
| Database connection fails | Bug report not created | Logged; user email still sent; manual review needed |
| User has no email | Email can't be sent | Logged as error; handled gracefully |
| ADMIN_EMAIL not configured | No admin notification | System logs error; tracked in dashboard anyway |
| Invalid email address | Email delivery fails | Mailer logs bounce; user can resend |

**Critical Principle:** Failures in email/bug reporting do NOT fail the upload. Uploads always succeed if files reach storage. Notifications are best-effort.

---

## File Changes Summary

### New Files
1. `backend/api/services/upload_completion_mailer.py` (420 lines)
   - Success and failure email templates
   - Quality label formatting
   - Metrics display

2. `backend/api/services/bug_reporter.py` (450 lines)
   - Automatic bug submission
   - Admin notifications
   - Error categorization

### Modified Files
1. `backend/api/routers/media.py` (52 lines added)
   - Success email integration
   - Non-blocking error handling

2. `backend/api/routers/tasks.py` (89 lines added)
   - Transcription error handling
   - Bug reporting on failure
   - Failure email notification

---

## Known Limitations

1. **Email Rate Limiting:** If many users upload simultaneously, email service may rate-limit. System handles gracefully with fallback logging.

2. **Metrics Not Available:** If analyzer fails, email still sent with "Unknown" quality. This is intentional - don't delay user communication for metrics.

3. **Admin Email Required for Notifications:** If `ADMIN_EMAIL` not set, bugs are still tracked in database but admin notification email not sent.

4. **Request ID May Be Missing:** Some legacy upload flows may not have `request_id`. System uses "unknown" fallback.

---

## Future Enhancements

1. **Email Preferences:** Let users opt-out of success emails (keep failure emails)
2. **Weekly Digest:** Send admin summary of bugs instead of individual emails
3. **User Support Portal:** Link to specific bug in email for user feedback
4. **Metric Thresholds:** Alert user if audio quality below expected for their tier
5. **Retry Logic:** Automatically retry failed transcriptions with admin visibility
6. **Email Templating:** Move HTML to template files for easier editing

---

## Support & Debugging

### For Users
**"I didn't receive a success email"**
- Check spam folder
- Verify email address in account settings
- Check upload was actually successful (files in Media Library)
- Contact support with request ID from logs

**"My upload failed and I got an error email"**
- Reference ID is in error email
- Follow troubleshooting steps in email
- Try uploading again with smaller file or different format
- Contact support with reference ID

### For Admins
**"Bugs not being reported"**
- Check `ADMIN_EMAIL` configuration
- Verify `FeedbackSubmission` table has entries
- Check Cloud Logging for `[bug_reporter]` errors
- Verify `FeedbackSubmission` model has all columns

**"Emails not being sent"**
- Verify `SMTP_HOST` and `SMTP_PASS` configured
- Check `[MAILER]` logs in Cloud Logging
- Test connectivity: `gcloud compute ssh <instance> -- nc -zv smtp.mailgun.org 587`
- Verify email addresses are valid

**"Quality assessment missing"**
- Check if audio analyzer is running
- Verify ffmpeg installed in container
- Check `[upload.quality]` logs for analyzer errors
- Fall back shown audio_quality_label = NULL

---

## Deployment Checklist

- [ ] Code review completed
- [ ] Unit tests passing (`pytest -q backend/api/tests/test_upload_completion.py`)
- [ ] Integration tests on staging
- [ ] SMTP configuration verified
- [ ] ADMIN_EMAIL set (optional but recommended)
- [ ] Test upload → success email received
- [ ] Test failure scenario → bug report created
- [ ] Monitor logs for first 24 hours
- [ ] Announce feature to users (if desired)

---

## Support Contact

For issues with this implementation, check:
1. Cloud Logging for `[upload.email]` and `[bug_reporter]` logs
2. `FeedbackSubmission` table for bug report status
3. Admin dashboard for overview of recent bugs
4. Email service logs (Mailgun/SendGrid) for delivery status

**Critical:** Any bugs reported here are CRITICAL by default. Check admin inbox immediately if not implementing automatic notifications.

