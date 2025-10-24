# YouTube Analytics Integration Plan - October 20, 2025

## Problem Statement

**Current Situation**:
- OP3 tracks downloads from podcast apps (Apple Podcasts, Spotify, Overcast, etc.)
- YouTube also reads our RSS feed and creates episodes automatically
- YouTube views/plays are NOT tracked by OP3 (different platform entirely)
- This means our analytics are **incomplete** - missing potentially significant YouTube audience

**User Question**: "Is there any way to track [YouTube] and add it in?"

## YouTube Analytics Integration Options

### Option 1: YouTube Data API (Recommended)

**How it works**:
1. Get YouTube API credentials (OAuth 2.0)
2. User connects their YouTube channel to our platform
3. We query YouTube Data API v3 for video statistics
4. Combine YouTube views with OP3 podcast downloads
5. Display unified analytics dashboard

**YouTube Data API Endpoints**:
- `/videos` - Get view count, likes, comments for specific videos
- `/channels` - Get channel-level statistics
- `/search` - Find videos matching RSS feed episode GUIDs

**Pros**:
- ✅ Official API, accurate data
- ✅ Can track views, watch time, engagement (likes/comments)
- ✅ Free tier: 10,000 quota units/day (plenty for our use case)
- ✅ Can match episodes by title/description
- ✅ Historical data available

**Cons**:
- ❌ Requires user to connect YouTube channel (OAuth flow)
- ❌ Need to match RSS episodes to YouTube videos (fuzzy matching)
- ❌ Quota limits (though generous for our scale)

**Implementation Complexity**: Medium

### Option 2: YouTube RSS Feed Parsing (Quick & Dirty)

**How it works**:
1. YouTube channels have public RSS feeds: `https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}`
2. Parse this feed to get video IDs
3. Use YouTube oEmbed API (no auth required) to get basic stats
4. Add to our analytics

**Pros**:
- ✅ No OAuth required
- ✅ Simple to implement
- ✅ No API quotas

**Cons**:
- ❌ Limited data (title, publish date, but no view counts in RSS)
- ❌ oEmbed doesn't provide view counts either
- ❌ Would still need Data API for actual stats

**Implementation Complexity**: Low (but limited value)

### Option 3: Manual Entry (Temporary Workaround)

**How it works**:
1. Add a "YouTube Stats" field to episodes
2. User manually enters view counts from YouTube Studio
3. We add these to analytics totals

**Pros**:
- ✅ Zero API work
- ✅ User controls data
- ✅ Can start immediately

**Cons**:
- ❌ Manual work for users
- ❌ Not real-time
- ❌ Easy to forget/skip

**Implementation Complexity**: Trivial

## Recommended Implementation: YouTube Data API

### Phase 1: YouTube OAuth Connection

**Files to create/modify**:
1. `backend/api/models/podcast.py` - Add YouTube channel fields
2. `backend/api/routers/youtube_oauth.py` - OAuth flow
3. `frontend/src/components/dashboard/YouTubeConnect.jsx` - Connect button

**Database schema addition**:
```python
class Podcast(SQLModel, table=True):
    # ... existing fields ...
    youtube_channel_id: Optional[str] = None
    youtube_channel_name: Optional[str] = None
    youtube_access_token: Optional[str] = None  # Encrypted
    youtube_refresh_token: Optional[str] = None  # Encrypted
    youtube_token_expires_at: Optional[datetime] = None
    youtube_enabled: bool = Field(default=False)
```

### Phase 2: YouTube Video Matching

**Matching strategies** (in order of preference):
1. **GUID matching** - Store YouTube video ID in episode GUID
2. **Title matching** - Fuzzy match episode title to video title (80%+ similarity)
3. **Date matching** - Match by publish date (within 24 hours)
4. **Manual mapping** - User can manually link episodes to videos

**Implementation**:
```python
# backend/api/services/youtube_analytics.py

async def match_episode_to_youtube_video(episode, youtube_videos):
    # Try GUID match first
    if episode.original_guid and episode.original_guid.startswith("yt:video:"):
        video_id = episode.original_guid.replace("yt:video:", "")
        return find_video_by_id(youtube_videos, video_id)
    
    # Try title fuzzy match
    from fuzzywuzzy import fuzz
    best_match = None
    best_score = 0
    
    for video in youtube_videos:
        score = fuzz.ratio(episode.title.lower(), video['title'].lower())
        if score > best_score and score >= 80:
            best_match = video
            best_score = score
    
    return best_match
```

### Phase 3: Unified Analytics Display

