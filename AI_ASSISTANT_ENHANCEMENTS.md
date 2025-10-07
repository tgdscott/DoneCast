# AI Assistant Enhancements

## Overview
This document covers the enhancements added to the AI Assistant after initial activation, focusing on strict scope enforcement, email notifications, Google Sheets logging, and global error handling.

## 1. Strict Platform-Only Scope

**User Requirement**: "This is an agent ONLY for answering questions related to this site and nothing else."

### Implementation
Updated `_get_system_prompt()` in `backend/api/routers/assistant.py` to include:

```python
CRITICAL RULES - READ CAREFULLY:
1. You ONLY answer questions about Podcast Plus Plus and how to use this platform
2. If asked about anything else (politics, news, other software, general knowledge), politely say:
   "I'm specifically designed to help with Podcast Plus Plus. I can only answer questions about using this platform. How can I help with your podcast?"
3. Do NOT provide general podcast advice unrelated to this platform
4. Do NOT help with other podcast platforms or tools
5. Stay focused on: uploading, editing, publishing, troubleshooting, and using features of THIS platform
```

### Examples
**IN SCOPE (Assistant will help):**
- ✅ "How do I upload audio?"
- ✅ "Why is my episode not publishing?"
- ✅ "What does the Flubber feature do?"
- ✅ "I'm getting an error when..."
- ✅ "How do I edit my podcast description?"

**OUT OF SCOPE (Assistant will politely refuse):**
- ❌ "What's the weather today?"
- ❌ "Help me write Python code"
- ❌ "Who won the game last night?"
- ❌ "Explain quantum physics"
- ❌ "How do I use Audacity?"

## 2. Email Notifications for Critical Bugs

### Implementation
Added `_send_critical_bug_email()` function that automatically emails admin when severity="critical".

**Location**: `backend/api/routers/assistant.py` lines 99-146

**Email Contains:**
- User information (name, email)
- Bug type and severity
- Page URL where error occurred
- Full description and error logs
- User action that triggered the bug
- Timestamp
- Link to admin panel

**Configuration Required:**
```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
ADMIN_EMAIL=admin@podcastplusplus.com
```

**Gmail Setup:**
1. Enable 2-factor authentication
2. Generate App Password: https://myaccount.google.com/apppasswords
3. Use App Password as SMTP_PASSWORD

### Testing
```bash
# Test with curl
curl -X POST https://your-api.com/api/assistant/feedback \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "bug",
    "title": "Test critical bug",
    "description": "This is a test",
    "context": {
      "page": "/dashboard",
      "errors": "TypeError: Cannot read property..."
    }
  }'
```

## 3. Google Sheets Logging

### Implementation
Added `_log_to_google_sheets()` function that logs ALL feedback to a tracking spreadsheet.

**Location**: `backend/api/routers/assistant.py` lines 149-222

**Sheet Columns:**
1. Timestamp
2. Feedback ID (UUID)
3. User Email
4. User Name
5. Type (bug, feature_request, complaint, praise, question)
6. Severity (critical, high, medium, low)
7. Title
8. Description
9. Page URL
10. User Action
11. Error Logs
12. Status (new, acknowledged, investigating, resolved)

