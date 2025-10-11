# PRODUCTION ISSUES - October 11, 2025
## FOCUS: PRODUCTION ONLY - NO LOCAL CHANGES

**Current Production Status:**
- Latest Revision: `podcast-api-00522-7sg` (deployed 1 hour ago from build cf2c110d)
- Previous Revision: `podcast-api-00521-4tm` (tagged as production1, getting 100% traffic?)
- **PROBLEM**: Traffic routing unclear - need to verify which revision actually serves requests

---

## ISSUE #1: Cannot Play Any of 6 Scheduled Episodes ❌
**Error**: `api.podcastplusplus.com/static/final/test110803---e200---the-long-walk---what-would-you-do.mp3` returns **500**

**Production Logs Show:**
```
[2025-10-11 06:10:56,940] WARNING api.exceptions: HTTPException GET /static/final/test110608---e199---twinless---what-would-you-do.mp3 -> 404: Not Found
[2025-10-11 04:30:09,993] WARNING api.exceptions: HTTPException GET /static/final/test110346---e195----e195---the-roses---what-would-you-do.mp3 -> 404: Not Found
```

**Root Cause**: Files returning 404/500 - either:
1. Files not in GCS bucket
2. Signed URL generation failing
3. Static file serving broken
4. Wrong file paths in database

**Investigation Needed:**
- Check if files exist in GCS: `gs://ppp-media-us-west1/.../final/`
- Check Episode.final_audio_path values in production database
- Check GCS signed URL generation code
- Verify IAM permissions for GCS access

---

## ISSUE #2: Episode Not Deleted After Creation ❌
**Symptom**: Used audio file still appears in Step 2 picker after being used in an episode

**Code Status**: Fix was committed in latest deployment:
- `backend/api/routers/media.py` - Changed filter to exclude ALL episodes using file

**Possible Causes:**
1. **Fix not deployed yet** - Latest revision 00522 might not be serving traffic
2. **Database state** - Episode still has working_audio_name set
3. **Frontend cache** - Old data cached in browser

**Investigation Needed:**
- Verify revision 00522 is actually serving traffic (not just deployed)
- Check production database for Episode.working_audio_name values
- Test with browser cache cleared

---

## ISSUE #3: Intern Does Not Work ❌
**Error**: `POST https://api.podcastplusplus.com/api/intern/prepare-by-file` returns **404**

**Production Logs Show:**
```
[2025-10-11 08:08:19,618] WARNING api.exceptions: HTTPException POST /api/intern/prepare-by-file -> 404: uploaded file not found
[2025-10-11 05:43:52,354] WARNING api.exceptions: HTTPException POST /api/intern/prepare-by-file -> 404: uploaded file not found
[2025-10-11 04:51:00,528] WARNING api.exceptions: HTTPException POST /api/intern/prepare-by-file -> 404: uploaded file not found
```

**Key Detail**: Error message is "uploaded file not found" NOT "endpoint not found"
- Endpoint EXISTS and is registered
- Error is from WITHIN the endpoint logic
- Frontend is calling correct endpoint
- **Backend can't find the uploaded audio file**

**Root Cause**: Endpoint receives request but can't locate the audio file it needs to process

**Investigation Needed:**
- Check what filename frontend is sending
- Check where endpoint looks for files (CLEANED_DIR? MEDIA_DIR?)
- Check if files are in GCS vs local filesystem
- Verify file path construction in intern.py

---

## ISSUE #4: Flubber Does Not Work ❌
**Error**: `POST https://api.podcastplusplus.com/api/flubber/prepare-by-file` returns **404**

**Production Logs Show:**
```
[2025-10-11 08:08:53,477] WARNING api.exceptions: HTTPException POST /api/flubber/prepare-by-file -> 404: uploaded file not found
[2025-10-11 08:08:52,203] WARNING api.exceptions: HTTPException POST /api/flubber/prepare-by-file -> 404: uploaded file not found
[2025-10-11 05:46:33,345] WARNING api.exceptions: HTTPException POST /api/flubber/prepare-by-file -> 404: uploaded file not found
[2025-10-11 05:46:31,994] WARNING api.exceptions: HTTPException POST /api/flubber/prepare-by-file -> 404: uploaded file not found
[2025-10-11 05:13:19,731] WARNING api.exceptions: HTTPException POST /api/flubber/prepare-by-file -> 404: uploaded file not found
[2025-10-11 05:12:50,354] WARNING api.exceptions: HTTPException POST /api/flubber/prepare-by-file -> 404: uploaded file not found
[2025-10-11 05:12:41,927] WARNING api.exceptions: HTTPException POST /api/flubber/prepare-by-file -> 404: uploaded file not found
```

**Key Detail**: Same as Intern - error is "uploaded file not found"
- Endpoint EXISTS and is registered  
- Error is from WITHIN the endpoint logic
- Frontend is calling correct endpoint
- **Backend can't find the uploaded audio file**

