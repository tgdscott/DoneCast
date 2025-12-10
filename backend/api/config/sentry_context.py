"""Sentry context enrichment middleware and utilities.

This module provides functions to add user, request, and business context to all
Sentry error events, so errors can be properly tracked and routed to the right team.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import sentry_sdk
from fastapi import Request

log = logging.getLogger("api.config.sentry_context")


def set_user_context(user_id: str, user_email: Optional[str] = None, user_name: Optional[str] = None) -> None:
    """Set user context for all subsequent Sentry events.
    
    This should be called during authentication to link errors to the user who caused them.
    
    Args:
        user_id: Unique user ID (e.g., database ID)
        user_email: User email address (optional, helps identify users)
        user_name: User name or display name (optional)
    """
    try:
        sentry_sdk.set_user({
            "id": str(user_id),
            "email": user_email or "",
            "username": user_name or "",
        })
    except Exception as e:
        log.debug("[sentry] Failed to set user context: %s", e)


def clear_user_context() -> None:
    """Clear user context (e.g., on logout)."""
    try:
        sentry_sdk.set_user(None)
    except Exception as e:
        log.debug("[sentry] Failed to clear user context: %s", e)


def set_request_context(request: Request) -> None:
    """Set request context from FastAPI request object.
    
    This extracts:
    - Request ID (from X-Request-ID header or generated)
    - User ID (from request.state.user_id if set)
    - HTTP method and path
    - Request headers (sanitized)
    
    Args:
        request: FastAPI request object
    """
    try:
        # Extract request ID from header or state
        request_id = getattr(request.state, "request_id", None)
        if not request_id:
            request_id = request.headers.get("x-request-id", "unknown")
        
        # Extract user ID if authenticated
        user_id = getattr(request.state, "user_id", None)
        
        # Set Sentry context with request information
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("request_id", str(request_id))
            scope.set_context("request", {
                "method": request.method,
                "url": str(request.url),
                "path": request.url.path,
                "query_string": request.url.query,
                "request_id": str(request_id),
                "user_id": str(user_id) if user_id else None,
            })
    except Exception as e:
        log.debug("[sentry] Failed to set request context: %s", e)


def set_business_context(
    podcast_id: Optional[str] = None,
    episode_id: Optional[str] = None,
    action: Optional[str] = None,
    **extra_context: Any
) -> None:
    """Set business context tags for better error grouping and tracking.
    
    This helps identify which podcasts/episodes are affected by errors.
    
    Args:
        podcast_id: Podcast ID if applicable
        episode_id: Episode ID if applicable
        action: What the user was doing (e.g., "upload", "transcribe", "publish")
        **extra_context: Additional key=value pairs to tag (e.g., quality="good")
    """
    try:
        tags = {}
        if podcast_id:
            tags["podcast_id"] = str(podcast_id)
        if episode_id:
            tags["episode_id"] = str(episode_id)
        if action:
            tags["action"] = str(action)
        tags.update(extra_context)
        
        if tags:
            sentry_sdk.set_tags(tags)
    except Exception as e:
        log.debug("[sentry] Failed to set business context: %s", e)


def capture_message(message: str, level: str = "info", **context: Any) -> None:
    """Capture a message with optional context.
    
    Useful for non-error events that should be tracked (e.g., user actions, milestones).
    
    Args:
        message: Message to capture
        level: Severity level (debug, info, warning, error, critical)
        **context: Additional context tags
    """
    try:
        if context:
            sentry_sdk.set_context("message_context", context)
        sentry_sdk.capture_message(message, level=level)
    except Exception as e:
        log.debug("[sentry] Failed to capture message: %s", e)


def add_breadcrumb(
    message: str,
    category: str = "user-action",
    level: str = "info",
    data: Optional[dict] = None
) -> None:
    """Add a breadcrumb to the current Sentry transaction.
    
    Breadcrumbs are helpful events that lead up to an error. They help understand
    what the user was doing when the error occurred.
    
    Args:
        message: Breadcrumb message
        category: Category (e.g., "user-action", "auth", "upload", "process")
        level: Severity level (debug, info, warning, error)
        data: Additional data to include in breadcrumb
    """
    try:
        sentry_sdk.add_breadcrumb(
            message=message,
            category=category,
            level=level,
            data=data or {}
        )
    except Exception as e:
        log.debug("[sentry] Failed to add breadcrumb: %s", e)
