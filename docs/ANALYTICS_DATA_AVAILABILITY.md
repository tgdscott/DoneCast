# Analytics Data Availability for Tier Gating

## Summary

This document outlines what data can be pulled from OP3 (Open Podcast Prefix Project) and how it can be used for tier gating.

---

## Data Available from OP3

### Show-Level Stats (via `show-download-counts`)

**Endpoint**: `GET /api/1/queries/show-download-counts?showUuid={uuid}&token={token}`

**Data Available**:
- `monthlyDownloads` - Last 30 days
- `weeklyDownloads` - Array of daily downloads (last N weeks)
- Can calculate:
  - **7d**: Sum of last 7 days from `weeklyDownloads`
  - **30d**: `monthlyDownloads` (last 30 days)
  - **365d**: Sum of last 365 days from `weeklyDownloads` (if available)
  - **All-time**: Sum of all `weeklyDownloads` (if available)

**Limitations**:
- `weeklyDownloads` array length depends on how long OP3 has been tracking
- May not include all historical data (only data since OP3 started tracking)
- No geographic breakdown at show level
- No app/platform breakdown at show level

**Code Location**: `backend/api/services/op3_analytics.py` lines 147-220

---

### Episode-Level Stats (via `episode-download-counts`)

**Endpoint**: `GET /api/1/queries/episode-download-counts?showUuid={uuid}&token={token}`

**Data Available**:
- `downloadsAll` - All-time downloads per episode
- Episode metadata: `title`, `itemGuid`, `pubdate`

**Limitations**:
- **Only returns recent episodes** (last 50-100 episodes)
- **No time-windowed stats** per episode (7d, 30d, 365d not available)
- Older episodes are not included in the response
- All-time downloads are **underestimated** because older episodes are missing

**Code Location**: `backend/api/services/op3_analytics.py` lines 231-294

**Warning in Code** (line 268):
```python
logger.info(f"OP3:   - Total from episodes = {downloads_all_time} (⚠️ WARNING: only recent episodes returned, NOT true all-time!)")
```

---

### Additional Data (Future/Not Yet Implemented)

**Geographic Breakdown**:
- Countries
- Regions
- Cities (if available)

**App/Platform Breakdown**:
- Apple Podcasts
- Spotify
- Overcast
- Pocket Casts
- Google Podcasts
- etc.

**Time-Series Data**:
- Downloads by day
- Downloads by hour
- Downloads by week
- Downloads by month

**User-Agent Analysis**:
- Podcast app user-agents
- Browser user-agents
- Bot user-agents

---

## Historical Data (Cinema IRL)

**Source**: `cinema-irl-episode-downloads.tsv`

**Data Available**:
- `downloads_3d` - Last 3 days
- `downloads_7d` - Last 7 days
- `downloads_30d` - Last 30 days
- `downloads_all_time` - All-time downloads
- Episode metadata: `episode_title`, `episode_pub_date`, `downloads_asof`

**Limitations**:
- Only for Cinema IRL podcast
- Pre-migration data (before self-hosted OP3)
- No 365-day data
- No geographic/app breakdown

**Code Location**: `backend/api/services/op3_historical_data.py`

---

## Tier Gating Strategy

### Free Tier

**Available Data**:
- Basic stats: 7d, 30d, all-time downloads
- Top 3 episodes (by all-time downloads)
- No geographic/app breakdown
- No time-series data
- No episode-level stats

**API Endpoints**:
- `GET /api/analytics/podcast/{id}/downloads?days=30` (limited to 7d, 30d, all-time)

**Code Location**: `backend/api/routers/analytics.py` lines 25-46
- `assert_analytics_access(user, "basic")` - checks user tier
- Uses `api.billing.plans.can_access_analytics()`

---

### Paid Tier (Basic)

**Available Data**:
- Basic stats: 7d, 30d, all-time downloads
- Top 10 episodes (by all-time downloads)
- No geographic/app breakdown
- No time-series data
- No episode-level stats

**API Endpoints**:
- `GET /api/analytics/podcast/{id}/downloads?days=30` (limited to 7d, 30d, all-time)

---

### Paid Tier (Advanced)

**Available Data**:
- Advanced stats: 7d, 30d, 365d, all-time downloads
- Top 10 episodes (by all-time downloads)
- Geographic breakdown (countries)
- App/platform breakdown
- Time-series data (downloads by day)
- No episode-level stats

**API Endpoints**:
- `GET /api/analytics/podcast/{id}/downloads?days=365` (full access)
- `GET /api/analytics/podcast/{id}/episodes-summary?limit=10`

---

### Paid Tier (Full)

