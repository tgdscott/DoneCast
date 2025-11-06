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
    """Generate text using the configured AI provider.
    
    Routes to the appropriate client based on AI_PROVIDER env var:
    - groq: Uses Groq API (fast, free tier)
    - gemini: Uses Google Gemini API
    - vertex: Uses Google Vertex AI
    """
    provider = get_provider()
    
    if provider == "groq":
        from . import client_groq
        return client_groq.generate(content, **kwargs)
    elif provider in ("gemini", "vertex"):
        from . import client_gemini
        return client_gemini.generate(content, **kwargs)
    else:
        _log.warning(f"[ai_router] Unknown provider '{provider}', falling back to gemini")
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
