# Analytics Investigation Report

## Summary

This report investigates the analytics system, addressing:
1. How analytics pings work when someone plays an episode
2. Cinema IRL historical data merge issue
3. Front page analytics display logic
4. All-time data from newest episodes
5. Data availability for tier gating

---

## 1. Analytics Ping Mechanism

### How It Works

**OP3 (Open Podcast Prefix Project)** tracks downloads by acting as a redirect proxy:

1. **RSS Feed Generation**: Audio URLs are prefixed with `https://analytics.podcastplusplus.com/e/` (self-hosted OP3 instance)
   - Example: `https://analytics.podcastplusplus.com/e/https://storage.googleapis.com/...?signature=...`
   - Code location: `backend/api/routers/rss_feed.py` line 232-240

2. **Podcast App Request**: When a podcast app downloads an episode:
   - App requests: `https://analytics.podcastplusplus.com/e/{actual_audio_url}`
   - OP3 logs: IP (hashed), user-agent, timestamp, country, episode URL
   - OP3 redirects: HTTP 302 to the actual audio URL
   - App downloads: From the actual storage (GCS/R2)

3. **Analytics Collection**: OP3 aggregates these logs and provides stats via API

### What Makes It Show Up as a Ping

Every download request goes through OP3 first, which creates a log entry. This is the "ping" - it's the HTTP request to OP3 before the actual audio download. The ping happens automatically when:
- A podcast app downloads an episode from the RSS feed
- A user plays an episode in a web player (if using OP3-prefixed URLs)
- A user downloads an episode manually (if using OP3-prefixed URLs)

**Key Files:**
- `backend/api/routers/rss_feed.py` - Adds OP3 prefix to audio URLs
- `op3-self-hosted/worker/routes/redirect_episode.ts` - OP3 redirect logic

---

## 2. Cinema IRL Historical Data Merge Issue

### Current Behavior

The historical TSV data (`cinema-irl-episode-downloads.tsv`) is **NOT being merged** with new OP3 data. Instead, it's used as a **fallback only** when OP3 returns no data.

**Code Location**: `backend/api/routers/analytics.py` lines 112-142

```python
if not stats or (hasattr(stats, 'downloads_30d') and stats.downloads_30d == 0 and stats.downloads_all_time == 0):
    # Try historical TSV fallback
    historical = get_historical_data()
    # ... returns historical data only
```

### Problem

- If OP3 has **any data** (even 1 download), historical data is ignored
- Historical data should be **merged** with new OP3 data, not replaced
- All-time downloads should = historical all-time + new OP3 downloads since migration

### Solution Needed

1. Load historical data from TSV
2. Fetch new OP3 data
3. Merge them:
   - 7d/30d/365d: Use OP3 data only (historical is old)
   - All-time: Historical all-time + OP3 all-time (since migration date)
   - Top episodes: Combine historical and OP3 episodes, sort by all-time

---

## 3. Front Page Analytics Display

### Current State

**The front page does NOT display analytics data.**

- `/api/sites/{subdomain}` endpoint (`backend/api/routers/sites.py`) returns:
  - Podcast info
  - Episodes list
  - Sections config
  - **NO analytics data**

- Front page components (`frontend/src/components/website/sections/SectionPreviews.jsx`) don't have analytics display

### Requirements

Front page should show:
- **7 days** - if podcast exists >= 7 days
- **30 days** - if podcast exists >= 30 days
- **365 days** - if podcast exists >= 365 days
- **All-time** - always show
- **Don't repeat** - if podcast is < 30 days, only show 7d and all-time

### Solution Needed

1. Create public analytics endpoint: `/api/public/podcast/{podcast_id}/analytics`
   - No authentication required
   - Returns: 7d, 30d, 365d, all-time downloads
   - Smart filtering based on podcast age

2. Add analytics section to website builder
   - New section type: "Stats" or "Analytics"
   - Displays download counts with smart time period selection

3. Calculate podcast age:
   - Use `podcast.created_at` or first episode `publish_at`
   - Filter time periods based on age

---

## 4. All-Time Data from Newest Episodes

### Current Behavior

**OP3 API only returns recent episodes**, not all episodes.

**Code Location**: `backend/api/services/op3_analytics.py` lines 248-268

```python
# OP3 episode-download-counts ONLY returns all-time downloads per episode
# Time-windowed stats (7d, 30d, 365d) come from show-level endpoint only
for ep in episodes:
    ep_all_time = ep.get("downloadsAll", 0)
    if ep_all_time:
        downloads_all_time += ep_all_time
```