**Available Data**:
- Full stats: 7d, 30d, 365d, all-time downloads
- Top 10 episodes (by all-time downloads)
- Geographic breakdown (countries, regions)
- App/platform breakdown
- Time-series data (downloads by day, hour, week, month)
- Episode-level stats (per-episode downloads)
- User-agent analysis
- Export to CSV

**API Endpoints**:
- `GET /api/analytics/podcast/{id}/downloads?days=365` (full access)
- `GET /api/analytics/podcast/{id}/episodes-summary?limit=10`
- `GET /api/analytics/episode/{id}/downloads?days=365`
- `GET /api/analytics/podcast/{id}/export?format=csv`

---

## Data Limitations

### All-Time Data

**Problem**: OP3's `episode-download-counts` endpoint only returns recent episodes (last 50-100), not all episodes.

**Solution**: 
1. Merge historical data (Cinema IRL TSV) with new OP3 data
2. Use show-level all-time data (sum of `weeklyDownloads`) as fallback
3. Document limitation: "All-time downloads include data from recent episodes only"

**Code Location**: `backend/api/routers/analytics.py` lines 112-266

---

### Time-Windowed Stats per Episode

**Problem**: OP3's `episode-download-counts` endpoint doesn't provide time-windowed stats (7d, 30d, 365d) per episode.

**Solution**:
1. Use show-level stats for time-windowed data
2. Estimate per-episode stats based on show-level stats and episode age
3. Document limitation: "Per-episode time-windowed stats are estimates based on show-level data"

---

### Geographic/App Breakdown

**Problem**: OP3's `show-download-counts` and `episode-download-counts` endpoints don't provide geographic/app breakdown.

**Solution**:
1. Use OP3's raw download logs (if available)
2. Aggregate by country/app from user-agent and IP hash
3. Document limitation: "Geographic/app breakdown requires additional data processing"

---

## Public Analytics Endpoint

**Endpoint**: `GET /api/public/podcast/{podcast_id}/analytics`

**Purpose**: Public analytics for podcast front page (no authentication required)

**Data Available**:
- Smart time period filtering based on podcast age:
  - **7d**: if podcast exists >= 7 days
  - **30d**: if podcast exists >= 30 days
  - **365d**: if podcast exists >= 365 days
  - **All-time**: always shown
  - **Don't repeat**: if podcast is < 30 days, only show 7d and all-time

**Code Location**: `backend/api/routers/public.py` lines 120-248

---

## Recommendations

### Immediate Actions

1. **Implement Tier Gating**:
   - Add tier checks to analytics endpoints
   - Return limited data for free tier
   - Show upgrade prompts for restricted data

2. **Fix All-Time Data**:
   - Merge historical data with new OP3 data
   - Use show-level all-time data as fallback
   - Document limitation

3. **Add Public Analytics Endpoint**:
   - Create public endpoint for front page
   - Implement smart time period filtering
   - Cache responses for performance

### Long-Term Improvements

1. **Enhanced Data Collection**:
   - Store analytics data in database
   - Cache OP3 responses
   - Merge historical and new data automatically

2. **Better Data Aggregation**:
   - Episode-level time-windowed stats
   - Geographic and app breakdowns
   - Time-series charts
   - Export to CSV

3. **Tier Gating Implementation**:
   - Implement tier-based data access
   - Show upgrade prompts for restricted data
   - Cache tier checks for performance

---

## Files Modified

1. `backend/api/routers/analytics.py` - Merge historical data with OP3 data
2. `backend/api/routers/public.py` - Create public analytics endpoint
3. `backend/api/services/op3_analytics.py` - OP3 API client
4. `backend/api/services/op3_historical_data.py` - Historical data parser

---

## Testing

### Test Cases

1. **Cinema IRL Historical Data Merge**:
   - Verify historical data is merged with new OP3 data
   - Verify all-time downloads = historical + OP3
   - Verify top episodes include both historical and OP3 episodes

2. **Public Analytics Endpoint**:
   - Test with podcast < 7 days (should only show all-time)
   - Test with podcast < 30 days (should show 7d and all-time)
   - Test with podcast < 365 days (should show 7d, 30d, and all-time)
   - Test with podcast >= 365 days (should show 7d, 30d, 365d, and all-time)

3. **Tier Gating**:
   - Test free tier (should return limited data)
   - Test paid tier (should return full data)
   - Test upgrade prompts (should show for restricted data)

---

## Conclusion

OP3 provides limited data compared to traditional analytics platforms, but it's sufficient for basic podcast analytics. The main limitations are:

1. **All-time data** - Only includes recent episodes, not all episodes
2. **Time-windowed stats per episode** - Not available, only show-level
3. **Geographic/app breakdown** - Not available in current API

However, with historical data merging and smart time period filtering, we can provide a good analytics experience for podcasters.






