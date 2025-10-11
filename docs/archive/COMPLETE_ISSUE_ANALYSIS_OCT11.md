# PRODUCTION ISSUE ROOT CAUSES - COMPLETE ANALYSIS

## Date: October 11, 2025
## Revision: podcast-api-00522-7sg (100% traffic)
## Build: cf2c110d

---

## ISSUE #1: Cannot Play Any Episodes (500 Errors) ❌

### Symptom
```
GET https://api.podcastplusplus.com/static/final/test110803---e200---the-long-walk---what-would-you-do.mp3
→ 500 Internal Server Error
```

### Root Causes (Multiple)

#### Cause 1A: TEST MODE ENABLED IN PRODUCTION ⚠️ **CRITICAL**
- **Location**: `backend/api/services/episodes/assembler.py` line 547
- **Code**:
```python
admin_rec = session.get(AppSetting, 'admin_settings')
adm = json.loads(admin_rec.value_json or '{}') if admin_rec else {}
test_mode = bool(adm.get('test_mode'))  # ← Reading from database

if test_mode:
    output_filename = f"test{sn_input}{en_input}---{slug}"  # ← Adds "test" prefix
```

- **Database State**: `appsetting` table has `admin_settings` with `{"test_mode": true}`
- **Impact**: ALL episode filenames get "test" prefix in production
- **Fix**: 
```sql
UPDATE appsetting SET value_json = '{"test_mode": false}' WHERE key = 'admin_settings';
```

#### Cause 1B: Static File Serving from Local Filesystem
- **Location**: `backend/api/app.py` line 311
- **Code**:
```python
app.mount("/static/final", StaticFiles(directory=str(FINAL_DIR), check_dir=False), name="final")
```

- **Problem**: `FINAL_DIR` = `/tmp/final_episodes` (ephemeral container filesystem)
- **Reality**: Files are actually in GCS: `gs://ppp-media-us-west1/.../final/`
- **Result**: FastAPI looks in /tmp, doesn't find files, returns 404/500

#### Cause 1C: Files Should Use Signed URLs, Not Static Serving
- **Expected Behavior**: Episodes should be served via GCS signed URLs
- **Current Behavior**: Frontend tries to load from `/static/final/` (local filesystem)
- **Problem**: In production containers, local filesystem is ephemeral - files don't persist
- **Solution**: Generate and return GCS signed URLs instead of local paths

### Fix Strategy
1. **Immediate**: Disable test_mode in database (SQL UPDATE)
2. **Short-term**: Verify files are being uploaded to GCS correctly
3. **Medium-term**: Change episode API to return signed URLs instead of `/static/final/` paths
4. **Long-term**: Remove `/static/final` mount entirely for production (only dev)

---

## ISSUE #2: Episode Not Deleted After Creation ⏳

### Symptom
Used audio file still appears in "Choose Processed Audio" picker in Step 2

### Root Cause
- **Location**: `backend/api/routers/media.py` lines 530-538 (ALREADY FIXED in 00522)
- **Previous Problem**: Filter only excluded `published` or `processed+scheduled` episodes
- **Fix Deployed**: Now filters ALL episodes with `working_audio_name` set
- **Status**: Should be working now that 00522 is serving traffic

### Testing Required
1. Clear browser cache
2. Create new episode using audio file
3. Check if file disappears from picker (regardless of episode status)

---

## ISSUE #3: Intern Does Not Work ❌

### Symptom
```
POST https://api.podcastplusplus.com/api/intern/prepare-by-file
→ 404 "uploaded file not found"
```

### Root Cause
- **Location**: `backend/api/routers/intern.py` line 116
- **Code**:
```python
def _resolve_media_path(filename: str) -> Path:
    candidate = (MEDIA_DIR / filename).resolve()  # /tmp/local_media/filename
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="uploaded file not found")
```

- **Problem**: Looks for files in `MEDIA_DIR` = `/tmp/local_media` (local filesystem)
- **Reality**: Files are in GCS: `gs://ppp-media-us-west1/.../main_content/`
- **Impact**: Endpoint receives request successfully, but can't find audio file to process

### Fix Required
1. Query `MediaItem` table to get GCS path for filename
2. Download file from GCS using `gcs.download_bytes()`
3. Save to temp location in `/tmp`
4. Process file
5. Clean up temp file after

**Code Change Needed**:
```python
def _resolve_media_path(filename: str, session) -> Path:
    # Get MediaItem record
    media = session.exec(
        select(MediaItem).where(MediaItem.filename == filename)
    ).first()
    
    if not media or not media.object_path:
        raise HTTPException(status_code=404, detail="uploaded file not found")
    
    # Download from GCS to temp location
    temp_dir = Path("/tmp/intern_temp")
    temp_dir.mkdir(exist_ok=True)
    temp_file = temp_dir / filename
    
    # Download from GCS
    gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
    data = gcs.download_bytes(gcs_bucket, media.object_path)
    if not data:
        raise HTTPException(status_code=404, detail="file not found in GCS")
    
    temp_file.write_bytes(data)
    return temp_file
```

---

## ISSUE #4: Flubber Does Not Work ❌

### Symptom  
```
POST https://api.podcastplusplus.com/api/flubber/prepare-by-file
→ 404 "uploaded file not found"
```

### Root Cause
**IDENTICAL TO ISSUE #3**

- **Location**: `backend/api/routers/flubber.py` line 173
- **Problem**: Looks in local `CLEANED_DIR` or `MEDIA_DIR` for files
- **Reality**: Files are in GCS
- **Fix**: Same as Issue #3 - download from GCS first

---

## ISSUE #5: Why Are 2 Revisions Checked? ✅

