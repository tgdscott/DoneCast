# Dashboard Stats Fix - Episode Count + OP3 Debugging

**Date:** October 12, 2025
**Build ID:** 16ec48b5-3005-402c-88f5-01633d8dc7d2
**Status:** DEPLOYING

## Issues Fixed

### Issue 1: Episode Count Includes Scheduled Episodes ❌

**What User Saw:**
- "Episodes published in last 30 days": 24
- But user has 17 published + 7 scheduled
- Scheduled episodes incorrectly counted as "published"

**Root Cause:**
```python
# OLD CODE - WRONG
episodes_last_30d = session.exec(
    select(func.count(Episode.id)).where(
        Episode.user_id == user_id,
        Episode.publish_at != None,
        Episode.publish_at >= since,  # 30 days ago
    )
).one()
```

This query counts ANY episode with `publish_at` between 30 days ago and infinity. That includes:
- ✅ Episodes published 5 days ago
- ✅ Episodes published 20 days ago
- ❌ Episodes SCHEDULED for 5 days from now (future!)

**The Fix:**
```python
# NEW CODE - CORRECT
episodes_last_30d = session.exec(
    select(func.count(Episode.id)).where(
        Episode.user_id == user_id,
        Episode.publish_at != None,
        Episode.publish_at >= since,  # 30 days ago
        Episode.publish_at <= now,    # ✅ ONLY PAST EPISODES
    )
).one()
```

Now it only counts episodes where:
- `publish_at` is between 30 days ago AND now
- Future scheduled episodes excluded

**Expected Result After Deploy:**
- "Episodes published in last 30 days": 17 (correct!)
- Scheduled episodes shown separately in "Upcoming scheduled": 7

---

### Issue 2: OP3 Analytics Not Working 🔍

**What User Saw:**
- "Analytics Error: Failed to fetch"
- No download numbers showing
- OP3 has been registered for weeks

**Possible Root Causes:**
1. RSS feed URL not configured in database
2. OP3 API has no data for that RSS URL
3. OP3 API endpoint changed/down
4. RSS URL format incorrect
5. OP3 API returned error

**The Fix:**
Added comprehensive logging to diagnose the issue:

```python
# Enhanced logging at each step
if not podcast:
    logger.info("No podcast found for user")
    op3_error_message = "No podcast configured"
    
elif not podcast.rss_feed_url:
    logger.warning(f"Podcast {podcast.id} has no RSS feed URL")
    op3_error_message = "RSS feed not configured"
    
else:
    logger.info(f"Fetching OP3 stats for RSS feed: {rss_url}")
    op3_show_stats = get_show_stats_sync(rss_url, days=30)
    
    if op3_show_stats:
        logger.info(f"OP3 stats SUCCESS: {op3_downloads_30d} downloads")
    else:
        logger.warning("OP3 API returned None")
        op3_error_message = "OP3 API returned no data"
```

**New Response Field:**
```json
{
  "downloads_last_30d": null,
  "op3_enabled": false,
  "op3_error": "RSS feed not configured"  // ✅ NEW - tells us what failed
}
```

---

## How to Diagnose OP3 Issue

Once the build deploys, check Cloud Run logs:

### Check What RSS URL Is Being Used

```bash
gcloud logging read \
  "resource.type=cloud_run_revision AND \
   resource.labels.service_name=podcast-api AND \
   textPayload=~'Fetching OP3 stats'" \
  --limit=5 --project=podcast612
```

**Expected log entries:**
```
INFO: Fetching OP3 stats for RSS feed: https://www.spreaker.com/show/XXXXX/episodes/feed
```

### Check OP3 API Response

```bash
gcloud logging read \
  "resource.type=cloud_run_revision AND \
   resource.labels.service_name=podcast-api AND \
   (textPayload=~'OP3 stats SUCCESS' OR textPayload=~'OP3 API returned')" \
  --limit=5 --project=podcast612
```

**Possible outcomes:**

