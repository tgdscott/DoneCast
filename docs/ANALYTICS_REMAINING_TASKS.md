# Analytics Implementation - Remaining Tasks

## ✅ COMPLETED

1. ✅ **OP3 prefix in RSS feed** - `backend/api/routers/rss_feed.py`
2. ✅ **OP3 API client** - `backend/api/services/op3_analytics.py`
3. ✅ **Analytics API endpoints** - `backend/api/routers/analytics.py`
4. ✅ **Router registration** - `backend/api/routing.py`
5. ✅ **Analytics dashboard component** - `frontend/src/components/dashboard/PodcastAnalytics.jsx`

---

## 🔧 TODO: Wire Up Analytics to Dashboard

### 1. Add Analytics to Dashboard Navigation (15 min)

**File**: `frontend/src/components/dashboard.jsx`

**Add these imports at the top:**
```javascript
import PodcastAnalytics from './dashboard/PodcastAnalytics';
import { BarChart } from 'lucide-react';
```

**Add analytics case to view switch (around line 500-600):**
```javascript
case 'analytics':
  return (
    <PodcastAnalytics
      podcastId={selectedPodcastId}
      token={token}
      onBack={handleBackToDashboard}
    />
  );
```

**Add state for selected podcast if not already present:**
```javascript
const [selectedPodcastId, setSelectedPodcastId] = useState(null);
```

---

### 2. Add Analytics Button to Podcast Cards (10 min)

**Find the podcast card/list rendering section** (likely in PodcastManager or dashboard main view).

**Add an Analytics button:**
```javascript
<Button 
  variant="outline"
  size="sm"
  onClick={() => {
    setSelectedPodcastId(podcast.id);
    setCurrentView('analytics');
  }}
>
  <BarChart className="w-4 h-4 mr-2" />
  Analytics
</Button>
```

**Or add to existing dropdown menu:**
```javascript
<DropdownMenuItem
  onClick={() => {
    setSelectedPodcastId(podcast.id);
    setCurrentView('analytics');
  }}
>
  <BarChart className="w-4 h-4 mr-2" />
  View Analytics
</DropdownMenuItem>
```

---

### 3. Add Analytics to Episode History (10 min)

**File**: `frontend/src/components/dashboard/EpisodeHistory.jsx`

**Add download count column to episode table:**

```javascript
// Add to the fetch function
async function fetchEpisodeWithStats(episodeId) {
  const api = makeApi(token);
  
  // Fetch episode details
  const episode = await api.get(`/api/episodes/${episodeId}`);
  
  // Fetch download stats (non-blocking)
  try {
    const stats = await api.get(`/api/analytics/episode/${episodeId}/downloads?days=30`);
    episode.downloads_30d = stats.downloads_30d;
    episode.downloads_7d = stats.downloads_7d;
    episode.downloads_24h = stats.downloads_24h;
  } catch (err) {
    // Analytics not available yet
    episode.downloads_30d = 0;
  }
  
  return episode;
}
```

**Add column to table:**
```javascript
<TableColumn>
  <div className="text-sm">
    <div className="font-medium">{episode.downloads_30d || 0}</div>
    <div className="text-xs text-gray-500">downloads (30d)</div>
  </div>
</TableColumn>
```

---

## 🎨 TODO: Polish Analytics UI

### 4. Add Loading States (5 min)

**The component already has loading states**, but you might want to add:

**Skeleton loaders instead of spinner:**
```javascript
{loading && (
  <div className="space-y-4">
    <Skeleton className="h-32 w-full" />
    <Skeleton className="h-64 w-full" />
    <div className="grid grid-cols-2 gap-4">
      <Skeleton className="h-96 w-full" />
      <Skeleton className="h-96 w-full" />
    </div>
  </div>
)}
```

---

### 5. Add Empty State Guidance (5 min)

**Enhance the error/empty state:**

```javascript
if (!showStats || totalDownloads === 0) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>No Analytics Data Yet</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <p className="text-gray-600">
            Analytics data will appear once listeners start downloading your episodes.
          </p>
          
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <h3 className="font-semibold text-blue-900 mb-2">How to get downloads:</h3>
            <ol className="list-decimal list-inside space-y-2 text-sm text-blue-800">
              <li>Submit your RSS feed to podcast directories</li>
              <li>Share episodes on social media</li>
              <li>Wait 24-48 hours for data to appear</li>
            </ol>
          </div>
          
          <div className="flex gap-3">
            <Button onClick={() => setCurrentView('distribution')}>
              Submit to Directories
            </Button>
            <Button variant="outline" onClick={onBack}>
              Back to Dashboard
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
```