### Answer
**Normal Cloud Run behavior** for safe deployments:
- Old revision (00521) kept for instant rollback
- New revision (00522) deployed and tested
- Both show as "selected" in UI
- Traffic routing determines which actually serves requests
- Old revisions automatically deleted after 7-30 days

**Status**: Not a problem - working as designed

---

## ISSUE #6: Episode Numbering Still Corrupted ⏳

### Symptom
Set S2E200 at assembly → Wrong number after assembly completes

### Deployed Fixes (in revision 00522)
1. `sync.py` line 420: New episodes from Spreaker get `season_number=None`, `episode_number=None`
2. `merge.py` lines 229-252: Existing episodes protected from Spreaker overwrite
3. `publisher.py`: Removed season/episode params from Spreaker API calls
4. `publish.py`: Removed parameters from all call sites

### Why It Might Still Be Broken
Need to trace the FULL flow to find where numbers are being changed:

1. **UI → Assembly**: User sets S2E200
2. **Assembly → Database**: Episode record created with season=2, episode=200
3. **Publish → Spreaker**: Send to Spreaker (WITHOUT season/episode per fix)
4. **Spreaker Response**: Returns S11E346 (their auto-assigned number)
5. **Sync Back**: Call `sync_spreaker_episodes()`
   - **OLD CODE**: Would overwrite to S11E346
   - **NEW CODE**: Should preserve S2E200 (if fix works)

**Possible Issues**:
- Fix not actually in deployed code (need to verify git commit)
- Another code path bypassing the protection
- Database trigger or constraint
- Frontend sending wrong values

### Testing Required
1. Create episode with explicit S2E200
2. Check database: `SELECT season_number, episode_number FROM episode WHERE id = '<episode_id>';`
3. Publish to Spreaker
4. Check database again immediately after publish
5. Wait for sync to run
6. Check database one more time
7. Identify exact step where number changes

---

## ISSUE #7: Notifications Not Working ❌

### Symptom
In-app notifications not appearing or delayed

### Investigation Required
1. **Check database**:
```sql
SELECT * FROM notification 
WHERE type = 'transcription'
ORDER BY created_at DESC 
LIMIT 20;
```

2. **Check if records created**: If no records, notification creation is broken
3. **Check timestamps**: If records exist, compare created_at with event time
4. **Check frontend**: Verify polling interval and API calls in DevTools

### Possible Causes
- Notification records not being written to database
- `notify_watchers_processed()` not being called (BUT logs show it is)
- Frontend polling too infrequent
- WebSocket not connected
- Database query performance issue

---

## ISSUE #8: Emails Not Sending ❌

### Symptom
Transcription completion emails not being sent

### Investigation Required
1. **Check Cloud Run env vars**:
```bash
gcloud run services describe podcast-api --region=us-west1 --format=json | 
  jq '.spec.template.spec.containers[0].env[] | select(.name | contains("SMTP"))'
```

2. **Required variables**:
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASS` (or `SMTP_PASSWORD`)

3. **Check database**:
```sql
SELECT * FROM transcriptionwatch 
WHERE notify_email IS NOT NULL
ORDER BY created_at DESC 
LIMIT 20;
```

4. **Check logs for SMTP errors**:
```bash
gcloud logging read 'resource.type=cloud_run_revision AND 
  resource.labels.service_name=podcast-api AND 
  (textPayload:"SMTP" OR textPayload:"mail")' 
  --limit=50 --project=podcast612
```

### Possible Causes
- SMTP credentials not set in Cloud Run
- SMTP service blocked by Cloud Run networking
- User not checking "Email me when ready" option
- `TranscriptionWatch` records missing email addresses
- Mailer service failing silently

---

## PRIORITY FIXES

### 1. CRITICAL: Disable Test Mode (SQL UPDATE - 30 seconds)
```sql
UPDATE appsetting SET value_json = '{"test_mode": false}' WHERE key = 'admin_settings';
```
**Impact**: Fixes filenames, may fix playback

### 2. HIGH: Fix Intern/Flubber GCS Downloads (Code Change - 2 hours)
Modify both endpoints to download from GCS before processing
**Impact**: Fixes Issues #3 and #4

### 3. HIGH: Switch to Signed URLs for Episode Playback (Code Change - 4 hours)
Return GCS signed URLs instead of `/static/final/` paths
**Impact**: Fixes Issue #1 completely

### 4. MEDIUM: Investigate Episode Numbering (Testing - 1 hour)
Trace full flow to find where S2E200 → S11E346 happens
**Impact**: Verifies if Issue #6 fix is working

### 5. MEDIUM: Check SMTP Configuration (Investigation - 30 min)
Verify env vars are set in Cloud Run
**Impact**: May fix Issue #8

### 6. LOW: Check Notification Creation (Investigation - 30 min)
Query database to see if records are being created
**Impact**: Diagnoses Issue #7

---

## SUMMARY

| Issue | Root Cause | Fix Status | Priority |
|-------|-----------|------------|----------|
| #1 Playing episodes | Test mode + local filesystem | ❌ Not Fixed | CRITICAL |
| #2 Episode deletion | Filter logic | ⏳ Fixed in 00522 | Test |
| #3 Intern 404 | Local FS vs GCS | ❌ Code change needed | HIGH |
| #4 Flubber 404 | Local FS vs GCS | ❌ Code change needed | HIGH |
| #5 Dual revisions | Normal behavior | ✅ Explained | N/A |
| #6 Episode numbers | Unknown if fix works | ⏳ Testing needed | MEDIUM |
| #7 Notifications | Unknown | ❌ Investigation needed | MEDIUM |
| #8 Emails | SMTP config? | ❌ Investigation needed | MEDIUM |

**Next Action**: Disable test_mode in production database NOW (30 seconds, massive impact)
