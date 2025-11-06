"""
OP3 Analytics Integration Service

OP3 (Open Podcast Prefix Project) provides a public API to retrieve analytics data.
This service wraps the OP3 API to fetch download statistics for our podcasts.

API Documentation: https://op3.dev/api/docs
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# In-memory cache for OP3 stats to prevent excessive API calls
# Cache structure: {rss_feed_url: {"stats": OP3ShowStats, "cached_at": datetime}}
_op3_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_HOURS = 3  # Cache OP3 stats for 3 hours

# Lock to prevent concurrent fetches for the same URL
_fetch_locks: Dict[str, asyncio.Lock] = {}
_locks_lock = asyncio.Lock()  # Lock for the locks dict itself


class OP3DownloadStats(BaseModel):
    """Download statistics for a time period."""
    total_downloads: int
    unique_listeners: Optional[int] = None
    date: Optional[str] = None


class OP3EpisodeStats(BaseModel):
    """Statistics for a single episode."""
    episode_url: str
    title: Optional[str] = None
    downloads_24h: int = 0
    downloads_7d: int = 0
    downloads_30d: int = 0
    downloads_total: int = 0


class OP3ShowStats(BaseModel):
    """Statistics for an entire podcast show."""
    show_url: str
    show_title: Optional[str] = None
    total_downloads: int = 0
    downloads_7d: int = 0
    downloads_30d: int = 0
    downloads_365d: int = 0
    downloads_all_time: int = 0
    weekly_downloads: List[int] = []  # Last 4 weeks
    downloads_trend: List[Dict[str, Any]] = []
    top_countries: List[Dict[str, Any]] = []
    top_apps: List[Dict[str, Any]] = []
    top_episodes: List[Dict[str, Any]] = []  # Top 3-5 episodes


class OP3Analytics:
    """Client for OP3 Analytics API."""
    
    BASE_URL = "https://analytics.podcastplusplus.com/api/1"
    # Self-hosted OP3 instance with admin token
    PREVIEW_TOKEN = "ZTY4NDZjOWMtNWE4Ny00NzIxLWFmOGQtYWM5Y2QxNjUzY2Y1"
    
    def __init__(self, timeout: int = 30, api_token: Optional[str] = None):
        self.timeout = timeout
        self.api_token = api_token or self.PREVIEW_TOKEN
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
    
    async def get_show_uuid_from_feed_url(self, feed_url: str) -> Optional[str]:
        """
        Get the OP3 show UUID for a given podcast feed URL.
        
        Args:
            feed_url: The RSS feed URL of the podcast
        
        Returns:
            Show UUID if found, None otherwise
        """
        import base64
        
        # Convert feed URL to urlsafe base64
        feed_url_b64 = base64.urlsafe_b64encode(feed_url.encode()).decode().rstrip('=')
        
        url = f"{self.BASE_URL}/shows/{feed_url_b64}"
        params = {"token": self.api_token}
        
        logger.info(f"OP3: Looking up show UUID for feed: {feed_url}")
        logger.debug(f"OP3: Base64 encoded: {feed_url_b64}")
        
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            show_uuid = data.get("showUuid")
            logger.info(f"OP3: Found show UUID: {show_uuid}")
            return show_uuid
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"OP3: Feed URL not registered with OP3 yet: {feed_url}")
                logger.info(f"OP3: This is normal for new podcasts. Downloads will appear after listeners discover your show via podcast apps.")
                return None
            logger.error(f"OP3 API error getting show UUID: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to get show UUID from OP3: {e}")
            return None
    
    async def get_show_downloads(
        self,
        show_url: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> OP3ShowStats:
        """
        Get comprehensive download statistics for a podcast show using OP3's APIs.
        
        Fetches:
        1. Monthly/weekly download counts from show-download-counts
        2. Top episodes from episode-download-counts (includes 1d/3d/7d/30d/all-time)
        
        Args:
            show_url: The RSS feed URL of the podcast show
            start_date: Ignored (OP3 uses fixed windows)
            end_date: Ignored (OP3 uses fixed windows)
        
        Returns:
            OP3ShowStats with comprehensive download data across all time periods
        """
        # Step 1: Get the show UUID from the feed URL
        show_uuid = await self.get_show_uuid_from_feed_url(show_url)
        
        if not show_uuid:
            logger.warning(f"OP3: Could not get show UUID for {show_url}")
            return OP3ShowStats(show_url=show_url)
        
        # Step 2: Fetch show-level stats (monthly/weekly counts)
        show_stats_url = f"{self.BASE_URL}/queries/show-download-counts"
        show_params = {
            "showUuid": show_uuid,
            "token": self.api_token,
        }
        
        # Step 3: Fetch episode-level stats (includes all time periods + top episodes)
        episode_stats_url = f"{self.BASE_URL}/queries/episode-download-counts"
        episode_params = {
            "showUuid": show_uuid,
            "token": self.api_token,
        }
        
        try:
            # Fetch both in parallel
            import asyncio
            results = await asyncio.gather(
                self.client.get(show_stats_url, params=show_params),
                self.client.get(episode_stats_url, params=episode_params),
                return_exceptions=True
            )
            
            show_resp = results[0]
            episode_resp = results[1]
            
            # Process show-level stats
            monthly_downloads = 0
            weekly_downloads_list = []
            
            if isinstance(show_resp, httpx.Response):
                try:
                    show_resp.raise_for_status()
                    show_data = show_resp.json()
                    show_info = show_data.get("showDownloadCounts", {}).get(show_uuid, {})
                    
                    # Log COMPLETE show-level JSON so user can verify exact field names
                    import json
                    logger.info(f"OP3: ===== COMPLETE SHOW-LEVEL JSON =====")
                    logger.info(f"OP3: {json.dumps(show_info, indent=2)}")
                    logger.info(f"OP3: ===== END SHOW JSON =====")
                    
                    monthly_downloads = show_info.get("monthlyDownloads", 0)
                    weekly_downloads_list = show_info.get("weeklyDownloads", [])
                    
                    # Calculate 7-day downloads from weekly data (last 7 days)
                    # weeklyDownloads is an array of daily download counts
                    downloads_7d = sum(weekly_downloads_list[-7:]) if weekly_downloads_list else 0
                    
                    # Calculate 365-day downloads if weekly data provides it (sum all if >365 days)
                    # If weeklyDownloads has more than 365 items, sum last 365 days
                    if len(weekly_downloads_list) >= 365:
                        downloads_365d = sum(weekly_downloads_list[-365:])
                    elif len(weekly_downloads_list) > 30:
                        # Use all available data as proxy for 365d if we have more than 30d
                        downloads_365d = sum(weekly_downloads_list)
                    else:
                        downloads_365d = 0
                    
                    # OP3 doesn't provide all-time at show level - need to use episode aggregation
                    # But episode endpoint only returns recent episodes, so all-time is unreliable
                    # Best we can do is use the longest available window as proxy
                    if len(weekly_downloads_list) > 0:
                        # Sum all available weekly data as best proxy for all-time
                        downloads_all_time_proxy = sum(weekly_downloads_list)
                    else:
                        downloads_all_time_proxy = 0
                    
                    logger.info(f"OP3: FIELD USAGE:")
                    logger.info(f"OP3:   - monthlyDownloads = {monthly_downloads} (used for 30d)")
                    logger.info(f"OP3:   - weeklyDownloads array length = {len(weekly_downloads_list)}")
                    logger.info(f"OP3:   - weeklyDownloads last 7 items sum = {downloads_7d} (used for 7d)")
                    logger.info(f"OP3:   - weeklyDownloads all items sum = {downloads_all_time_proxy} (used for all-time)")
                    logger.info(f"OP3:   - calculated 365d = {downloads_365d}")
                except Exception as e:
                    logger.error(f"OP3: Error processing show stats: {e}")
            elif isinstance(show_resp, Exception):
                logger.error(f"OP3: Show stats request failed: {show_resp}")
            
            # Process episode-level stats (only provides all-time downloads per episode)
            downloads_365d = 0
            downloads_all_time = 0
            top_episodes = []
            
            if isinstance(episode_resp, httpx.Response):
                try:
                    episode_resp.raise_for_status()
                    episode_data = episode_resp.json()
                    episodes = episode_data.get("episodes", [])
                    
                    logger.info(f"OP3: ===== EPISODE RESPONSE =====")
                    logger.info(f"OP3: Total episodes returned: {len(episodes)}")
                    
                    # Log first 3 episodes completely to understand API response format
                    if episodes:
                        import json
                        logger.info(f"OP3: ===== FIRST 3 EPISODES COMPLETE JSON =====")
                        for i, ep in enumerate(episodes[:3], 1):
                            logger.info(f"OP3: Episode {i}: {json.dumps(ep, indent=2)}")
                        logger.info(f"OP3: ===== END EPISODE JSON =====")
                    
                    # OP3 episode-download-counts ONLY returns all-time downloads per episode
                    # Time-windowed stats (7d, 30d, 365d) come from show-level endpoint only
                    for ep in episodes:
                        # The correct field name is "downloadsAll" not "downloadsAllTime"
                        ep_all_time = ep.get("downloadsAll", 0)
                        if ep_all_time:
                            downloads_all_time += ep_all_time
                    
                    # Since episode endpoint doesn't provide 7d/30d/365d per-episode,
                    # we cannot aggregate those from episodes. They come from show-level stats only.
                    # Set 365d to all-time as fallback since OP3 doesn't provide 365d
                    if downloads_all_time > 0:
                        downloads_365d = downloads_all_time
                    
                    # If 365d wasn't provided by OP3, use all-time as reasonable proxy
                    if downloads_365d == 0 and downloads_all_time > 0:
                        downloads_365d = downloads_all_time
                    
                    logger.info(f"OP3: FIELD USAGE (EPISODES):")
                    logger.info(f"OP3:   - Summing 'downloadsAll' from {len(episodes)} episodes")
                    logger.info(f"OP3:   - Total from episodes = {downloads_all_time} (⚠️ WARNING: only recent episodes returned, NOT true all-time!)")
                    
                    # Get top 3 episodes by all-time downloads
                    sorted_episodes = sorted(
                        episodes,
                        key=lambda x: x.get("downloadsAll", 0),
                        reverse=True
                    )[:3]
                    
                    top_episodes = [
                        {
                            "title": ep.get("title", "Unknown"),
                            "episode_id": ep.get("itemGuid"),  # OP3 uses "itemGuid" not "episodeId"
                            "downloads_1d": 0,  # Not available from OP3 episode-download-counts
                            "downloads_3d": 0,  # Not available
                            "downloads_7d": 0,  # Not available per-episode
                            "downloads_30d": 0,  # Not available per-episode
                            "downloads_all_time": ep.get("downloadsAll", 0),  # Correct field name
                        }
                        for ep in sorted_episodes
                    ]
                    
                    logger.info(f"OP3: Processed {len(episodes)} episodes")
                    logger.info(f"OP3: Aggregated stats - 7d: {downloads_7d}, 365d: {downloads_365d}, all-time: {downloads_all_time}")
                    if top_episodes:
                        logger.info(f"OP3: Top episode '{top_episodes[0]['title']}' has {top_episodes[0]['downloads_all_time']} all-time downloads")
                    logger.info(f"OP3: Returning {len(top_episodes)} top episodes")
                    
                except Exception as e:
                    logger.error(f"OP3: Error processing episode stats: {e}")
            elif isinstance(episode_resp, Exception):
                logger.error(f"OP3: Episode stats request failed: {episode_resp}")
            
            return OP3ShowStats(
                show_url=show_url,
                show_title=None,
                total_downloads=monthly_downloads,  # Legacy field (30d)
                downloads_7d=downloads_7d,
                downloads_30d=monthly_downloads,
                downloads_365d=downloads_365d if downloads_365d > 0 else downloads_all_time,  # Fallback
                downloads_all_time=downloads_all_time,
                weekly_downloads=weekly_downloads_list,
                downloads_trend=[],
                top_countries=[],
                top_apps=[],
                top_episodes=top_episodes,
            )
            
        except Exception as e:
            logger.error(f"Failed to fetch comprehensive OP3 stats: {e}")
            return OP3ShowStats(show_url=show_url)
    
    async def get_episode_downloads(
        self,
        episode_url: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> OP3EpisodeStats:
        """
        Get download statistics for a single episode.
        
        Args:
            episode_url: The enclosure URL of the episode (can be OP3-prefixed or direct)
            start_date: Start date for statistics
            end_date: End date for statistics
        
        Returns:
            OP3EpisodeStats with download data
        """
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()
        
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        
        url = f"{self.BASE_URL}/downloads/episode"
        params = {
            "url": episode_url,
            "start": start_str,
            "end": end_str,
            "format": "json",
        }
        
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Calculate different time period totals
            downloads_24h = self._sum_recent_days(data.get("downloadsByDay", []), days=1)
            downloads_7d = self._sum_recent_days(data.get("downloadsByDay", []), days=7)
            downloads_30d = self._sum_recent_days(data.get("downloadsByDay", []), days=30)
            
            return OP3EpisodeStats(
                episode_url=episode_url,
                title=data.get("episodeTitle"),
                downloads_24h=downloads_24h,
                downloads_7d=downloads_7d,
                downloads_30d=downloads_30d,
                downloads_total=data.get("downloads", 0),
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"OP3: No data found for episode {episode_url}")
                return OP3EpisodeStats(episode_url=episode_url)
            logger.error(f"OP3 API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to fetch OP3 episode stats: {e}")
            raise
    
    def _sum_recent_days(self, downloads_by_day: List[Dict], days: int) -> int:
        """Sum downloads for the most recent N days."""
        if not downloads_by_day:
            return 0
        
        # Sort by date descending
        sorted_data = sorted(
            downloads_by_day,
            key=lambda x: x.get("date", ""),
            reverse=True
        )
        
        # Sum first N days
        return sum(item.get("downloads", 0) for item in sorted_data[:days])
    
    async def get_multiple_episodes(
        self,
        episode_urls: List[str],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[OP3EpisodeStats]:
        """
        Get statistics for multiple episodes in parallel.
        
        Args:
            episode_urls: List of episode enclosure URLs
            start_date: Start date for statistics
            end_date: End date for statistics
        
        Returns:
            List of OP3EpisodeStats
        """
        import asyncio
        
        tasks = [
            self.get_episode_downloads(url, start_date, end_date)
            for url in episode_urls
        ]
        
        return await asyncio.gather(*tasks, return_exceptions=True)


# Convenience functions for sync usage
def get_show_stats_sync(show_url: str, days: int = 30) -> Optional[OP3ShowStats]:
    """
    Synchronous wrapper for getting show stats with caching.
    
    CRITICAL: Uses lock-based caching to prevent concurrent fetches.
    Multiple simultaneous requests will wait for the first fetch to complete
    and then use the cached result. Cache expires after CACHE_TTL_HOURS hours.
    
    Args:
        show_url: RSS feed URL
        days: Number of days to look back (default 30)
    
    Returns:
        OP3ShowStats or None if error
    """
    
    # Check cache first (before acquiring lock)
    now = datetime.utcnow()
    if show_url in _op3_cache:
        cached_entry = _op3_cache[show_url]
        cached_at = cached_entry.get("cached_at")
        if cached_at and (now - cached_at) < timedelta(hours=CACHE_TTL_HOURS):
            cached_stats = cached_entry.get("stats")
            if cached_stats:
                time_since_cache = int((now - cached_at).total_seconds() / 60)
                logger.info(f"OP3: ✅ Cache HIT for {show_url} (cached {time_since_cache} min ago, expires in {int(CACHE_TTL_HOURS * 60 - time_since_cache)} min)")
                return cached_stats
    
    async def _fetch_with_lock():
        """Fetch stats with lock to prevent concurrent requests."""
        # Get or create a lock for this URL
        async with _locks_lock:
            if show_url not in _fetch_locks:
                _fetch_locks[show_url] = asyncio.Lock()
            lock = _fetch_locks[show_url]
        
        # Check cache again (another request might have fetched while we waited for lock)
        if show_url in _op3_cache:
            cached_entry = _op3_cache[show_url]
            cached_at = cached_entry.get("cached_at")
            if cached_at and (datetime.utcnow() - cached_at) < timedelta(hours=CACHE_TTL_HOURS):
                cached_stats = cached_entry.get("stats")
                if cached_stats:
                    logger.info(f"OP3: ✅ Cache HIT after lock wait for {show_url}")
                    return cached_stats
        
        # Acquire lock for this URL (prevents concurrent fetches)
        async with lock:
            # Triple-check cache (another request might have fetched while we waited for lock)
            if show_url in _op3_cache:
                cached_entry = _op3_cache[show_url]
                cached_at = cached_entry.get("cached_at")
                if cached_at and (datetime.utcnow() - cached_at) < timedelta(hours=CACHE_TTL_HOURS):
                    cached_stats = cached_entry.get("stats")
                    if cached_stats:
                        logger.info(f"OP3: ✅ Cache HIT inside lock for {show_url}")
                        return cached_stats
            
            # Cache miss - fetch from OP3
            logger.info(f"OP3: ❌ Cache MISS for {show_url} - fetching from OP3...")
            client = OP3Analytics()
            try:
                start_date = datetime.utcnow() - timedelta(days=days)
                stats = await client.get_show_downloads(show_url, start_date=start_date)
                
                # Cache the result
                if stats:
                    fetch_time = datetime.utcnow()
                    _op3_cache[show_url] = {
                        "stats": stats,
                        "cached_at": fetch_time
                    }
                    logger.info(f"OP3: 💾 Cached fresh stats for {show_url} (valid for {CACHE_TTL_HOURS} hours)")
                
                return stats
            finally:
                await client.close()
    
    try:
        # Try to use existing event loop if one exists, otherwise create new one
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context - create a task and run it
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _fetch_with_lock())
                return future.result(timeout=30)
        except RuntimeError:
            # No running loop - safe to use asyncio.run()
            return asyncio.run(_fetch_with_lock())
    except Exception as e:
        logger.error(f"OP3: ⚠️ Failed to fetch stats: {e}")
        return None


def get_episode_stats_sync(episode_url: str, days: int = 30) -> Optional[OP3EpisodeStats]:
    """
    Synchronous wrapper for getting episode stats.
    
    Args:
        episode_url: Episode enclosure URL
        days: Number of days to look back (default 30)
    
    Returns:
        OP3EpisodeStats or None if error
    """
    import asyncio
    
    async def _fetch():
        client = OP3Analytics()
        try:
            start_date = datetime.utcnow() - timedelta(days=days)
            return await client.get_episode_downloads(episode_url, start_date=start_date)
        finally:
            await client.close()
    
    try:
        return asyncio.run(_fetch())
    except Exception as e:
        logger.error(f"Failed to fetch OP3 stats: {e}")
        return None
