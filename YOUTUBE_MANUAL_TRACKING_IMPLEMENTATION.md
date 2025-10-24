# Quick YouTube Tracking Implementation - October 20, 2025

## Problem
OP3 shows 0 downloads because:
1. Downloads only track podcast apps, not YouTube
2. YouTube is a significant distribution channel that's completely invisible in current analytics

## Quick Solution: Manual YouTube View Tracking

This is a **1-2 hour implementation** that allows manual YouTube data entry while we build full YouTube API integration.

## Database Migration

### Add to Episode Model
```python
# backend/api/models/podcast.py

class Episode(SQLModel, table=True):
    # ... existing fields ...
    
    # YouTube integration fields
    youtube_video_id: Optional[str] = Field(default=None, nullable=True)
    youtube_video_url: Optional[str] = Field(default=None, nullable=True)
    youtube_views: Optional[int] = Field(default=None, nullable=True)
    youtube_views_updated_at: Optional[datetime] = Field(default=None, nullable=True)
```

### Migration Script
```python
# backend/migrations/XXX_add_youtube_fields.py

def run_migration(session: Session):
    """Add YouTube tracking fields to Episode table."""
    from sqlalchemy import text
    
    # Add columns (if they don't exist)
    columns_to_add = [
        "ALTER TABLE episode ADD COLUMN IF NOT EXISTS youtube_video_id VARCHAR(50)",
        "ALTER TABLE episode ADD COLUMN IF NOT EXISTS youtube_video_url VARCHAR(500)",
        "ALTER TABLE episode ADD COLUMN IF NOT EXISTS youtube_views INTEGER",
        "ALTER TABLE episode ADD COLUMN IF NOT EXISTS youtube_views_updated_at TIMESTAMP",
    ]
    
    for sql in columns_to_add:
        session.execute(text(sql))
    
    session.commit()
    print("✅ YouTube tracking fields added to Episode table")
```

## Backend API Endpoints

### Update Episode Endpoint
```python
# backend/api/routers/episodes/edit.py

from pydantic import BaseModel, HttpUrl

class YouTubeDataUpdate(BaseModel):
    youtube_video_url: Optional[str] = None
    youtube_views: Optional[int] = None

@router.patch("/{episode_id}/youtube")
def update_episode_youtube_data(
    episode_id: UUID,
    youtube_data: YouTubeDataUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update YouTube-specific data for an episode."""
    episode = session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    # Verify ownership
    podcast = session.get(Podcast, episode.podcast_id)
    if podcast.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Extract video ID from URL if provided
    if youtube_data.youtube_video_url:
        video_id = extract_youtube_video_id(youtube_data.youtube_video_url)
        episode.youtube_video_id = video_id
        episode.youtube_video_url = youtube_data.youtube_video_url
    
    if youtube_data.youtube_views is not None:
        episode.youtube_views = youtube_data.youtube_views
        episode.youtube_views_updated_at = datetime.utcnow()
    
    session.add(episode)
    session.commit()
    session.refresh(episode)
    
    return {
        "episode_id": str(episode.id),
        "youtube_video_id": episode.youtube_video_id,
        "youtube_views": episode.youtube_views,
        "updated_at": episode.youtube_views_updated_at.isoformat() if episode.youtube_views_updated_at else None,
    }

def extract_youtube_video_id(url: str) -> Optional[str]:
    """Extract video ID from YouTube URL."""
    import re
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/)([^&\?/]+)',
        r'youtube\.com/embed/([^&\?/]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None
```

### Enhanced Dashboard Stats
```python
# backend/api/routers/dashboard.py

def _compute_youtube_stats(session: Session, user_id) -> dict:
    """Compute YouTube view totals from episodes."""
    from sqlalchemy import func
    from datetime import datetime, timedelta
    
    # Total YouTube views (all episodes)
    total_youtube = session.exec(
        select(func.sum(Episode.youtube_views))
        .where(Episode.user_id == user_id)
        .where(Episode.youtube_views.is_not(None))
    ).one() or 0
    
    # Recent YouTube views (last 30 days)
    # Note: This is imperfect since we don't track view dates, just total views
    # For accurate time-based stats, need YouTube Data API
    since = datetime.utcnow() - timedelta(days=30)
    recent_youtube = session.exec(
        select(func.sum(Episode.youtube_views))
        .where(Episode.user_id == user_id)
        .where(Episode.youtube_views.is_not(None))
        .where(Episode.publish_at >= since)
    ).one() or 0
    
    return {
        "youtube_views_total": int(total_youtube),
        "youtube_views_30d": int(recent_youtube),
    }

# In dashboard_stats() function:
youtube_stats = _compute_youtube_stats(session, current_user.id)

return {
    # ... existing fields ...
    "youtube_views_total": youtube_stats["youtube_views_total"],
    "youtube_views_30d": youtube_stats["youtube_views_30d"],
    "total_plays_30d": (op3_downloads_30d or 0) + youtube_stats["youtube_views_30d"],
    "total_plays_all_time": (op3_downloads_all_time or 0) + youtube_stats["youtube_views_total"],
}
```