---

## 📊 TODO: Add Analytics Widgets to Dashboard

### 6. Dashboard Summary Widget (20 min)

**Add analytics summary to main dashboard** (shows total downloads across all podcasts).

**File**: `frontend/src/components/dashboard.jsx`

**Add widget to dashboard main view:**

```javascript
function AnalyticsSummaryWidget({ podcasts, token }) {
  const [totalDownloads, setTotalDownloads] = useState(0);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    async function fetchTotals() {
      if (!podcasts || podcasts.length === 0) return;
      
      try {
        const api = makeApi(token);
        let total = 0;
        
        // Fetch stats for all podcasts
        for (const podcast of podcasts) {
          try {
            const stats = await api.get(`/api/analytics/podcast/${podcast.id}/downloads?days=30`);
            total += stats.total_downloads || 0;
          } catch (err) {
            // Skip if no data
          }
        }
        
        setTotalDownloads(total);
      } finally {
        setLoading(false);
      }
    }
    
    fetchTotals();
  }, [podcasts, token]);
  
  if (loading) {
    return <Skeleton className="h-32 w-full" />;
  }
  
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-gray-600 flex items-center gap-2">
          <TrendingUp className="w-4 h-4" />
          Total Downloads (30 days)
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-bold">{totalDownloads.toLocaleString()}</div>
        <p className="text-xs text-gray-500 mt-1">Across all your podcasts</p>
      </CardContent>
    </Card>
  );
}

// Add to dashboard main view:
<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
  <AnalyticsSummaryWidget podcasts={podcasts} token={token} />
  {/* Other dashboard widgets */}
</div>
```

---

### 7. Recent Episodes Performance (15 min)

**Add a "Recent Episodes" widget showing download stats:**

```javascript
function RecentEpisodesWidget({ podcastId, token }) {
  const [episodes, setEpisodes] = useState([]);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    async function fetchRecent() {
      try {
        const api = makeApi(token);
        const data = await api.get(`/api/analytics/podcast/${podcastId}/episodes-summary?limit=5`);
        setEpisodes(data.episodes || []);
      } finally {
        setLoading(false);
      }
    }
    
    if (podcastId) fetchRecent();
  }, [podcastId, token]);
  
  if (loading) {
    return <Skeleton className="h-64 w-full" />;
  }
  
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Recent Episodes</span>
          <Button 
            variant="ghost" 
            size="sm"
            onClick={() => setCurrentView('analytics')}
          >
            View All
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {episodes.map((ep) => (
            <div key={ep.episode_id} className="flex items-center justify-between p-2 border rounded hover:bg-gray-50">
              <div className="flex-1 truncate">
                <div className="font-medium text-sm truncate">{ep.title}</div>
                <div className="text-xs text-gray-500">
                  24h: {ep.downloads_24h} · 7d: {ep.downloads_7d}
                </div>
              </div>
              <div className="text-right ml-4">
                <div className="font-bold">{ep.downloads_30d}</div>
                <div className="text-xs text-gray-500">30d</div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
```

---

## 🔒 TODO: Add Authorization Checks

### 8. Secure Analytics Endpoints (15 min)

**File**: `backend/api/routers/analytics.py`

**Currently the endpoints have TODOs for ownership checks. Implement them:**

```python
# Add this helper function at the top of the file
def verify_podcast_ownership(podcast: Podcast, user: User) -> None:
    """Verify user owns the podcast."""
    # Get the podcast owner
    from api.models.user import UserPodcast
    
    # Check if user owns this podcast
    # Option 1: If Podcast has owner_id field
    if hasattr(podcast, 'owner_id'):
        if podcast.owner_id != user.id:
            raise HTTPException(status_code=403, detail="Not authorized to view this podcast's analytics")
    
    # Option 2: If using UserPodcast junction table
    else:
        stmt = select(UserPodcast).where(
            UserPodcast.user_id == user.id,
            UserPodcast.podcast_id == podcast.id
        )
        user_podcast = session.exec(stmt).first()
        if not user_podcast:
            raise HTTPException(status_code=403, detail="Not authorized to view this podcast's analytics")
```