**Configuration Required:**
```bash
GOOGLE_SHEETS_ENABLED=true
FEEDBACK_SHEET_ID=your-spreadsheet-id
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

**Google Cloud Setup:**
1. Create service account: https://console.cloud.google.com/iam-admin/serviceaccounts
2. Download JSON key
3. Enable Google Sheets API
4. Share spreadsheet with service account email
5. Grant "Editor" permission

**Create Tracking Sheet:**
```
Sheet Name: Feedback
Headers (Row 1):
Timestamp | ID | Email | Name | Type | Severity | Title | Description | Page | Action | Errors | Status
```

### Testing
1. Submit feedback via assistant
2. Check Google Sheet for new row
3. Verify `google_sheet_row` field in database matches

## 4. Global Error Handler

### Implementation
Added global error listeners in `frontend/src/App.jsx` that catch:
- Uncaught JavaScript errors
- Unhandled promise rejections

**Location**: `frontend/src/App.jsx` lines 115-150

**Captured Information:**
- Error message
- Stack trace
- Filename and line number
- Timestamp
- Error type (uncaught vs unhandled-rejection)

**How It Works:**
1. Global `error` and `unhandledrejection` event listeners
2. Dispatch `ppp:error-occurred` custom event
3. AIAssistant component listens and tracks errors
4. After 3+ errors, proactive help notification appears
5. User can report bug with error context automatically included

**Benefits:**
- No need to manually wrap try/catch everywhere
- Errors automatically available to AI assistant
- Better context for bug reports
- Proactive help when users encounter repeated errors

## 5. Updated System Prompt

### Key Additions
1. **Strict scope enforcement** - Only Podcast Plus Plus questions
2. **Updated platform knowledge** - Added media library, AI features, GCS retention
3. **Clear refusal instructions** - How to decline off-topic questions
4. **Personality guidelines** - Friendly but focused on platform

### Full Context Provided to AI
- User name, email, tier, account age
- Current page and action
- Last 10 messages in conversation
- Onboarding progress (if in guided mode)
- Recent errors and actions

## Configuration Checklist

### Required for Email (Critical Bugs Only)
- [ ] SMTP_HOST
- [ ] SMTP_PORT
- [ ] SMTP_USER (email address)
- [ ] SMTP_PASSWORD (app password)
- [ ] ADMIN_EMAIL (where to send notifications)

### Required for Google Sheets (All Feedback)
- [ ] GOOGLE_SHEETS_ENABLED=true
- [ ] FEEDBACK_SHEET_ID (spreadsheet ID from URL)
- [ ] GOOGLE_APPLICATION_CREDENTIALS (path to service account JSON)
- [ ] Service account has Sheets API enabled
- [ ] Spreadsheet shared with service account email

### Already Configured (Vertex AI)
- [x] AI_PROVIDER=vertex
- [x] VERTEX_PROJECT
- [x] VERTEX_LOCATION
- [x] VERTEX_MODEL
- [x] Application Default Credentials

## Testing Checklist

### Scope Enforcement
- [ ] Ask on-topic question → Get helpful answer
- [ ] Ask off-topic question → Get polite refusal
- [ ] Ask about other podcasting tools → Get redirected to platform
- [ ] Try general knowledge question → Get scope reminder

### Email Notifications
- [ ] Submit critical bug → Admin receives email
- [ ] Email contains all relevant information
- [ ] `admin_notified` flag set in database
- [ ] Non-critical feedback → No email sent

### Google Sheets
- [ ] Submit feedback → Row appears in sheet
- [ ] All columns populated correctly
- [ ] `google_sheet_row` matches actual row number
- [ ] Works for all feedback types (bug, feature, praise, etc.)

### Global Error Handler
- [ ] Trigger JavaScript error → AIAssistant tracks it
- [ ] Trigger 3+ errors → Proactive help appears
- [ ] Submit bug report → Error logs included automatically
- [ ] Unhandled promise rejection → Also captured

## Production Deployment

### Environment Variables
Add to Cloud Run configuration:

```yaml
SMTP_HOST: smtp.gmail.com
SMTP_PORT: "587"
SMTP_USER: notifications@podcastplusplus.com
SMTP_PASSWORD: <app-password>
ADMIN_EMAIL: admin@podcastplusplus.com
GOOGLE_SHEETS_ENABLED: "true"
FEEDBACK_SHEET_ID: <spreadsheet-id>
GOOGLE_APPLICATION_CREDENTIALS: /secrets/service-account.json
```

### Secret Manager (Google Cloud)
1. Store SMTP_PASSWORD as secret
2. Store service account JSON as secret
3. Mount secrets to Cloud Run container

### Deploy
```bash
git add -A
git commit -m "ENHANCEMENT: AI Assistant - strict scope, email, sheets, error handling"
git push origin main
```

### Verify Deployment
1. Check Cloud Run logs for startup messages
2. Test assistant with on-topic question
3. Test assistant with off-topic question
4. Submit test feedback (all types)
5. Verify email received (critical bugs)
6. Verify Google Sheets row created
7. Trigger test error and check tracking

## Monitoring

### Key Metrics
- Email notifications sent (critical bugs)
- Google Sheets rows added (all feedback)
- Errors captured by global handler
- Off-topic question attempts (should see refusals in logs)

### Log Queries
```bash
# Check critical bug emails
gcloud logging read "resource.type=cloud_run_revision AND textPayload:\"Critical bug email sent\""

# Check Google Sheets logs
gcloud logging read "resource.type=cloud_run_revision AND textPayload:\"Feedback logged to Google Sheets\""

# Check global errors captured
gcloud logging read "resource.type=cloud_run_revision AND textPayload:\"ppp:error-occurred\""
```

## Next Steps

### Future Enhancements
1. **Admin Dashboard Panel** - View all feedback in-app
2. **Feedback Status Updates** - Allow marking as resolved
3. **Smart Categorization** - Auto-categorize feedback by feature area
4. **Trend Analysis** - Detect common issues
5. **Priority Scoring** - Auto-prioritize based on user tier + severity

### Analytics
- Track most common questions
- Identify confusing features (high error rates)
- Measure time-to-resolution
- User satisfaction after assistant help

## Files Modified

### Backend
- `backend/api/routers/assistant.py` - Added email, sheets, strict scope

### Frontend
- `frontend/src/App.jsx` - Added global error handler

### Documentation
- `AI_ASSISTANT_ACTIVATION.md` - Initial activation
- `AI_ASSISTANT_ENHANCEMENTS.md` - This file

## Summary

The AI Assistant is now production-ready with:
✅ **Strict platform-only responses** - Won't answer off-topic questions
✅ **Email alerts** - Admin notified of critical bugs immediately
✅ **Google Sheets tracking** - All feedback logged for analysis
✅ **Global error capture** - Automatic error tracking without manual coding
✅ **Enhanced context** - Better understanding of user issues

The assistant will ONLY help users with Podcast Plus Plus platform questions and will politely redirect any off-topic requests back to platform-related help.
