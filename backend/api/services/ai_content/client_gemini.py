from __future__ import annotations

import json
import os
import logging
import time
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

def _is_dev_env() -> bool:
    """Return True if running in a local/dev/test environment.

    We consider typical local setups where strict cloud auth shouldn't block UX.
    """
    val = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").strip().lower()
    return val in {"dev", "development", "local", "test", "testing"}

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
    
    Implements exponential backoff retry for 429 (rate limit) errors.
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
    
    # Default MOST PERMISSIVE safety settings for podcast content
    # Podcasts often discuss mature topics (sex education, crime, violence, medical content)
    # that are 100% legitimate but Gemini's filters block them as "harmful"
    # BLOCK_NONE = disable safety filters entirely (appropriate for professional content analysis)
    # If caller explicitly passes safety_settings, respect that; otherwise use maximally permissive.
    default_safety_settings = None
    if genai:
        try:
            # Import the safety enums
            from google.generativeai.types import HarmCategory, HarmBlockThreshold  # type: ignore
            # BLOCK_NONE = Completely disable safety filtering for all categories
            # This is appropriate for:
            # - Educational content (sex ed, health topics)
            # - Entertainment (true crime, horror, mature comedy)
            # - News/documentary content (violence, tragedy, sensitive topics)
            default_safety_settings = {
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
            _log.debug("[gemini] Created BLOCK_NONE safety settings for podcast content analysis")
        except Exception as e:
            # If import fails, log warning and continue without safety settings
            _log.warning("[gemini] Failed to create relaxed safety settings: %s", e)
            pass

    provider = (os.getenv("AI_PROVIDER") or getattr(settings, "AI_PROVIDER", "gemini")).lower()
    if provider not in ("gemini", "vertex"):
        provider = "gemini"
    # Public Gemini path
    if provider == "gemini":
        # Resolve model with GEMINI-specific inputs only to avoid cross-provider mixups.
        model_name = (
            os.getenv("GEMINI_MODEL")
            or getattr(settings, "GEMINI_MODEL", None)
            or "models/gemini-1.5-flash-latest"
        )
        if isinstance(model_name, str) and model_name.startswith("models/"):
            model_name = model_name.split("/", 1)[1]
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
        # Call SDK with retry logic for rate limits
        max_retries = 3
        base_delay = 2.0  # seconds
        
        for attempt in range(max_retries):
            try:
                # Use caller's safety_settings if provided, otherwise use relaxed defaults
                # Check once before the loop starts (don't pop multiple times in retry loop!)
                if attempt == 0:
                    caller_safety = kwargs.pop("safety_settings", None)
                    safety_settings_to_use = caller_safety if caller_safety is not None else default_safety_settings
                    
                    _log.info(
                        "[gemini] generate_content: model=%s safety_settings=%s content_len=%d",
                        model_name,
                        "CALLER_PROVIDED" if caller_safety is not None else "BLOCK_NONE (default)",
                        len(content)
                    )
                
                resp = model.generate_content(
                    content,
                    generation_config=gen_conf or None,  # type: ignore[arg-type]
                    safety_settings=safety_settings_to_use,
                )
                
                # Check if content was blocked by safety filters
                # This happens when resp.candidates is empty due to PROHIBITED_CONTENT
                if not hasattr(resp, 'candidates') or not resp.candidates:
                    block_reason = None
                    safety_ratings = None
                    if hasattr(resp, 'prompt_feedback'):
                        block_reason = getattr(resp.prompt_feedback, 'block_reason', None)
                        safety_ratings = getattr(resp.prompt_feedback, 'safety_ratings', None)
                    
                    if block_reason:
                        _log.error(
                            "[gemini] Content BLOCKED by safety filters! block_reason=%s safety_ratings=%s. "
                            "This is a FALSE POSITIVE for legitimate podcast content. "
                            "Using BLOCK_NONE settings should prevent this. "
                            "Prompt preview: %s",
                            block_reason,
                            safety_ratings,
                            content[:500] if content else "(empty)"
                        )
                        raise RuntimeError(f"GEMINI_CONTENT_BLOCKED:{block_reason}")
                
                return getattr(resp, "text", "") or ""
            except Exception as e:
                # Only downgrade to stub when explicit stub mode is enabled
                if _stub_mode():
                    return f"Stub output (exception: {type(e).__name__})"
                
                name = type(e).__name__
                error_str = str(e)
                
                # Handle 429 rate limit errors with exponential backoff
                if "429" in error_str or "ResourceExhausted" in name or "quota" in error_str.lower():
                    if attempt < max_retries - 1:  # Don't sleep on last attempt
                        delay = base_delay * (2 ** attempt)  # Exponential backoff: 2s, 4s, 8s
                        _log.warning(
                            "[gemini] Rate limit hit (429), retrying in %.1fs (attempt %d/%d)",
                            delay, attempt + 1, max_retries
                        )
                        time.sleep(delay)
                        continue
                    else:
                        _log.error("[gemini] Rate limit exceeded after %d retries", max_retries)
                        raise RuntimeError("GEMINI_RATE_LIMIT_EXCEEDED") from e
                
                # Non-retryable errors
                if "NotFound" in name or "404" in error_str:
                    raise RuntimeError("AI_MODEL_NOT_FOUND") from e
                raise
    # Vertex path
    else:
        # Lazy import vertex AI only when needed
        try:
            from google.cloud import aiplatform  # type: ignore
        except Exception as e:  # pragma: no cover
            if _stub_mode() or _is_dev_env():
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
            if _stub_mode() or _is_dev_env():
                return "Stub output (vertex project missing)"
            raise RuntimeError("VERTEX_PROJECT_NOT_SET")
        try:
            aiplatform.init(project=project, location=location)
        except Exception as e:
            # If the configured region doesn't support the model or Vertex GenAI,
            # fall back to the canonical region 'us-central1' to avoid hard failures.
            if _stub_mode() or _is_dev_env():
                return "Stub output (vertex init error)"
            try:
                if str(location) != "us-central1":
                    _log.warning("[vertex] init failed for location=%s; retrying with us-central1", location)
                    aiplatform.init(project=project, location="us-central1")
                    location = "us-central1"
                else:
                    raise
            except Exception:
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
            if _stub_mode() or _is_dev_env():
                return "Stub output (vertex model import error)"
            raise RuntimeError("VERTEX_MODEL_CLASS_UNAVAILABLE") from e
        try:
            _log.debug("[vertex] using model=%s project=%s location=%s preview=%s", v_model, project, location, preview_used)
            model = VertexModel(v_model)
            # Vertex SDK uses generate_content similarly but may differ slightly
            resp = model.generate_content(content)
            return getattr(resp, "text", "") or ""
        except Exception as e:
            if _stub_mode() or _is_dev_env():
                # Specific auth guidance often appears in the error; keep it terse
                return f"Stub output (vertex exception: {type(e).__name__})"
            name = type(e).__name__
            # If the region was not 'us-central1', attempt a one-time region fallback and retry once
            if str(location) != "us-central1":
                try:
                    _log.warning("[vertex] generate_content failed in %s (%s); retrying in us-central1", location, name)
                    from google.cloud import aiplatform as _ai2  # type: ignore
                    _ai2.init(project=project, location="us-central1")
                    model = VertexModel(v_model)
                    resp = model.generate_content(content)
                    return getattr(resp, "text", "") or ""
                except Exception:
                    pass
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


def generate_podcast_cover_image(
    prompt: str,
    *,
    aspect_ratio: str = "1:1",  # Podcast covers are square
    negative_prompt: Optional[str] = None,
) -> Optional[str]:
    """
    Generate a podcast cover image using Vertex AI Imagen.
    
    Args:
        prompt: Description of the image to generate
        aspect_ratio: Image aspect ratio (default "1:1" for square podcast covers)
        negative_prompt: Things to avoid in the image
    
    Returns:
        Base64-encoded PNG image data, or None if generation fails
    
    Cost: ~$0.020 per image (Imagen 3 standard quality)
    """
    if _stub_mode():
        _log.info("STUB: Would generate image with prompt: %s", prompt)
        return None
    
    try:
        from vertexai.preview.vision_models import ImageGenerationModel  # type: ignore
        import vertexai  # type: ignore
        import base64
        
        # Initialize Vertex AI
        project = os.getenv("VERTEX_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("VERTEX_LOCATION", "us-central1")
        
        if not project:
            _log.error("VERTEX_PROJECT not configured for image generation")
            return None
        
        vertexai.init(project=project, location=location)
        
        # Use Imagen 3
        model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")
        
        # Build generation parameters
        generation_params = {
            "prompt": prompt,
            "number_of_images": 1,
            "aspect_ratio": aspect_ratio,
            "safety_filter_level": "block_some",  # Balanced filtering
            "person_generation": "allow_all",  # Allow people in images
        }
        
        if negative_prompt:
            generation_params["negative_prompt"] = negative_prompt
        
        # Generate image
        _log.info(f"Generating podcast cover image: {prompt[:100]}...")
        response = model.generate_images(**generation_params)
        
        if response.images:
            # Get first image and convert to base64
            image = response.images[0]
            image_bytes = image._image_bytes
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            _log.info("Successfully generated podcast cover image")
            return f"data:image/png;base64,{base64_image}"
        else:
            _log.warning("No images generated from Imagen")
            return None
            
    except ImportError:
        _log.error("Vertex AI SDK not installed for image generation")
        return None
    except Exception as e:
        _log.error(f"Image generation failed: {e}", exc_info=True)
        return None
