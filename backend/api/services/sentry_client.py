"""Sentry API client for fetching and analyzing error events.

This service provides methods to query the Sentry API for error events,
allowing the admin dashboard to display production errors and their context.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Any
import os

import httpx

log = logging.getLogger("api.services.sentry_client")


class SentryAPIClient:
    """Client for querying Sentry API to fetch error events."""
    
    # Sentry URLs
    SENTRY_BASE_URL = "https://sentry.io/api/0"
    
    def __init__(
        self,
        org_slug: Optional[str] = None,
        project_slug: str = "default",
        auth_token: Optional[str] = None,
    ):
        """Initialize Sentry API client.
        
        Args:
            org_slug: Sentry organization slug. If None, reads from SENTRY_ORG_SLUG env var 
                     or defaults to "chainsaw-enterprises"
            project_slug: Sentry project slug (e.g., "default")
            auth_token: Sentry organization auth token. If None, reads from SENTRY_ORG_TOKEN env var.
        """
        self.org_slug = org_slug or os.getenv("SENTRY_ORG_SLUG", "chainsaw-enterprises")
        self.project_slug = project_slug
        self.auth_token = auth_token or os.getenv("SENTRY_ORG_TOKEN")
        
        if not self.auth_token:
            log.warning("[sentry-client] No SENTRY_ORG_TOKEN configured - Sentry API calls will fail")
    
    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for Sentry API requests."""
        return {
            "Authorization": f"Bearer {self.auth_token}",
            "Accept": "application/json",
        }
    
    def _build_url(self, path: str) -> str:
        """Build full Sentry API URL."""
        return f"{self.SENTRY_BASE_URL}/{path}"
    
    async def get_recent_issues(
        self,
        limit: int = 20,
        hours_back: int = 24,
        severity_filter: Optional[str] = None,
        search_query: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Fetch recent issues from Sentry.
        
        Args:
            limit: Maximum number of issues to return (max 100)
            hours_back: How far back to search (default 24 hours)
            severity_filter: Filter by severity level (error, fatal, warning, etc.)
            search_query: Optional search query for filtering issues
        
        Returns:
            List of issue dictionaries with metadata
        """
        if not self.auth_token:
            log.warning("[sentry-client] Cannot fetch issues - SENTRY_ORG_TOKEN not configured")
            return []
        
        # Build query parameters
        params = {
            "limit": min(limit, 100),  # Sentry API max is 100
            "query": "is:unresolved",  # Only show unresolved issues
            "sort": "-firstSeen",  # Most recent first
        }
        
        # Add time range filter
        since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        time_filter = f"firstSeen:[{since.isoformat()} TO *]"
        params["query"] = f"{params['query']} {time_filter}"
        
        # Add severity filter if specified
        if severity_filter:
            valid_severities = ["fatal", "error", "warning", "info", "debug"]
            if severity_filter.lower() in valid_severities:
                params["query"] = f"{params['query']} level:{severity_filter}"
        
        # Add custom search query
        if search_query:
            params["query"] = f"{params['query']} {search_query}"
        
        try:
            url = self._build_url(f"organizations/{self.org_slug}/issues/")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url,
                    headers=self._get_headers(),
                    params=params,
                )
                response.raise_for_status()
                
                issues = response.json()
                log.info(f"[sentry-client] Fetched {len(issues)} recent issues")
                return issues
        
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                log.error("[sentry-client] Unauthorized - invalid SENTRY_ORG_TOKEN")
            elif e.response.status_code == 404:
                log.error(f"[sentry-client] Project not found: {self.org_slug}/{self.project_slug}")
            else:
                log.error(f"[sentry-client] HTTP error {e.response.status_code}: {e.response.text}")
            return []
        
        except Exception as e:
            log.error(f"[sentry-client] Failed to fetch Sentry issues: {e}")
            return []
    
    async def get_issue_details(
        self,
        issue_id: str,
    ) -> Optional[dict[str, Any]]:
        """Fetch detailed information about a specific issue.
        
        Args:
            issue_id: Sentry issue ID
        
        Returns:
            Issue details dictionary or None if not found
        """
        if not self.auth_token:
            log.warning("[sentry-client] Cannot fetch issue - SENTRY_ORG_TOKEN not configured")
            return None
        
        try:
            url = self._build_url(f"organizations/{self.org_slug}/issues/{issue_id}/")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url,
                    headers=self._get_headers(),
                )
                response.raise_for_status()
                return response.json()
        
        except Exception as e:
            log.error(f"[sentry-client] Failed to fetch issue {issue_id}: {e}")
            return None
    
    async def get_issue_events(
        self,
        issue_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Fetch recent events for a specific issue.
        
        Args:
            issue_id: Sentry issue ID
            limit: Maximum number of events to return
        
        Returns:
            List of event dictionaries
        """
        if not self.auth_token:
            log.warning("[sentry-client] Cannot fetch events - SENTRY_ORG_TOKEN not configured")
            return []
        
        try:
            url = self._build_url(f"organizations/{self.org_slug}/issues/{issue_id}/events/")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url,
                    headers=self._get_headers(),
                    params={"limit": min(limit, 100)},
                )
                response.raise_for_status()
                events = response.json()
                log.info(f"[sentry-client] Fetched {len(events)} events for issue {issue_id}")
                return events
        
        except Exception as e:
            log.error(f"[sentry-client] Failed to fetch events for issue {issue_id}: {e}")
            return []
    
    async def get_user_affected_count(
        self,
        issue_id: str,
    ) -> int:
        """Get count of unique users affected by an issue.
        
        Args:
            issue_id: Sentry issue ID
        
        Returns:
            Count of affected users
        """
        details = await self.get_issue_details(issue_id)
        if details and "userCount" in details:
            return details["userCount"]
        return 0


# Singleton instance for use throughout the application
_sentry_client: Optional[SentryAPIClient] = None


def get_sentry_client(
    org_slug: Optional[str] = None,
    project_slug: str = "default",
) -> SentryAPIClient:
    """Get or create Sentry API client singleton.
    
    Args:
        org_slug: Sentry organization slug. If None, uses SENTRY_ORG_SLUG env var
                 or defaults to "chainsaw-enterprises"
        project_slug: Sentry project slug
    
    Returns:
        SentryAPIClient instance
    """
    global _sentry_client
    if _sentry_client is None:
        _sentry_client = SentryAPIClient(org_slug=org_slug, project_slug=project_slug)
    return _sentry_client