## Frontend UI Components

### Episode Edit Form - YouTube Section
```jsx
// frontend/src/components/dashboard/EpisodeHistory.jsx

function YouTubeDataSection({ episode, onUpdate }) {
  const [youtubeUrl, setYoutubeUrl] = useState(episode.youtube_video_url || '');
  const [youtubeViews, setYoutubeViews] = useState(episode.youtube_views || '');
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    try {
      await api.patch(`/api/episodes/${episode.id}/youtube`, {
        youtube_video_url: youtubeUrl || null,
        youtube_views: youtubeViews ? parseInt(youtubeViews) : null,
      });
      toast({ title: "YouTube data updated" });
      onUpdate();
    } catch (err) {
      toast({ title: "Failed to update YouTube data", variant: "destructive" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="border rounded-lg p-4 bg-red-50">
      <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
        <svg className="w-5 h-5 text-red-600" fill="currentColor" viewBox="0 0 24 24">
          <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
        </svg>
        YouTube Data (Optional)
      </h4>
      <div className="space-y-3">
        <div>
          <label className="text-xs text-gray-600 block mb-1">YouTube Video URL</label>
          <input
            type="url"
            value={youtubeUrl}
            onChange={(e) => setYoutubeUrl(e.target.value)}
            placeholder="https://youtube.com/watch?v=..."
            className="w-full px-3 py-2 border rounded text-sm"
          />
        </div>
        <div>
          <label className="text-xs text-gray-600 block mb-1">YouTube Views</label>
          <input
            type="number"
            value={youtubeViews}
            onChange={(e) => setYoutubeViews(e.target.value)}
            placeholder="0"
            className="w-full px-3 py-2 border rounded text-sm"
          />
          <p className="text-[10px] text-gray-500 mt-1">
            Get this from YouTube Studio → Content → [Video] → Analytics
          </p>
        </div>
        <Button onClick={handleSave} disabled={saving} size="sm">
          {saving ? "Saving..." : "Save YouTube Data"}
        </Button>
      </div>
    </div>
  );
}
```

### Enhanced Dashboard Stats Display
```jsx
// frontend/src/components/dashboard.jsx

{/* Combined Stats Cards */}
<div className="grid md:grid-cols-2 gap-3">
  <div className="p-3 rounded border bg-white flex flex-col gap-1">
    <span className="text-[11px] tracking-wide text-gray-500">Total Plays Last 30 Days</span>
    <span className="text-lg font-semibold">{(stats.total_plays_30d || 0).toLocaleString()}</span>
    {(stats.downloads_30d > 0 || stats.youtube_views_30d > 0) && (
      <div className="flex gap-2 text-[9px] text-gray-400">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
          Podcasts: {(stats.downloads_30d || 0).toLocaleString()}
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 bg-red-500 rounded-full"></span>
          YouTube: {(stats.youtube_views_30d || 0).toLocaleString()}
        </span>
      </div>
    )}
  </div>
  
  <div className="p-3 rounded border bg-white flex flex-col gap-1">
    <span className="text-[11px] tracking-wide text-gray-500">Total Plays All-Time</span>
    <span className="text-lg font-semibold">{(stats.total_plays_all_time || 0).toLocaleString()}</span>
    {(stats.downloads_all_time > 0 || stats.youtube_views_total > 0) && (
      <div className="flex gap-2 text-[9px] text-gray-400">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
          Podcasts: {(stats.downloads_all_time || 0).toLocaleString()}
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 bg-red-500 rounded-full"></span>
          YouTube: {(stats.youtube_views_total || 0).toLocaleString()}
        </span>
      </div>
    )}
  </div>
</div>
```

## Implementation Checklist

### Backend (1 hour)
- [ ] Add migration script for YouTube fields
- [ ] Add `PATCH /api/episodes/{id}/youtube` endpoint
- [ ] Update dashboard stats to include YouTube totals
- [ ] Test endpoint with manual data entry

### Frontend (1 hour)
- [ ] Add YouTube section to episode edit modal
- [ ] Update dashboard to show combined podcast + YouTube totals
- [ ] Add color-coded breakdown (blue = podcast, red = YouTube)
- [ ] Test with sample data

### Testing
- [ ] Create test episode with YouTube URL
- [ ] Enter manual view count
- [ ] Verify dashboard shows combined total
- [ ] Verify breakdown shows correct split

## Future Enhancement: YouTube API

Once this manual tracking is working, we can upgrade to automatic YouTube API fetching:
1. Connect YouTube channel via OAuth
2. Automatically fetch view counts every 3 hours
3. No manual data entry needed

But for now, manual entry gets you accurate total plays immediately!

---

**Time estimate**: 2 hours total  
**Value**: Immediately see complete picture of audience across platforms

*Implementation guide: October 20, 2025*
