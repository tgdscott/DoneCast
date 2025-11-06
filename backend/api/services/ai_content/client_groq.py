from __future__ import annotations

import os
import logging
from typing import Any, Dict

_log = logging.getLogger(__name__)

try:
    from groq import Groq
except ImportError:
    Groq = None


def _stub_mode() -> bool:
    """Return True if AI_STUB_MODE=1."""
    return (os.getenv("AI_STUB_MODE") or "").strip() == "1"


def generate(content: str, **kwargs) -> str:
    """Generate text using Groq's API.
    
    Supported kwargs:
      - max_tokens (int) - maximum tokens to generate
      - temperature (float) - sampling temperature (0.0 to 2.0)
      - top_p (float) - nucleus sampling probability
      - system_instruction (str) - system message for the model
    
    Returns:
        Generated text string
    """
    if _stub_mode() or Groq is None:
        _log.warning("[groq] Running in stub mode - returning placeholder text")
        return "Stub output (Groq disabled)"
    
    # Get API key
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        if _stub_mode():
            return "Stub output (no GROQ_API_KEY)"
        raise RuntimeError("GROQ_API_KEY not set in environment")
    
    # Get model name
    model_name = os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile"
    
    # Extract system instruction if provided
    system_instruction = kwargs.pop("system_instruction", None)
    
    # Build messages list
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": content})
    
    # Build request parameters
    request_params: Dict[str, Any] = {
        "model": model_name,
        "messages": messages,
    }
    
    # Map common parameters
    if "max_tokens" in kwargs:
        request_params["max_tokens"] = int(kwargs.pop("max_tokens"))
    if "temperature" in kwargs:
        request_params["temperature"] = float(kwargs.pop("temperature"))
    if "top_p" in kwargs:
        request_params["top_p"] = float(kwargs.pop("top_p"))
    
    _log.info(
        "[groq] generate: model=%s max_tokens=%s content_len=%d",
        model_name,
        request_params.get("max_tokens", "default"),
        len(content)
    )
    
    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(**request_params)
        
        if not response.choices:
            _log.error("[groq] No choices returned in response")
            if _stub_mode():
                return "Stub output (no choices)"
            raise RuntimeError("No response from Groq API")
        
        result = response.choices[0].message.content or ""
        _log.debug("[groq] Generated %d characters", len(result))
        return result
        
    except Exception as e:
        _log.error("[groq] Generation failed: %s", str(e))
        if _stub_mode():
            return f"Stub output (exception: {type(e).__name__})"
        raise
