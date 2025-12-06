"""
AI client router - dispatches to the correct provider based on AI_PROVIDER env var.
This module provides a unified interface that routes to Gemini, Groq, or other providers.
"""
from __future__ import annotations

import os
import logging
from typing import Any

_log = logging.getLogger(__name__)


def get_provider() -> str:
    """Get the configured AI provider."""
    return (os.getenv("AI_PROVIDER") or "gemini").lower()


def generate(content: str, **kwargs) -> str:
    """Generate text via Gemini for all providers.

    Permanent design decision: all text generation (titles, notes, tags
    fallback, etc.) uses the Gemini client so behavior is consistent and not
    dependent on external provider quirks. We still read AI_PROVIDER for
    observability, but it no longer changes routing.
    """
    provider = get_provider()
    if provider not in ("gemini", "vertex"):
        _log.info("[ai_router] Forcing provider to Gemini (was '%s')", provider)
    from . import client_gemini
    return client_gemini.generate(content, **kwargs)


def generate_json(content: str, **kwargs) -> Any:
    """Generate JSON using the configured AI provider."""
    provider = get_provider()
    
    if provider == "groq":
        # Groq doesn't have native JSON mode, so we'll use the gemini fallback
        from . import client_gemini
        return client_gemini.generate_json(content, **kwargs)
    elif provider in ("gemini", "vertex"):
        from . import client_gemini
        return client_gemini.generate_json(content, **kwargs)
    else:
        from . import client_gemini
        return client_gemini.generate_json(content, **kwargs)


def generate_podcast_cover_image(*args, **kwargs):
    """Generate podcast cover image - always uses Gemini (has image generation)."""
    from . import client_gemini
    return client_gemini.generate_podcast_cover_image(*args, **kwargs)