1. **SUCCESS:**
   ```
   INFO: OP3 stats SUCCESS: 1234 downloads in last 30 days
   ```
   → Downloads will show on dashboard!

2. **NO DATA:**
   ```
   WARNING: OP3 API returned None
   ```
   → OP3 has no data for that RSS URL (not registered or no downloads yet)

3. **NO RSS URL:**
   ```
   WARNING: Podcast XXXXX has no RSS feed URL
   ```
   → Need to ensure podcast.rss_feed_url is set in database

4. **API ERROR:**
   ```
   ERROR: Failed to fetch OP3 analytics: [error details]
   ```
   → Check if OP3 API is down or URL format wrong

---

## Testing Plan

After deployment (build 16ec48b5 completes):

### 1. Check Episode Count ✅
- Refresh dashboard
- "Episodes published in last 30 days" should be **17** (not 24)
- "Upcoming scheduled" should still show **7**

### 2. Check OP3 Analytics 🔍
- Dashboard will still show "Analytics Error" (expected)
- But now we can check Cloud Run logs to see WHY
- Look for log entries with keywords:
  - "Fetching OP3 stats"
  - "OP3 stats SUCCESS"
  - "RSS feed not configured"
  - "Failed to fetch OP3"

### 3. Browser DevTools
- Open browser console (F12)
- Refresh dashboard
- Look at `/api/dashboard/stats` response
- Check `op3_error` field:
  ```json
  {
    "op3_error": "RSS feed not configured"  // tells us the problem
  }
  ```

---

## Likely OP3 Issue Scenarios

### Scenario A: RSS URL Not In Database
**Symptom:** `op3_error: "RSS feed not configured"`

**Fix:** Need to set `podcast.rss_feed_url` in database
```sql
UPDATE podcast 
SET rss_url = 'https://www.spreaker.com/show/XXXXX/episodes/feed'
WHERE user_id = '<user_uuid>';
```

### Scenario B: OP3 Has No Data
**Symptom:** `op3_error: "OP3 API returned no data"`

**Why:** 
- RSS feed not prefixed with OP3 redirects yet
- No podcast apps have downloaded episodes
- OP3 registration incomplete

**Fix:** Verify RSS feed includes OP3 prefixes:
```xml
<enclosure 
  url="https://op3.dev/e/https://storage.googleapis.com/.../episode.mp3" 
  type="audio/mpeg" 
  length="12345678"/>
```

### Scenario C: Wrong RSS URL Format
**Symptom:** `op3_error: "API error: 404 Not Found"`

**Why:** OP3 expects specific URL format

**Current:** `https://www.spreaker.com/show/XXXXX/episodes/feed`
**OP3 Needs:** The URL that podcast apps actually use

**Fix:** Check what URL is in podcast directories (Apple Podcasts, Spotify, etc.)

---

## What Happens After Deploy

### Immediate (Dashboard Display)
- ✅ Episode count fixed (17 instead of 24)
- ❌ OP3 analytics still shows error (but we can now diagnose WHY)

### Diagnostic Phase (Next 10 Minutes)
1. Check Cloud Run logs for "Fetching OP3 stats" message
2. See what RSS URL is being queried
3. Check if OP3 API returns data or error
4. Identify root cause from logs

### Resolution Phase (Depends on Root Cause)
- **If RSS URL missing:** Add to database → redeploy
- **If OP3 has no data:** Wait for downloads, verify RSS prefixes
- **If API error:** Fix URL format or OP3 API issue

---

## Next Steps

1. ✅ **Deploy completes** (~8 minutes)
2. ✅ **Verify episode count** fixed (17, not 24)
3. 🔍 **Check Cloud Run logs** for OP3 diagnostic info
4. 🔍 **Identify OP3 failure reason** from logs
5. 🔧 **Apply targeted fix** based on diagnosis

---

**Build:** `16ec48b5-3005-402c-88f5-01633d8dc7d2`
**Commit:** `fix: Dashboard stats - exclude future scheduled episodes from 30-day count + add OP3 error logging`
