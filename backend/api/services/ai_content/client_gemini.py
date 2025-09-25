from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

try:  # pragma: no cover - optional dependency
    import google.generativeai as genai  # type: ignore
    from google.generativeai.client import configure as _configure  # type: ignore
    from google.generativeai.generative_models import GenerativeModel as _GenerativeModel  # type: ignore
except Exception:  # pragma: no cover
    genai = None
    _configure = None
    _GenerativeModel = None


def _get_model():
    if genai is None or _configure is None or _GenerativeModel is None:
        raise RuntimeError("google-generativeai is not installed")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in environment")
    _configure(api_key=api_key)
    return _GenerativeModel("gemini-2.5-flash")


def generate(content: str, **kwargs) -> str:
    """Generate text using Gemini with optional tuning via kwargs.

    Supported kwargs (moved into generation_config):
      - max_tokens -> max_output_tokens (int)
      - max_output_tokens (int)
      - temperature (float)
      - top_p (float)
      - top_k (int)

    Other optional kwargs:
      - system_instruction (str)
      - safety_settings (passed through to SDK)
    """
    # Ensure SDK available
    if genai is None or _configure is None or _GenerativeModel is None:  # pragma: no cover
        raise RuntimeError("Gemini SDK not available")

    # Configure with our API key from settings
    from api.core.config import settings  # local import to avoid problems if settings not loaded at import-time
    _configure(api_key=getattr(settings, "GEMINI_API_KEY", None))

    # Build generation_config
    gen_conf: Dict[str, Any] = {}
    if "max_tokens" in kwargs:
        try:
            gen_conf["max_output_tokens"] = int(kwargs.pop("max_tokens"))
        except Exception:
            kwargs.pop("max_tokens", None)
    if "max_output_tokens" in kwargs:
        try:
            gen_conf["max_output_tokens"] = int(kwargs.pop("max_output_tokens"))
        except Exception:
            kwargs.pop("max_output_tokens", None)
    for k in ("temperature", "top_p", "top_k"):
        if k in kwargs and kwargs[k] is not None:
            gen_conf[k] = kwargs.pop(k)

    # Initialize model
    model_name = getattr(settings, "GEMINI_MODEL", None) or "models/gemini-1.5-flash-latest"
    system_instruction = kwargs.pop("system_instruction", None)
    model = (
        _GenerativeModel(model_name=model_name, system_instruction=system_instruction)
        if system_instruction
        else _GenerativeModel(model_name=model_name)
    )

    # Call SDK
    resp = model.generate_content(
        content,
    generation_config=gen_conf or None,  # type: ignore[arg-type]
        safety_settings=kwargs.pop("safety_settings", None),
    )
    return getattr(resp, "text", "") or ""


def generate_json(content: str) -> Dict[str, Any]:
    raw = ""
    try:
        raw = generate(content)
        return json.loads(raw)
    except Exception:
        # best-effort: attempt to extract JSON from raw text
        try:
            txt = raw or ""
            start = txt.find("[") if "[" in txt else txt.find("{")
            end = txt.rfind("]") if "]" in txt else txt.rfind("}")
            if start != -1 and end != -1:
                return json.loads(txt[start : end + 1])
        except Exception:
            pass
        return {}
