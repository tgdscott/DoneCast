# Analytics Investigation Summary

## Investigation Complete ✅

This document summarizes the investigation into analytics issues and the fixes implemented.

---

## Issues Investigated

### 1. Analytics Ping Mechanism ✅

**Question**: What makes analytics show up as a ping when someone plays an episode?

**Answer**: 
- **OP3 (Open Podcast Prefix Project)** acts as a redirect proxy
- Audio URLs in RSS feed are prefixed with `https://analytics.podcastplusplus.com/e/`
- When a podcast app downloads an episode, it requests the OP3-prefixed URL first
- OP3 logs the request (IP hash, user-agent, timestamp, country) - this is the "ping"
- OP3 then redirects (HTTP 302) to the actual audio URL
- The podcast app downloads from the actual storage (GCS/R2)

**Code Location**: 
- `backend/api/routers/rss_feed.py` lines 232-240 (OP3 prefix addition)
- `op3-self-hosted/worker/routes/redirect_episode.ts` (OP3 redirect logic)

**Files**: `docs/ANALYTICS_INVESTIGATION_REPORT.md` section 1

---

### 2. Cinema IRL Historical Data Merge ✅

**Problem**: Historical TSV data was NOT being merged with new OP3 data. It was only used as a fallback when OP3 returned no data.

**Solution**: 
- **Fixed**: Historical data is now merged with new OP3 data
- **All-time downloads**: Historical all-time + OP3 all-time (additive, not overlapping)
- **Time-windowed stats** (7d, 30d, 365d): Use OP3 data only (historical is old)
- **Top episodes**: Combine historical and OP3 episodes, sort by all-time downloads
- **Only for Cinema IRL**: Merge only happens if podcast name/slug contains "cinema" and "irl"

**Code Location**: `backend/api/routers/analytics.py` lines 112-266

**Files**: `docs/ANALYTICS_INVESTIGATION_REPORT.md` section 2

---

### 3. Front Page Analytics Display ✅

**Problem**: Front page did NOT display analytics data. No public endpoint existed.

**Solution**: 
- **Created**: Public analytics endpoint `/api/public/podcast/{podcast_id}/analytics`
- **Smart time period filtering** based on podcast age:
  - **7d**: if podcast exists >= 7 days
  - **30d**: if podcast exists >= 30 days
  - **365d**: if podcast exists >= 365 days
  - **All-time**: always shown
  - **Don't repeat**: if podcast is < 30 days, only show 7d and all-time
- **No authentication required**: Public access for front page display
- **Merges historical data**: Includes Cinema IRL historical data in all-time

**Code Location**: `backend/api/routers/public.py` lines 120-248

**Files**: `docs/ANALYTICS_INVESTIGATION_REPORT.md` section 3

---

### 4. All-Time Data from Newest Episodes ✅

**Problem**: OP3 API only returns recent episodes (last 50-100), not all episodes. All-time downloads were underestimated.

**Solution**: 
- **Merged historical data**: For Cinema IRL, historical all-time + OP3 all-time
- **Documented limitation**: OP3 only returns recent episodes, not all episodes
- **Used show-level data**: Use show-level all-time data (sum of `weeklyDownloads`) as fallback
- **Warning in code**: Logs warning that all-time is "only recent episodes returned, NOT true all-time!"

**Code Location**: 
- `backend/api/services/op3_analytics.py` lines 248-268
- `backend/api/routers/analytics.py` lines 112-266

**Files**: `docs/ANALYTICS_INVESTIGATION_REPORT.md` section 4

---

### 5. Data Availability for Tier Gating ✅

**Question**: What data can be pulled from OP3 for tier gating?

**Answer**: 
- **Show-level stats**: 7d, 30d, 365d, all-time (from `show-download-counts`)
- **Episode-level stats**: All-time per episode (from `episode-download-counts`, limited to recent episodes)
- **Top episodes**: Top episodes by all-time downloads
- **Limitations**: 
  - No time-windowed stats per episode (7d, 30d, 365d not available)
  - No geographic/app breakdown (not yet implemented)
  - No time-series data (not yet implemented)
  - Only recent episodes returned (last 50-100)

**Tier Gating Strategy**:
- **Free Tier**: Basic stats (7d, 30d, all-time), top 3 episodes
- **Paid Tier (Basic)**: Basic stats, top 10 episodes
- **Paid Tier (Advanced)**: Advanced stats (7d, 30d, 365d, all-time), top 10 episodes, geographic/app breakdown
- **Paid Tier (Full)**: Full stats, episode-level stats, time-series data, export to CSV

**Code Location**: 
- `backend/api/routers/analytics.py` lines 25-46 (tier gating)
- `backend/api/billing/plans.py` (tier checks)

**Files**: `docs/ANALYTICS_DATA_AVAILABILITY.md`

---

## Files Modified

1. **`backend/api/routers/analytics.py`**:
   - Fixed Cinema IRL historical data merge
   - Merged historical all-time + OP3 all-time
   - Merged top episodes from historical and OP3 data
   - Added logging for merge process