**Update the three endpoints to use it:**

```python
@router.get("/podcast/{podcast_id}/downloads")
async def get_podcast_downloads(...):
    podcast = session.get(Podcast, podcast_id)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    # Add ownership check
    verify_podcast_ownership(podcast, current_user)
    
    # ... rest of the code
```

---

## 🧪 TODO: Add Tests

### 9. Unit Tests for OP3 Client (30 min)

**Create**: `backend/tests/test_op3_analytics.py`

```python
import pytest
from api.services.op3_analytics import OP3Analytics

@pytest.mark.asyncio
async def test_get_show_downloads():
    """Test fetching show-level stats."""
    client = OP3Analytics()
    try:
        stats = await client.get_show_downloads(
            show_url="https://example.com/feed.xml"
        )
        assert stats.show_url == "https://example.com/feed.xml"
        assert stats.total_downloads >= 0
    finally:
        await client.close()

@pytest.mark.asyncio
async def test_get_episode_downloads():
    """Test fetching episode-level stats."""
    client = OP3Analytics()
    try:
        stats = await client.get_episode_downloads(
            episode_url="https://example.com/audio.mp3"
        )
        assert stats.episode_url == "https://example.com/audio.mp3"
        assert stats.downloads_total >= 0
    finally:
        await client.close()

@pytest.mark.asyncio
async def test_get_multiple_episodes():
    """Test parallel fetching."""
    client = OP3Analytics()
    try:
        urls = [
            "https://example.com/ep1.mp3",
            "https://example.com/ep2.mp3"
        ]
        results = await client.get_multiple_episodes(urls)
        assert len(results) == 2
    finally:
        await client.close()
```

---

### 10. Integration Tests for API (30 min)

**Create**: `backend/tests/test_analytics_api.py`

```python
import pytest
from fastapi.testclient import TestClient
from api.app import app

client = TestClient(app)

def test_get_podcast_downloads_unauthorized():
    """Test analytics endpoint requires auth."""
    response = client.get("/api/analytics/podcast/test-id/downloads")
    assert response.status_code == 401

def test_get_podcast_downloads_not_found(auth_headers):
    """Test 404 for non-existent podcast."""
    response = client.get(
        "/api/analytics/podcast/00000000-0000-0000-0000-000000000000/downloads",
        headers=auth_headers
    )
    assert response.status_code == 404

def test_get_podcast_downloads_success(auth_headers, test_podcast):
    """Test successful stats fetch."""
    response = client.get(
        f"/api/analytics/podcast/{test_podcast.id}/downloads?days=30",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "total_downloads" in data
    assert "downloads_by_day" in data
```

---

## 📝 TODO: Add Documentation

### 11. API Documentation (15 min)

**Update**: `backend/api/routers/analytics.py`

**Enhance docstrings with examples:**

```python
@router.get("/podcast/{podcast_id}/downloads")
async def get_podcast_downloads(...):
    """
    Get download statistics for a podcast show from OP3.
    
    This endpoint fetches analytics data from OP3 (Open Podcast Prefix Project),
    which tracks downloads via redirect URLs in your RSS feed.
    
    **Query Parameters:**
    - `days` (int): Number of days to look back (1-365). Default: 30
    
    **Returns:**
    - `total_downloads` (int): Total downloads in the time period
    - `downloads_by_day` (array): Daily download counts with dates
    - `top_countries` (array): Geographic breakdown with country names and counts
    - `top_apps` (array): Podcast app breakdown (e.g., Apple Podcasts, Spotify)
    
    **Example Response:**
    ```json
    {
      "podcast_id": "123e4567-e89b-12d3-a456-426614174000",
      "podcast_name": "My Podcast",
      "rss_url": "https://example.com/feed.xml",
      "period_days": 30,
      "total_downloads": 5432,
      "downloads_by_day": [
        {"date": "2025-10-09", "downloads": 245},
        {"date": "2025-10-08", "downloads": 198}
      ],
      "top_countries": [
        {"country": "United States", "downloads": 3200},
        {"country": "Canada", "downloads": 850}
      ],
      "top_apps": [
        {"app": "Apple Podcasts", "downloads": 2100},
        {"app": "Spotify", "downloads": 1800}
      ]
    }
    ```
    
    **Note:** Data may take 24-48 hours to appear after deploying OP3 prefixes.
    
    **Errors:**
    - `401`: Not authenticated
    - `403`: Not authorized to view this podcast
    - `404`: Podcast not found
    - `500`: OP3 API error
    """
    # ... implementation
```