**Warning in code**: Line 268
```python
logger.info(f"OP3:   - Total from episodes = {downloads_all_time} (⚠️ WARNING: only recent episodes returned, NOT true all-time!)")
```

### Problem

- OP3's `episode-download-counts` endpoint returns only **recent episodes** (likely last 50-100)
- Older episodes are not included in the response
- All-time downloads are **underestimated** because older episodes are missing

### Solution Options

1. **Use show-level all-time data**: OP3's `show-download-counts` endpoint might have better all-time data
2. **Merge with historical data**: Use historical TSV for older episodes, OP3 for new episodes
3. **Paginate OP3 requests**: Request all episodes in batches (if OP3 supports pagination)
4. **Accept limitation**: Document that all-time is "all-time for recent episodes" only

---

## 5. Data Availability for Tier Gating

### What Data Can Be Pulled from OP3

#### Show-Level Stats (via `show-download-counts`)
- `monthlyDownloads` - Last 30 days
- `weeklyDownloads` - Array of daily downloads (last N weeks)
- Can calculate: 7d, 30d, 365d, all-time (sum of weeklyDownloads)

#### Episode-Level Stats (via `episode-download-counts`)
- `downloadsAll` - All-time downloads per episode
- **Limited**: Only returns recent episodes (last 50-100)
- **No time-windowed stats** per episode (7d, 30d per episode not available)

#### Additional Data (if available)
- Geographic breakdown (countries)
- App/platform breakdown (Apple Podcasts, Spotify, etc.)
- Time-series data (downloads by day)
- Top episodes list

### Tier Gating Strategy

**Free Tier:**
- Basic stats: 7d, 30d, all-time downloads
- Top 3 episodes
- No geographic/app breakdown
- No time-series data

**Paid Tier:**
- Advanced stats: 7d, 30d, 365d, all-time
- Top 10 episodes
- Geographic breakdown
- App/platform breakdown
- Time-series data (downloads by day)
- Episode-level stats

**Code Location**: `backend/api/routers/analytics.py` lines 25-46
- `assert_analytics_access()` function checks user tier
- Uses `api.billing.plans.can_access_analytics()`

---

## Recommendations

### Immediate Fixes

1. **Fix Cinema IRL Historical Data Merge**
   - Merge historical TSV data with new OP3 data
   - All-time = historical all-time + OP3 all-time since migration
   - Top episodes = combine and sort by all-time

2. **Fix Front Page Analytics Display**
   - Create public analytics endpoint
   - Add analytics section to website builder
   - Implement smart time period filtering based on podcast age

3. **Fix All-Time Data from Newest Episodes**
   - Merge historical data for older episodes
   - Use show-level all-time data if available
   - Document limitation if OP3 doesn't return all episodes

### Long-Term Improvements

1. **Better Data Aggregation**
   - Store analytics data in database
   - Cache OP3 responses
   - Merge historical and new data automatically

2. **Enhanced Analytics**
   - Episode-level time-windowed stats (7d, 30d per episode)
   - Geographic and app breakdowns
   - Time-series charts
   - Export to CSV

3. **Tier Gating Implementation**
   - Implement tier-based data access
   - Show upgrade prompts for restricted data
   - Cache tier checks for performance

---

## Files to Modify

1. `backend/api/routers/analytics.py` - Merge historical data with OP3 data
2. `backend/api/routers/sites.py` - Add analytics data to public website endpoint
3. `backend/api/routers/public.py` - Create public analytics endpoint
4. `backend/api/services/op3_analytics.py` - Improve all-time data aggregation
5. `backend/api/services/op3_historical_data.py` - Add merge functionality
6. `frontend/src/components/website/sections/SectionPreviews.jsx` - Add analytics section
7. `frontend/src/pages/PublicWebsite.jsx` - Fetch and display analytics data

---

## Data Flow Diagram

```
RSS Feed → OP3-Prefixed URL → Podcast App Request → OP3 Logs → OP3 API → Your Backend → Frontend
                ↓
         Historical TSV Data (Cinema IRL) → Merge with OP3 Data → Display
```

---

## Next Steps

1. Implement historical data merge
2. Create public analytics endpoint
3. Add analytics section to website builder
4. Fix all-time data aggregation
5. Implement tier gating
6. Test with Cinema IRL data
7. Document data limitations