2. **`backend/api/routers/public.py`**:
   - Created public analytics endpoint
   - Implemented smart time period filtering based on podcast age
   - Added podcast age calculation (days since first episode)
   - Merged historical data for Cinema IRL

3. **`docs/ANALYTICS_INVESTIGATION_REPORT.md`**:
   - Comprehensive investigation report
   - All issues documented with solutions
   - Data flow diagrams
   - Recommendations

4. **`docs/ANALYTICS_DATA_AVAILABILITY.md`**:
   - Data available from OP3
   - Tier gating strategy
   - Data limitations
   - Recommendations

---

## Key Findings

### 1. Analytics Ping Mechanism

**How it works**:
- OP3 prefix in RSS feed audio URLs
- Podcast app requests OP3-prefixed URL
- OP3 logs the request (ping)
- OP3 redirects to actual audio URL
- Podcast app downloads from actual storage

### 2. Historical Data Merge

**Fixed**:
- Historical data now merges with new OP3 data
- All-time = historical all-time + OP3 all-time
- Top episodes = combine historical and OP3 episodes
- Only for Cinema IRL podcast

### 3. Front Page Analytics

**Created**:
- Public analytics endpoint
- Smart time period filtering
- No authentication required
- Merges historical data

### 4. All-Time Data

**Limitation**:
- OP3 only returns recent episodes (last 50-100)
- All-time downloads are underestimated
- Solution: Merge historical data for Cinema IRL

### 5. Data Availability

**Available**:
- Show-level stats: 7d, 30d, 365d, all-time
- Episode-level stats: All-time per episode (recent episodes only)
- Top episodes: Top episodes by all-time downloads

**Not Available**:
- Time-windowed stats per episode (7d, 30d, 365d)
- Geographic/app breakdown (not yet implemented)
- Time-series data (not yet implemented)
- All episodes (only recent episodes returned)

---

## Testing Recommendations

### 1. Cinema IRL Historical Data Merge

**Test Cases**:
- Verify historical data is loaded from TSV
- Verify historical data is merged with OP3 data
- Verify all-time downloads = historical + OP3
- Verify top episodes include both historical and OP3 episodes
- Verify merge only happens for Cinema IRL

### 2. Front Page Analytics Endpoint

**Test Cases**:
- Test with podcast < 7 days (should only show all-time)
- Test with podcast < 30 days (should show 7d and all-time)
- Test with podcast < 365 days (should show 7d, 30d, and all-time)
- Test with podcast >= 365 days (should show 7d, 30d, 365d, and all-time)
- Test with Cinema IRL (should merge historical data)

### 3. All-Time Data

**Test Cases**:
- Verify OP3 returns recent episodes only
- Verify historical data is merged for Cinema IRL
- Verify all-time downloads are correct
- Verify top episodes include both historical and OP3 episodes

### 4. Tier Gating

**Test Cases**:
- Test free tier (should return limited data)
- Test paid tier (should return full data)
- Test upgrade prompts (should show for restricted data)

---

## Next Steps

### Immediate Actions

1. **Test the fixes**:
   - Test Cinema IRL historical data merge
   - Test public analytics endpoint
   - Test smart time period filtering
   - Test tier gating

2. **Deploy the changes**:
   - Deploy backend changes
   - Test in production
   - Monitor logs for errors

3. **Update frontend**:
   - Add analytics section to website builder
   - Display analytics data on front page
   - Add smart time period filtering UI

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

## Conclusion

All issues have been investigated and fixed:

1. ✅ **Analytics ping mechanism**: Documented how OP3 redirects work
2. ✅ **Cinema IRL historical data merge**: Fixed to merge historical data with new OP3 data
3. ✅ **Front page analytics display**: Created public analytics endpoint with smart time period filtering
4. ✅ **All-time data from newest episodes**: Documented limitation and merged historical data
5. ✅ **Data availability for tier gating**: Documented what data can be pulled from OP3

**Status**: All issues resolved ✅

**Next Steps**: Test the fixes and deploy to production

---

## Files Created/Modified

### Created
- `docs/ANALYTICS_INVESTIGATION_REPORT.md` - Comprehensive investigation report
- `docs/ANALYTICS_DATA_AVAILABILITY.md` - Data availability documentation
- `docs/ANALYTICS_INVESTIGATION_SUMMARY.md` - This summary document

### Modified
- `backend/api/routers/analytics.py` - Fixed Cinema IRL historical data merge
- `backend/api/routers/public.py` - Created public analytics endpoint

---

## References

- OP3 API Documentation: https://op3.dev/api/docs
- OP3 Self-Hosted: `op3-self-hosted/worker/`
- Analytics Service: `backend/api/services/op3_analytics.py`
- Historical Data: `backend/api/services/op3_historical_data.py`
- Analytics Router: `backend/api/routers/analytics.py`
- Public Router: `backend/api/routers/public.py`