---

## 🎯 TODO: Error Handling & Edge Cases

### 12. Handle OP3 API Failures Gracefully (10 min)

**Update**: `backend/api/routers/analytics.py`

**Add fallback responses:**

```python
@router.get("/podcast/{podcast_id}/downloads")
async def get_podcast_downloads(...):
    # ... existing code ...
    
    client = OP3Analytics()
    try:
        stats = await client.get_show_downloads(
            show_url=rss_url,
            start_date=start_date,
        )
        return {
            "podcast_id": str(podcast_id),
            "podcast_name": podcast.name,
            "rss_url": rss_url,
            "period_days": days,
            "total_downloads": stats.total_downloads,
            "downloads_by_day": stats.downloads_by_day,
            "top_countries": stats.top_countries,
            "top_apps": stats.top_apps,
            "data_source": "op3",
            "last_updated": datetime.utcnow().isoformat(),
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            # No data yet - return empty stats
            return {
                "podcast_id": str(podcast_id),
                "podcast_name": podcast.name,
                "rss_url": rss_url,
                "period_days": days,
                "total_downloads": 0,
                "downloads_by_day": [],
                "top_countries": [],
                "top_apps": [],
                "data_source": "op3",
                "message": "No analytics data available yet. Data appears 24-48 hours after first downloads.",
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to fetch analytics from OP3")
    except Exception as e:
        logger.error(f"OP3 analytics error: {e}")
        raise HTTPException(status_code=500, detail="Analytics service temporarily unavailable")
    finally:
        await client.close()
```

---

## 📊 TODO: Add Caching

### 13. Cache OP3 Responses (20 min)

**OP3 data doesn't change frequently, so cache it:**

**Install dependency:**
```bash
pip install aiocache
```

**Update**: `backend/api/services/op3_analytics.py`

```python
from aiocache import cached
from aiocache.serializers import JsonSerializer

class OP3Analytics:
    # ... existing code ...
    
    @cached(ttl=3600, key_builder=lambda f, *args, **kwargs: f"op3_show_{kwargs.get('show_url')}", serializer=JsonSerializer())
    async def get_show_downloads(self, show_url: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> OP3ShowStats:
        """Get download statistics for a podcast show (cached for 1 hour)."""
        # ... existing implementation ...
    
    @cached(ttl=1800, key_builder=lambda f, *args, **kwargs: f"op3_episode_{kwargs.get('episode_url')}", serializer=JsonSerializer())
    async def get_episode_downloads(self, episode_url: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> OP3EpisodeStats:
        """Get download statistics for a single episode (cached for 30 min)."""
        # ... existing implementation ...
```

**Add to requirements.txt:**
```
aiocache[redis]
```

---

## ✅ SUMMARY: Analytics TODO Checklist

### Before Deploy:
- [ ] Wire up analytics to dashboard (navigation)
- [ ] Add analytics button to podcast cards
- [ ] Add download counts to episode history (optional)
- [ ] Add authorization checks (podcast ownership)
- [ ] Enhance error handling
- [ ] Add empty state guidance

### After Deploy (when you have data):
- [ ] Test analytics dashboard with real data
- [ ] Add dashboard summary widget
- [ ] Add recent episodes widget
- [ ] Write unit tests
- [ ] Add API documentation examples
- [ ] Implement caching (performance)

### Nice-to-Have:
- [ ] Export analytics to CSV
- [ ] Email reports (weekly digest)
- [ ] Download goals/milestones notifications
- [ ] Compare episodes side-by-side
- [ ] Analytics API rate limiting

---

## 🚀 NEXT: What To Implement Now

I recommend doing items **1-6** before deploy (wire up UI + auth + error handling). That's about **1-2 hours of work** and will give you a complete, production-ready analytics feature.

Items **7-13** can be done after deploy as polish/optimization.

**Want me to start with any of these?** I can implement the dashboard wiring (#1-2) right now!
