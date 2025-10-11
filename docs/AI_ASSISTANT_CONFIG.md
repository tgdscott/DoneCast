# AI Assistant - Configuration Guide

## What's Already Working

✅ **Assistant UI** - Visible in dashboard (bottom-right)  
✅ **Strict Platform Scope** - Only answers Podcast Plus Plus questions  
✅ **Database Logging** - All feedback saved to database  
✅ **Error Tracking** - Global error handler captures issues  

## What Needs Configuration

### 1. Email Notifications (Optional but Recommended)

**Current Status**: You already have SMTP configured!
- ✅ `SMTP_HOST=smtp.mailgun.org`
- ✅ `SMTP_PORT=587`
- ✅ `SMTP_USER=admin@podcastplusplus.com`
- ✅ `SMTP_PASS=<your-mailgun-password>`

**What to Add**:
Just set where to send critical bug alerts:
```bash
ADMIN_EMAIL=scott@scottgerhardt.com  # or wherever you want alerts
```

That's it! When users report critical bugs, you'll get an email.

### 2. Google Sheets Logging (Optional)

**Purpose**: Log all feedback to a spreadsheet for easy tracking/analysis

**If You Want This**:

#### Option A: Use Application Default Credentials (Easiest for Cloud Run)
```bash
GOOGLE_SHEETS_ENABLED=true
FEEDBACK_SHEET_ID=<your-spreadsheet-id>
# No GOOGLE_APPLICATION_CREDENTIALS needed - uses Cloud Run service account
```

Then:
1. Create a Google Sheet
2. Add headers in row 1: `Timestamp | ID | Email | Name | Type | Severity | Title | Description | Page | Action | Errors | Status`
3. Share with your Cloud Run service account email (find in IAM console)
4. Enable Sheets API: https://console.cloud.google.com/apis/library/sheets.googleapis.com

#### Option B: Skip It For Now
Just leave `GOOGLE_SHEETS_ENABLED=false` (or don't set it). All feedback still saves to database.

## Current Issue: Assistant Connection Error

The error "Sorry, I'm having trouble connecting" means the `/api/assistant/chat` endpoint is failing.

**Most Likely Causes**:

1. **Gemini/Vertex AI not configured locally**
   - Check: Do you have `VERTEX_PROJECT`, `VERTEX_LOCATION`, `VERTEX_MODEL` set?
   - Check: Is Application Default Credentials configured? Run: `gcloud auth application-default login`

2. **API endpoint not responding**
   - Check backend logs for errors
   - Test the endpoint directly:
   ```bash
   curl -X POST http://localhost:8000/api/assistant/chat \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"message":"Hello","session_id":"test123"}'
   ```

3. **Frontend can't reach backend**
   - Check browser console (F12) for error details
   - Verify API URL is correct

## Quick Test Commands

### Test Email (if configured)
```bash
curl -X POST http://localhost:8000/api/assistant/feedback \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "bug",
    "title": "Test critical bug",
    "description": "Testing email notifications",
    "context": {"page": "/dashboard"}
  }'
```

Should send email to ADMIN_EMAIL.

### Test Assistant Chat
```bash
curl -X POST http://localhost:8000/api/assistant/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How do I upload audio?",
    "session_id": "test-session-123",
    "context": {"page": "/dashboard"}
  }'
```

Should return helpful response about uploading.

### Check Backend Logs
```bash
# Look for errors
grep -i "error\|exception\|failed" logs.txt

# Look for Gemini issues
grep -i "gemini\|vertex" logs.txt

# Look for assistant requests
grep -i "assistant" logs.txt
```

## Environment Variables Summary

### Already Set (from your screenshot)
```bash
SMTP_HOST=smtp.mailgun.org ✅
SMTP_PORT=587 ✅
SMTP_USER=admin@podcastplusplus.com ✅
SMTP_PASS=<secret> ✅
VERTEX_PROJECT=podcast612 ✅
VERTEX_LOCATION=us-central1 ✅
VERTEX_MODEL=gemini-2.5-flash-lite ✅
AI_PROVIDER=vertex ✅
```

### Need to Add
```bash
ADMIN_EMAIL=scott@scottgerhardt.com  # Where to send critical bug emails
```

### Optional (for Google Sheets)
```bash
GOOGLE_SHEETS_ENABLED=true
FEEDBACK_SHEET_ID=<spreadsheet-id>
```

## Troubleshooting Steps

1. **Check if backend is running**: `netstat -ano | Select-String ":8000"`
2. **Check backend logs**: Look for startup messages about Gemini
3. **Test Gemini directly**: Try generating content with your current setup
4. **Check browser console**: Open DevTools (F12) and look at Network tab when sending message
5. **Verify token**: Make sure you're logged in and token is valid

## What to Do Next

1. ✅ **Add `ADMIN_EMAIL`** to environment variables (use existing SMTP settings)
2. 🔍 **Check why assistant connection fails**:
   - Look at backend logs when you click "Yes, show me around!"
   - Check browser console (F12 → Console tab)
   - Share error details so I can help fix
3. ⏳ **Optionally set up Google Sheets** later (not required for assistant to work)

The assistant should work once Gemini/Vertex AI is properly configured. Everything else (email, sheets) is optional enhancement.
