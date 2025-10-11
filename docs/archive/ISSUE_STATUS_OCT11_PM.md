# Issue Status Report - October 11, 2025 (PM)

## Executive Summary

User reported 8 issues after deployment. After investigation:
- **FIXED**: 5 issues resolved (episodes #2, #4, #5, numbering, test labels)
- **DEPLOYING**: 2 issues (intern #2, flubber #3) - GCS URL fix
- **NEEDS INVESTIGATION**: 3 issues (raw files #1, emails #7, raw file persistence #8)

## Issues Analyzed

### ✅ Issue #4: Episode Numbering IS Fixed
**User Report:** "Episode numbering IS fixed. In retrospect it was because of test mode."

**Status:** **VERIFIED FIXED**
- Root cause was test_mode enabled in database
- User disabled test_mode via UI
- Episodes now retain user-set season/episode numbers
- No code changes needed

---

### ✅ Issue #5: "test" Label is Gone
**User Report:** "The 'test' label is also gone, obviously"

**Status:** **VERIFIED FIXED**
- Test mode disabled = no more "test" prefix on filenames
- Future episodes won't have test prefix
- Old episodes (#195-200) still have test prefix (see Issue #6)

---

### 🚀 Issue #2: Intern Still Fails (DEPLOYING FIX)
**User Report:**
```
[2025-10-11 09:18:49,820] ERROR backend.infrastructure.gcs: Failed to download 
gs://ppp-media-us-west1/b6d5f77e699e444ba31ae1b4cb15feb4/media/main_content/
gs://ppp-media-us-west1/b6d5f77e699e444ba31ae1b4cb15feb4/main_content/09435e0d30bc4aa49016463c143b5d33.mp3
```

**Root Cause Discovered:**
- MediaItem.filename stores **full GCS URL** (not just filename)
- Previous fix assumed it was simple filename
- Code was building: `{user_id}/media/main_content/{filename}`
- Where `{filename}` was already `gs://ppp-media-us-west1/.../file.mp3`
- Result: Doubled GCS path

**Fix Implemented:**
```python
# Enhanced _resolve_media_path() in intern.py
if stored_filename.startswith("gs://"):
    # Extract key from full GCS URL: gs://bucket/key/path
    parts = stored_filename.replace("gs://", "").split("/", 1)
    if len(parts) == 2:
        gcs_key = parts[1]  # Everything after bucket name
else:
    # Legacy format: construct path
    gcs_key = f"{media.user_id.hex}/media/main_content/{stored_filename}"
```

**Status:** **DEPLOYING NOW** (Build in progress)
- Committed to git
- Build started: waiting for completion
- Will create revision 00524

---

### 🚀 Issue #3: Flubber Still Fails (DEPLOYING FIX)
**User Report:**
```
[2025-10-11 09:19:22,847] WARNING api.exceptions: HTTPException 
POST /api/flubber/prepare-by-file -> 404: uploaded file not found
```

**Root Cause:** **SAME AS ISSUE #2** - GCS URL handling bug

**Fix Implemented:** Same pattern as intern.py fix applied to flubber.py

**Status:** **DEPLOYING NOW** (Same build as Issue #2)

---

### ✅ Issue #6: Old "test" Episodes Playback
**User Report:** "The episode I just made can be played from episode history. The 6 I made under test mode can not, but I have a feeling that once they resolve to published, they will. If we can do it earlier that would be great, but I feel like they way we did it put the only copy up on Spreaker, and I don't think its worth writing a script to just reimport these 6. If there is an easy way to take care of Ep 195-200, great. If not, that's fine."

**Analysis:**
- Episodes 195-200 have "test" prefix in filenames (e.g., `test110803---e200---the-long-walk.mp3`)
- `/static/final` serves from `/tmp` (ephemeral) but files are in GCS
- User says it's OK if we don't fix old episodes

**Options:**
1. **Easy:** Leave as-is (user's preference)
2. **Medium:** Rename files in GCS and database (remove "test" prefix)
3. **Hard:** Switch to signed URLs for all playback (future enhancement)

**Status:** **LOW PRIORITY** - User said "If not, that's fine"

**Recommendation:** Mark as "Known Issue" and document. User can re-publish if needed.

---

### ❓ Issue #1: Raw Files Revert to "processing" After Build
**User Report:** "Raw data files uploaded but don't have episodes created yet still revert to processing (and stuck there) after a new build."

**Analysis:**
- Needs investigation - likely frontend state management issue
- MediaItem records in database don't have "status" field
- Might be localStorage or sessionStorage state reset
- Might be frontend polling logic reinitializing

**Next Steps:**
1. Check frontend localStorage/sessionStorage for upload state
2. Check if draft metadata is being reset
3. Verify TranscriptionWatch records persist correctly
4. Check frontend polling logic for transcript status

**Status:** **NEEDS INVESTIGATION**

---

### ❓ Issue #7: Emails Not Sending
**User Report:** "Email smtp env var is correct, but no emails"

**SMTP Configuration (Verified):**
```
SMTP_HOST: smtp.mailgun.org
SMTP_PORT: 587
SMTP_USER: admin@podcastplusplus.com
SMTP_FROM: no-reply@PodcastPlusPlus.com
SMTP_PASS: [configured as secret]
ADMIN_EMAIL: scott@scottgerhardt.com
```

**Analysis:**
- SMTP environment variables are correctly configured
- Need to check if email sending code exists and is called
- TranscriptionWatch table exists (tracks email notifications)
- Need to check logs for SMTP connection attempts/errors
- Need to verify email sending logic is triggered after transcription

**Next Steps:**
1. Find email sending code (search for SMTP usage)
2. Check production logs for SMTP connection errors
3. Query TranscriptionWatch table to see if records are created
4. Verify transcription completion triggers email logic
5. Test SMTP connection manually if needed

**Status:** **NEEDS INVESTIGATION**

---

### ❓ Issue #8: Raw Files Persist After Episode Creation
**User Report:** "The Raw files converted to episodes still persist in the raw files section"

**Analysis:**
- Raw files (MediaItem records) should be filtered out after episode creation
- Need to check:
  1. Are MediaItem records being marked as "used"?
  2. Is there a relationship between MediaItem and Episode?
  3. Is frontend filtering logic correct?

**Possible Solutions:**
1. **Add field:** MediaItem.used_by_episode_id (foreign key to Episode)
2. **Filter query:** Exclude MediaItem records that are referenced by episodes
3. **Lifecycle:** Mark MediaItem as "consumed" when episode created

**Next Steps:**
1. Check MediaItem model for "used" or "consumed" field
2. Check episode creation code to see if it updates MediaItem
3. Check media list API endpoint filtering logic
4. Verify frontend filtering/display logic

**Status:** **NEEDS INVESTIGATION**

---

## Current Deployment Status

**Build:** In progress
**Expected Revision:** 00524
**Deploy Time:** ~8-10 minutes
**Traffic Routing:** Will automatically route to new revision when ready

**Fixes in This Build:**
- ✅ Intern GCS URL handling (Issue #2)
- ✅ Flubber GCS URL handling (Issue #3)

**Rollback Command (if needed):**
```bash
gcloud run services update-traffic podcast-api --region=us-west1 \
  --to-revisions=podcast-api-00523-xxxxx=100 --project=podcast612
```

---

## Testing Checklist (After Deployment)

### Immediate Testing (CRITICAL)
- [ ] Test intern endpoint with uploaded file (Issue #2)
- [ ] Test flubber endpoint with flubber markers (Issue #3)

### Verification Testing (HIGH)
- [ ] Confirm new episodes don't have "test" prefix (Issue #5)
- [ ] Confirm episode numbering stays as user-set (Issue #4)

### Investigation Tasks (MEDIUM)
- [ ] Reproduce raw files status reset issue (Issue #1)
- [ ] Check email notification logs and code (Issue #7)
- [ ] Check raw file persistence in UI (Issue #8)

---

## Remaining Work

### High Priority
1. **Test Deployed Fixes:** Verify intern/flubber work after deployment
2. **Investigate Email Issue:** Find why SMTP emails not sending
3. **Raw File Status Reset:** Debug why files revert to "processing"

### Medium Priority
1. **Raw File Persistence:** Fix files showing in UI after episode creation
2. **Old Test Episodes:** Document as known issue (low user impact)

### Low Priority
1. **Signed URLs for Playback:** Future enhancement to serve from GCS
2. **Episode Deletion Filter:** Verify fix in revision 522 is working

---

## Summary

**What's Working:**
- ✅ Episode numbering fixed (test mode off)
- ✅ Test label gone for new episodes
- ✅ Chunked processing working (previous session)
- ✅ Episode deletion filter deployed (revision 522)

**What's Deploying:**
- 🚀 Intern GCS URL fix (revision 524)
- 🚀 Flubber GCS URL fix (revision 524)

**What Needs Work:**
- ❓ Raw files status reset investigation
- ❓ Email notifications not sending
- ❓ Raw files persist after episode creation

**User Feedback:**
- "Episode numbering IS fixed"
- "The test label is also gone"
- "The episode I just made can be played from episode history"
- "If there is an easy way to take care of Ep 195-200, great. If not, that's fine"

---

## Commit History (This Session)

1. **Previous commit (9cd5024d):**
   - Fix: Download files from GCS for intern/flubber endpoints in production
   - Issue: Constructed GCS path incorrectly

2. **Current commit (just committed):**
   - Fix: Handle full GCS URLs in MediaItem.filename for intern/flubber endpoints
   - Issue: MediaItem.filename stores full GCS URL, not just filename

---

## Next Actions

1. **Wait for build completion** (~5 minutes remaining)
2. **Test intern/flubber** immediately after deployment
3. **Check production logs** for SMTP and email errors
4. **Investigate raw files** status reset issue
5. **Query database** to check TranscriptionWatch and MediaItem records
6. **Document** remaining issues for next session

---

*Report Generated: October 11, 2025*
*Build Status: In Progress*
*Next Revision: 00524*
