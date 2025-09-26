from __future__ import annotations

import json
import os
import logging
from typing import Any, Dict, Optional, Callable
_log = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    import google.generativeai as genai  # type: ignore
    from google.generativeai.client import configure as _configure  # type: ignore
    from google.generativeai.generative_models import GenerativeModel as _GenerativeModel  # type: ignore
except Exception:  # pragma: no cover
    genai = None
    _configure = None
    _GenerativeModel = None


def _stub_mode() -> bool:
    """Return True if we should operate in stub mode.

    Made dynamic (function) instead of a module-level constant so that tests or
    late environment injection (e.g. setting AI_STUB_MODE after import) still
    take effect. Previously, a user starting the server without AI_STUB_MODE set
    would lock out stub behavior for the lifetime of the process.
    """
    return (os.getenv("AI_STUB_MODE") or "").strip() == "1"

def _get_model():
    """Return an initialized GenerativeModel or None (stub path).

    We intentionally avoid caching to allow hot changes to env vars (e.g. user
    adds a key while the server is running and triggers a reload via code edit).
    """
    if genai is None or _configure is None or _GenerativeModel is None:
        if _stub_mode():
            return None
        raise RuntimeError("Gemini SDK not available")
    # Lazy import settings so tests can monkeypatch
    settings_mod = getattr(__import__('api.core.config', fromlist=['settings']), 'settings', None)  # type: ignore
    api_key = os.getenv("GEMINI_API_KEY") or getattr(settings_mod, 'GEMINI_API_KEY', None)
    provider = (os.getenv("AI_PROVIDER") or getattr(settings_mod, 'AI_PROVIDER', 'gemini')).lower()
    if provider not in ("gemini", "vertex"):
        provider = "gemini"
    if provider == "gemini":
        if not api_key:
            if _stub_mode():
                return None
            raise RuntimeError("GEMINI_API_KEY not set in environment")
        _configure(api_key=api_key)
    else:  # vertex path
        # For Vertex we rely on ADC; GEMINI_API_KEY is ignored.
        # We initialize lazily via google.cloud.aiplatform only when generating.
        pass
    if _GenerativeModel is None:  # double guard
        if _stub_mode():
            return None
        raise RuntimeError("Gemini model class unavailable")
    # Model name resolution: prefer explicit env/setting otherwise fallback
    model_name = (
        os.getenv("GEMINI_MODEL")
        or getattr(settings_mod, 'GEMINI_MODEL', None)
        or os.getenv("VERTEX_MODEL")
        or getattr(settings_mod, 'VERTEX_MODEL', None)
        or "gemini-1.5-flash"
    )
    # Accept legacy forms like "models/gemini-1.5-flash-latest" and normalize
    if model_name.startswith("models/"):
        # generativeai SDK accepts either but we normalize to the shorter alias
        model_name = model_name.split("/", 1)[1]
    try:
        return _GenerativeModel(model_name=model_name)  # type: ignore[misc]
    except Exception as e:
        # If model creation itself fails and stub is enabled, just drop to stub path
        if _stub_mode():
            return None
        raise


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
    # Stub path short-circuit: if missing SDK/key and STUB_MODE set
    if _stub_mode() and (genai is None or _configure is None or _GenerativeModel is None or not getattr(__import__('api.core.config', fromlist=['settings']), 'settings', None).GEMINI_API_KEY):  # type: ignore
        return "Stub output (Gemini disabled)"

    # Configure with our API key from settings
    from api.core.config import settings  # local import
    if _configure and getattr(settings, "GEMINI_API_KEY", None):  # guard for stub mode
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

    provider = (os.getenv("AI_PROVIDER") or getattr(settings, "AI_PROVIDER", "gemini")).lower()
    if provider not in ("gemini", "vertex"):
        provider = "gemini"
    # Public Gemini path
    model_name = getattr(settings, "GEMINI_MODEL", None) or "models/gemini-1.5-flash-latest"
    if provider == "gemini":
        if _stub_mode() and not getattr(settings, "GEMINI_API_KEY", None):
            # Avoid calling SDK at all
            return "Stub output (Gemini key missing)"
        system_instruction = kwargs.pop("system_instruction", None)
        if not _GenerativeModel:
            if _stub_mode():
                return "Stub output (model unavailable)"
            raise RuntimeError("Gemini model class unavailable")
        try:
            if _stub_mode():
                _log.debug("[gemini] stub_mode=1 model=%s (will short-circuit on errors)", model_name)
            else:
                _log.debug("[gemini] using model=%s system_instruction=%s", model_name, bool(system_instruction))
            model = (
                _GenerativeModel(model_name=model_name, system_instruction=system_instruction)  # type: ignore[misc]
                if system_instruction
                else _GenerativeModel(model_name=model_name)  # type: ignore[misc]
            )
        except Exception as e:
            if _stub_mode():
                return f"Stub output (model init error: {type(e).__name__})"
            raise
        # Call SDK
        try:
            resp = model.generate_content(
                content,
                generation_config=gen_conf or None,  # type: ignore[arg-type]
                safety_settings=kwargs.pop("safety_settings", None),
            )
            return getattr(resp, "text", "") or ""
        except Exception as e:
            # Common provider errors we may want to downgrade in stub mode
            if _stub_mode():
                return f"Stub output (exception: {type(e).__name__})"
            name = type(e).__name__
            if "NotFound" in name or "404" in str(e):
                raise RuntimeError("AI_MODEL_NOT_FOUND") from e
            raise
    # Vertex path
    else:
        # Lazy import vertex AI only when needed
        try:
            from google.cloud import aiplatform  # type: ignore
        except Exception as e:  # pragma: no cover
            if _stub_mode():
                return "Stub output (vertex import error)"
            raise RuntimeError("VERTEX_SDK_NOT_AVAILABLE") from e
        # Accept both VERTEX_PROJECT and legacy VERTEX_PROJECT_ID for convenience
        project = (
            os.getenv("VERTEX_PROJECT")
            or os.getenv("VERTEX_PROJECT_ID")
            or getattr(settings, "VERTEX_PROJECT", None)
            or getattr(settings, "VERTEX_PROJECT_ID", None)
        )
        location = os.getenv("VERTEX_LOCATION") or getattr(settings, "VERTEX_LOCATION", "us-central1")
        v_model = os.getenv("VERTEX_MODEL") or getattr(settings, "VERTEX_MODEL", None) or getattr(settings, "GEMINI_MODEL", None) or "gemini-1.5-flash"
        if not project:
            if _stub_mode():
                return "Stub output (vertex project missing)"
            raise RuntimeError("VERTEX_PROJECT_NOT_SET")
        try:
            aiplatform.init(project=project, location=location)
        except Exception as e:
            if _stub_mode():
                return "Stub output (vertex init error)"
            raise RuntimeError("VERTEX_INIT_FAILED") from e
        # Newer SDK deprecates the 'preview' path; prefer stable import first.
        try:
            try:
                from vertexai.generative_models import GenerativeModel as VertexModel  # type: ignore
                preview_used = False
            except Exception:
                from vertexai.preview.generative_models import GenerativeModel as VertexModel  # type: ignore
                preview_used = True
                _log.warning("[vertex] Using deprecated preview GenerativeModel; update code to stable API before June 24 2026.")
        except Exception as e:
            if _stub_mode():
                return "Stub output (vertex model import error)"
            raise RuntimeError("VERTEX_MODEL_CLASS_UNAVAILABLE") from e
        try:
            _log.debug("[vertex] using model=%s project=%s location=%s preview=%s", v_model, project, location, preview_used)
            model = VertexModel(v_model)
            # Vertex SDK uses generate_content similarly but may differ slightly
            resp = model.generate_content(content)
            return getattr(resp, "text", "") or ""
        except Exception as e:
            if _stub_mode():
                return f"Stub output (vertex exception: {type(e).__name__})"
            name = type(e).__name__
            if "NotFound" in name or "404" in str(e):
                raise RuntimeError("AI_MODEL_NOT_FOUND") from e
            raise

    # Should not reach here; if we do, return stub or raise
    if _stub_mode():
        return "Stub output (unreachable state)"
    raise RuntimeError("AI_GENERATION_UNREACHABLE")


def generate_json(content: str) -> Dict[str, Any]:
    raw = ""
    try:
        raw = generate(content)
        return json.loads(raw)
    except Exception:
        if _stub_mode() and not raw:
            return {"tags": ["stub", "ai", "example"]}
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
