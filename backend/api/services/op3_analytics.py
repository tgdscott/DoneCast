"""
OP3 Analytics Integration Service

OP3 (Open Podcast Prefix Project) provides a public API to retrieve analytics data.
This service wraps the OP3 API to fetch download statistics for our podcasts.

API Documentation: https://op3.dev/api/docs
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


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
    downloads_trend: List[Dict[str, Any]] = []
    top_countries: List[Dict[str, Any]] = []
    top_apps: List[Dict[str, Any]] = []


class OP3Analytics:
    """Client for OP3 Analytics API."""
    
    BASE_URL = "https://op3.dev/api/1"
    # OP3 requires authentication - using preview token for public access
    # To get your own token, visit: https://op3.dev/api/keys
    PREVIEW_TOKEN = "preview07ce"
    
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
        
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("showUuid")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"OP3: Feed URL not registered: {feed_url}")
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
        Get download statistics for a podcast show using OP3's show-download-counts API.
        
        Args:
            show_url: The RSS feed URL of the podcast show
            start_date: Ignored (OP3 API uses fixed 30-day window)
            end_date: Ignored (OP3 API uses fixed 30-day window)
        
        Returns:
            OP3ShowStats with download data
        """
        # Step 1: Get the show UUID from the feed URL
        show_uuid = await self.get_show_uuid_from_feed_url(show_url)
        
        if not show_uuid:
            logger.warning(f"OP3: Could not get show UUID for {show_url}")
            return OP3ShowStats(show_url=show_url, total_downloads=0)
        
        # Step 2: Query the show-download-counts endpoint
        # This gives us monthly downloads (last 30 days) without needing date parameters
        url = f"{self.BASE_URL}/queries/show-download-counts"
        params = {
            "showUuid": show_uuid,
            "token": self.api_token,
        }
        
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Extract show stats from the response
            show_data = data.get("showDownloadCounts", {}).get(show_uuid, {})
            monthly_downloads = show_data.get("monthlyDownloads", 0)
            weekly_downloads = show_data.get("weeklyDownloads", [])
            
            logger.info(f"OP3: Got {monthly_downloads} downloads for show {show_uuid}")
            
            return OP3ShowStats(
                show_url=show_url,
                show_title=None,  # Not included in this endpoint
                total_downloads=monthly_downloads,
                downloads_trend=[],  # Could reconstruct from weekly if needed
                top_countries=[],  # Not included in this endpoint
                top_apps=[],  # Not included in this endpoint
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"OP3: No data found for show UUID {show_uuid}")
                return OP3ShowStats(show_url=show_url, total_downloads=0)
            elif e.response.status_code == 401:
                logger.error(f"OP3 API authentication failed. Check API token. Status: 401 Unauthorized")
                return OP3ShowStats(show_url=show_url, total_downloads=0)
            logger.error(f"OP3 API error: {e}")
            return OP3ShowStats(show_url=show_url, total_downloads=0)
        except Exception as e:
            logger.error(f"Failed to fetch OP3 show stats: {e}")
            return OP3ShowStats(show_url=show_url, total_downloads=0)
    
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
    Synchronous wrapper for getting show stats.
    
    Args:
        show_url: RSS feed URL
        days: Number of days to look back (default 30)
    
    Returns:
        OP3ShowStats or None if error
    """
    import asyncio
    
    async def _fetch():
        client = OP3Analytics()
        try:
            start_date = datetime.utcnow() - timedelta(days=days)
            return await client.get_show_downloads(show_url, start_date=start_date)
        finally:
            await client.close()
    
    try:
        return asyncio.run(_fetch())
    except Exception as e:
        logger.error(f"Failed to fetch OP3 stats: {e}")
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