**Dashboard changes**:
```jsx
// Downloads Last 7 Days: 123 (OP3) + 456 (YouTube) = 579 total

{
  "downloads_7d": 123,           // OP3 podcast downloads
  "youtube_views_7d": 456,       // YouTube views
  "total_plays_7d": 579,         // Combined
  
  "top_episodes": [
    {
      "title": "Episode 42",
      "downloads_all_time": 1234,     // OP3
      "youtube_views_all_time": 5678,  // YouTube
      "total_plays_all_time": 6912     // Combined
    }
  ]
}
```

**Display strategy**:
- Show combined totals by default
- Allow toggle to see OP3 vs YouTube breakdown
- Color code: Blue for OP3, Red for YouTube

### Phase 4: YouTube-Specific Insights

**Additional YouTube metrics** (that podcast analytics don't have):
- Average view duration (how far people watch)
- Traffic sources (YouTube search, suggested videos, external)
- Demographics (age, gender, geography from YouTube)
- Engagement (likes, comments, shares)

## Zero Downloads Issue - Root Cause Analysis

**Why are downloads showing as 0?**

Possible reasons:
1. **OP3 hasn't registered your feed yet** - 404 when looking up show UUID
2. **No one has downloaded via podcast apps yet** - YouTube views don't count
3. **RSS feed URL mismatch** - OP3 sees different URL than what we're querying
4. **OP3 prefix not applied** - RSS feed missing `op3.dev/e/` wrapper

**Debug checklist**:
```python
# Check backend logs for:
logger.info(f"OP3: Looking up show UUID for feed: {feed_url}")
# → What RSS URL is being used?

logger.warning(f"OP3: Feed URL not registered with OP3 yet")
# → If you see this, OP3 doesn't know your feed

logger.info(f"OP3: Found show UUID: {show_uuid}")
# → If you see this, feed is registered, check episode counts
```

## Immediate Action Items

### For Analytics Accuracy:
1. **Check backend logs** - Look for OP3 registration messages
2. **Verify RSS feed** - View source of your RSS feed, confirm OP3 prefix exists on enclosure URLs
3. **Wait 24-48 hours** - OP3 updates daily, might need time to register

### For YouTube Integration:
1. **Quick win**: Add manual YouTube view count field to episodes (1 hour)
2. **Full solution**: Implement YouTube Data API integration (1-2 days)

## Code Example: Manual YouTube Views (Quick Win)

**Database migration**:
```python
# Add to Episode model
youtube_video_id: Optional[str] = None
youtube_views: Optional[int] = None
youtube_views_updated_at: Optional[datetime] = None
```

**Dashboard endpoint update**:
```python
# In /dashboard/stats response:
"downloads_7d": op3_downloads_7d,
"youtube_views_7d": manual_youtube_views_7d,  # Sum from episodes
"total_plays_7d": op3_downloads_7d + manual_youtube_views_7d,
```

**Frontend UI**:
```jsx
<div className="p-3 rounded border bg-white flex flex-col gap-1">
  <span className="text-[11px] tracking-wide text-gray-500">Total Plays Last 7 Days</span>
  <span className="text-lg font-semibold">{stats.total_plays_7d?.toLocaleString()}</span>
  <div className="text-[9px] text-gray-400 flex gap-2">
    <span>Podcasts: {stats.downloads_7d}</span>
    <span>YouTube: {stats.youtube_views_7d}</span>
  </div>
</div>
```

## Next Steps

**Immediate** (to understand current situation):
1. Check production logs for OP3 registration status
2. Verify RSS feed has OP3 prefixes
3. Check if any downloads actually exist in OP3 dashboard: `https://op3.dev/show/{your-feed-url-base64}`

**Short-term** (if you want YouTube tracking now):
1. Add manual YouTube fields to Episode model
2. Allow users to paste YouTube video URLs when creating episodes
3. Display combined totals on dashboard

**Long-term** (full automation):
1. Implement YouTube OAuth
2. Build episode → video matching logic
3. Fetch YouTube stats automatically every 3 hours (same as OP3 cache)
4. Display unified analytics with platform breakdown

## Resources

- YouTube Data API: https://developers.google.com/youtube/v3
- OP3 Stats Page: https://op3.dev/show/{feed-url-base64}
- YouTube API Quotas: https://developers.google.com/youtube/v3/getting-started#quota

---

**Recommendation**: Start with manual YouTube views field (1 hour work), then build full YouTube API integration if YouTube is a significant portion of your audience.

*Analysis completed: October 20, 2025*