**Root Cause**: Same as Issue #3 - endpoint receives request but can't locate the audio file

**Investigation Needed:**
- Same as Issue #3 - file path/location problem
- Check flubber.py for file lookup logic
- Verify pydub import guard didn't break anything

---

## ISSUE #5: Why Are 2 Revisions Checked? ℹ️
**Observation**: Cloud Run UI shows 2 revisions selected even though only 1 serves traffic

**Explanation**: This is **NORMAL Cloud Run behavior** during gradual rollout:
- Old revision kept alive for instant rollback
- New revision deployed and tested
- After validation period, old revision can be deleted
- Both show as "selected" but only one gets traffic

**Answer**: Not a problem - standard Cloud Run deployment pattern. Can manually delete old revisions if desired.

**No Action Required** - This is expected behavior

---

## ISSUE #6: Episode Numbering Still Fucked Up ❌
**Symptom**: Set S2E200 at assembly, kicks out wrong number after assembly completes

**Previous Fix Status**: 
- Committed sync.py fix (new episodes stay NULL)
- Committed merge.py protection (existing episodes protected)
- Removed season/episode from publisher.py calls

**Current Problem**: Despite all fixes, numbers STILL getting corrupted

**Possible Causes:**
1. **Fix not deployed yet** - Revision 00522 might not be serving traffic
2. **Another code path** - Something else is setting episode numbers AFTER assembly
3. **Timing issue** - Numbers set correctly, then overwritten later
4. **Database triggers** - Postgres trigger changing values?
5. **Frontend issue** - Wrong values being sent from UI

**Investigation Needed:**
- Trace FULL episode creation flow: UI → assembly → database → publish → sync
- Check if there's a database trigger on Episode table
- Check if there's code AFTER assembly that sets season/episode
- Verify the fix is actually in deployed revision 00522
- Check production database Episode table for actual values

---

## ISSUE #7: Notifications Still Do Not Work Properly ❌
**Symptom**: In-app notifications not appearing or delayed

**Previous Investigation**: Code appears correct, `notify_watchers_processed()` is called

**Possible Causes:**
1. **Notification records not created** - Database write failing
2. **Frontend polling broken** - Not checking for new notifications
3. **Timing issue** - Notification created too late
4. **Database query slow** - Query timeout or performance issue

**Investigation Needed:**
- Check production database `notification` table for recent records
- Check frontend code for notification polling interval
- Check if WebSocket connection for real-time notifications
- Query production logs for notification creation timestamps

---

## ISSUE #8: Emails Still Do Not Go Out ❌
**Symptom**: Transcription completion emails not being sent to users

**Previous Investigation**: Code appears correct, email sending function exists

**Possible Causes:**
1. **SMTP credentials not set in production** - Environment variables missing
2. **SMTP service blocked** - Firewall or Cloud Run networking issue
3. **Email addresses not captured** - TranscriptionWatch records missing email
4. **Mailer service failing silently** - Exceptions being caught

**Investigation Needed:**
- Check production Cloud Run environment variables for SMTP config:
  - `SMTP_HOST`
  - `SMTP_PORT`
  - `SMTP_USER`
  - `SMTP_PASS`
- Check production database `transcriptionwatch` table for email addresses
- Check production logs for SMTP connection errors
- Test SMTP connectivity from Cloud Run container

---

## CRITICAL TRAFFIC ROUTING ISSUE ⚠️

**Problem**: Unclear which revision is serving production traffic

From screenshot: Only revision 00522-7sg shows as serving 100% traffic
From gcloud output: Revision 00521-4tm is tagged "production1" 

**Need to verify:**
```bash
# Route ALL traffic to latest revision
gcloud run services update-traffic podcast-api --region=us-west1 \
  --to-revisions=podcast-api-00522-7sg=100 --project=podcast612
```

**THIS MIGHT BE WHY FIXES AREN'T WORKING** - Old revision still serving requests!

---

## INVESTIGATION PRIORITY ORDER

1. **VERIFY TRAFFIC ROUTING** - Ensure revision 00522 gets 100% traffic
2. **Issue #6 - Episode Numbering** - Most critical user-facing bug
3. **Issue #3 & #4 - Intern/Flubber** - Same root cause, file path problem
4. **Issue #1 - Cannot Play Episodes** - GCS/static file serving
5. **Issue #8 - Emails** - Check SMTP config in production
6. **Issue #7 - Notifications** - Check database and frontend
7. **Issue #2 - Episode Not Deleted** - Likely fixed after traffic routing

---

## NO LOCAL CHANGES

**CRITICAL REMINDER:**
- DO NOT touch local development setup
- DO NOT modify database.py for local connections  
- DO NOT run local database migrations
- FOCUS 100% ON PRODUCTION

All investigation commands must target production:
- Use `--project=podcast612`
- Use `--region=us-west1`
- Query production database only
- Check production Cloud Run logs only
- Check production environment variables only

**Local dev environment can wait - production MUST work NOW.**
