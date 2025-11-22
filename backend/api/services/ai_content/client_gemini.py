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
    
    Returns False (safe default) if environment parsing fails, with logging.
    """
    try:
        val = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").strip().lower()
        return val in {"dev", "development", "local", "test", "testing"}
    except Exception as e:
        import logging
        log = logging.getLogger(__name__)
        log.warning(
            "event=env.check_failed function=_is_dev_env error=%s - "
            "Environment variable parsing failed, defaulting to False (production mode)",
            str(e),
            exc_info=True
        )
        return False  # Safe default: treat as production if parsing fails

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
    # Use gemini-2.5-flash-lite for both dev and production as requested
    default_model = "gemini-2.5-flash-lite"
    
    model_name = (
        os.getenv("GEMINI_MODEL")
        or getattr(settings_mod, 'GEMINI_MODEL', None)
        or os.getenv("VERTEX_MODEL")
        or getattr(settings_mod, 'VERTEX_MODEL', None)
        or default_model
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
    Protected by circuit breaker to prevent cascading failures.
    """
    # Stub path short-circuit: if missing SDK/key and STUB_MODE set
    if _stub_mode() and (genai is None or _configure is None or _GenerativeModel is None or not getattr(__import__('api.core.config', fromlist=['settings']), 'settings', None).GEMINI_API_KEY):  # type: ignore
        return "Stub output (Gemini disabled)"
    
    # Circuit breaker protection for actual API calls
    from api.core.circuit_breaker import get_circuit_breaker
    breaker = get_circuit_breaker("gemini")
    
    def _generate_internal():
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

        # Extract system_instruction early (used by both Gemini and Vertex paths)
        system_instruction = kwargs.pop("system_instruction", None)
        
        provider = (os.getenv("AI_PROVIDER") or getattr(settings, "AI_PROVIDER", "gemini")).lower()
        if provider not in ("gemini", "vertex"):
            provider = "gemini"
            # Public Gemini path
        if provider == "gemini":
            # Resolve model with GEMINI-specific inputs only to avoid cross-provider mixups.
            model_name = (
                os.getenv("GEMINI_MODEL")
                or getattr(settings, "GEMINI_MODEL", None)
                or "gemini-2.5-flash-lite"
            )
            if isinstance(model_name, str) and model_name.startswith("models/"):
                model_name = model_name.split("/", 1)[1]
            if _stub_mode() and not getattr(settings, "GEMINI_API_KEY", None):
                # Avoid calling SDK at all
                return "Stub output (Gemini key missing)"
            # system_instruction was already extracted above
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
                    
                    # Circuit breaker protection for API call
                    from api.core.circuit_breaker import get_circuit_breaker
                    breaker = get_circuit_breaker("gemini")
                    
                    def _call_api():
                        return model.generate_content(
                            content,
                            generation_config=gen_conf or None,  # type: ignore[arg-type]
                            safety_settings=safety_settings_to_use,
                        )
                    
                    resp = breaker.call(_call_api)
                    
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
            
            # CRITICAL: Production default to gemini-2.5-flash-lite, dev default to gemini-1.5-flash
            # This ensures production uses the optimized model even if VERTEX_MODEL env var is missing/overridden
            env = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or getattr(settings, "APP_ENV", "dev")).strip().lower()
            is_production = env in {"prod", "production", "stage", "staging"}
            # Use gemini-2.5-flash-lite for both dev and production as requested
            default_model = "gemini-2.5-flash-lite"
            
            v_model = (
                os.getenv("VERTEX_MODEL") 
                or getattr(settings, "VERTEX_MODEL", None) 
                or getattr(settings, "GEMINI_MODEL", None) 
                or default_model
            )
            
            # CRITICAL: Log where we're getting the model from for debugging
            _log.info(
                "[vertex] Model selection: env=%s is_prod=%s os.getenv('VERTEX_MODEL')=%s, settings.VERTEX_MODEL=%s, settings.GEMINI_MODEL=%s, default=%s, final=%s",
                env,
                is_production,
                os.getenv("VERTEX_MODEL"),
                getattr(settings, "VERTEX_MODEL", None),
                getattr(settings, "GEMINI_MODEL", None),
                default_model,
                v_model
            )
            _log.info(
                "[vertex] Project selection: os.getenv('VERTEX_PROJECT')=%s, settings.VERTEX_PROJECT=%s, final=%s",
                os.getenv("VERTEX_PROJECT"),
                getattr(settings, "VERTEX_PROJECT", None),
                project
            )
            _log.info(
                "[vertex] Location selection: os.getenv('VERTEX_LOCATION')=%s, settings.VERTEX_LOCATION=%s, final=%s",
                os.getenv("VERTEX_LOCATION"),
                getattr(settings, "VERTEX_LOCATION", "us-central1"),
                location
            )
            
            # Normalize model name - remove "models/" prefix if present (Vertex accepts both formats)
            if isinstance(v_model, str) and v_model.startswith("models/"):
                v_model = v_model.split("/", 1)[1]
            
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
                # system_instruction was already extracted above (before provider check)
                
                _log.debug("[vertex] using model=%s project=%s location=%s preview=%s system_instruction=%s", 
                          v_model, project, location, preview_used, bool(system_instruction))
                
                # Initialize Vertex model with system_instruction if provided
                if system_instruction:
                    model = VertexModel(v_model, system_instruction=system_instruction)
                else:
                    model = VertexModel(v_model)
                
                # Build Vertex GenerationConfig object (Vertex SDK requires object, not dict)
                vertex_gen_config = None
                if gen_conf:
                    try:
                        # Try to import GenerationConfig from Vertex SDK
                        try:
                            from vertexai.generative_models import GenerationConfig  # type: ignore
                        except Exception:
                            from vertexai.preview.generative_models import GenerationConfig  # type: ignore
                        
                        # Build GenerationConfig with available params
                        gen_config_kwargs = {}
                        if "max_output_tokens" in gen_conf:
                            gen_config_kwargs["max_output_tokens"] = gen_conf["max_output_tokens"]
                        if "temperature" in gen_conf:
                            gen_config_kwargs["temperature"] = gen_conf["temperature"]
                        if "top_p" in gen_conf:
                            gen_config_kwargs["top_p"] = gen_conf["top_p"]
                        if "top_k" in gen_conf:
                            gen_config_kwargs["top_k"] = gen_conf["top_k"]
                        
                        if gen_config_kwargs:
                            vertex_gen_config = GenerationConfig(**gen_config_kwargs)
                    except Exception as config_err:
                        _log.warning("[vertex] Failed to create GenerationConfig: %s, using None", config_err)
                        vertex_gen_config = None
                
                # Build safety settings for Vertex
                # CRITICAL: Vertex SDK requires SafetySetting objects, not dictionaries
                # Always create BLOCK_NONE safety settings for podcast content (even if default_safety_settings is None)
                vertex_safety_settings = None
                try:
                    # Try stable import first
                    try:
                        from vertexai.generative_models import (  # type: ignore
                            HarmCategory, 
                            HarmBlockThreshold,
                            SafetySetting,
                        )
                    except Exception:
                        # Fall back to preview import
                        from vertexai.preview.generative_models import (  # type: ignore
                            HarmCategory, 
                            HarmBlockThreshold,
                            SafetySetting,
                        )
                    
                    # Create SafetySetting objects (not dictionaries!)
                    vertex_safety_settings = [
                        SafetySetting(
                            category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                            threshold=HarmBlockThreshold.BLOCK_NONE,
                        ),
                        SafetySetting(
                            category=HarmCategory.HARM_CATEGORY_HARASSMENT,
                            threshold=HarmBlockThreshold.BLOCK_NONE,
                        ),
                        SafetySetting(
                            category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                            threshold=HarmBlockThreshold.BLOCK_NONE,
                        ),
                        SafetySetting(
                            category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                            threshold=HarmBlockThreshold.BLOCK_NONE,
                        ),
                    ]
                    _log.debug("[vertex] Created SafetySetting objects with BLOCK_NONE for all categories")
                except Exception as safety_err:
                    _log.warning("[vertex] Failed to import/create safety settings: %s, using None", safety_err)
                    vertex_safety_settings = None
                
                # Use caller's safety_settings if provided
                # NOTE: If caller provides safety_settings for Vertex, they must be SafetySetting objects, not dicts
                caller_safety = kwargs.pop("safety_settings", None)
                if caller_safety is not None:
                    # Validate that caller-provided safety_settings are SafetySetting objects
                    # If they're dicts (from Gemini format), log a warning but try to use our defaults
                    if isinstance(caller_safety, list) and len(caller_safety) > 0:
                        first_item = caller_safety[0]
                        if isinstance(first_item, dict):
                            _log.warning(
                                "[vertex] Caller provided safety_settings as dicts (Gemini format), "
                                "but Vertex requires SafetySetting objects. Using default BLOCK_NONE settings instead."
                            )
                            safety_to_use = vertex_safety_settings
                        else:
                            # Assume they're SafetySetting objects
                            safety_to_use = caller_safety
                    else:
                        safety_to_use = caller_safety
                else:
                    safety_to_use = vertex_safety_settings
                
                _log.info(
                    "[vertex] generate_content: model=%s project=%s location=%s config=%s safety=%s content_len=%d",
                    v_model,
                    project,
                    location,
                    f"GenerationConfig({gen_conf})" if vertex_gen_config else "None",
                    "CALLER_PROVIDED" if caller_safety is not None else ("BLOCK_NONE" if safety_to_use else "DEFAULT"),
                    len(content)
                )
                
                # Vertex SDK uses generate_content with generation_config and safety_settings
                # Pass None if not set (don't pass empty dict)
                resp = model.generate_content(
                    content,
                    generation_config=vertex_gen_config,
                    safety_settings=safety_to_use,
                )
                
                # Check for blocked content (similar to Gemini path)
                if not hasattr(resp, 'candidates') or not resp.candidates:
                    block_reason = None
                    if hasattr(resp, 'prompt_feedback'):
                        block_reason = getattr(resp.prompt_feedback, 'block_reason', None)
                    if block_reason:
                        _log.error(
                            "[vertex] Content BLOCKED by safety filters! block_reason=%s. "
                            "Prompt preview: %s",
                            block_reason,
                            content[:500] if content else "(empty)"
                        )
                        raise RuntimeError(f"VERTEX_CONTENT_BLOCKED:{block_reason}")
                
                return getattr(resp, "text", "") or ""
            except Exception as e:
                # CRITICAL FIX: Log the actual error even in dev mode for debugging
                error_name = type(e).__name__
                error_msg = str(e)
                _log.error(
                    "[vertex] generate_content FAILED: %s: %s (model=%s project=%s location=%s)",
                    error_name,
                    error_msg,
                    v_model,
                    project,
                    location,
                    exc_info=True
                )
                
                # In dev mode, still log but return stub for non-fatal errors
                if _stub_mode() or _is_dev_env():
                    # For NotFound errors, provide helpful guidance
                    if "NotFound" in error_name or "404" in error_msg or "not found" in error_msg.lower():
                        _log.error(
                            "[vertex] MODEL NOT FOUND - Possible issues:\n"
                            "  1. Model name '%s' may be invalid or not available in location '%s'\n"
                            "  2. Try stable models: 'gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-1.5-flash-latest'\n"
                            "  3. Experimental models like 'gemini-2.0-flash-exp' may not be available in all regions\n"
                            "  4. Check Vertex AI Model Garden: https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/gemini\n"
                            "  5. Verify VERTEX_PROJECT='%s' and VERTEX_LOCATION='%s' are correct\n"
                            "  6. Ensure Vertex AI API is enabled in your GCP project\n"
                            "  7. Verify ADC (gcloud auth application-default login) is configured\n"
                            "  8. Try us-central1 if current location doesn't support the model",
                            v_model,
                            location,
                            project,
                            location
                        )
                        # Try suggesting a fallback model name if experimental model fails
                        if "exp" in v_model.lower() or "2.0" in v_model:
                            _log.warning(
                                "[vertex] Experimental model '%s' not found, consider using 'gemini-1.5-flash' instead",
                                v_model
                            )
                        return f"Stub output (vertex model not found: {v_model} in {location} - check logs for details)"
                    # For other errors, return stub with error type
                    return f"Stub output (vertex exception: {error_name})"
                
                name = type(e).__name__
                # If the region was not 'us-central1', attempt a one-time region fallback and retry once
                if str(location) != "us-central1":
                    try:
                        _log.warning("[vertex] generate_content failed in %s (%s); retrying in us-central1", location, name)
                        from google.cloud import aiplatform as _ai2  # type: ignore
                        _ai2.init(project=project, location="us-central1")
                        # Recreate model with same system_instruction
                        if system_instruction:
                            model = VertexModel(v_model, system_instruction=system_instruction)
                        else:
                            model = VertexModel(v_model)
                        # Retry with same config
                        resp = model.generate_content(
                            content,
                            generation_config=vertex_gen_config,
                            safety_settings=safety_to_use,
                        )
                        # Check for blocked content on retry too
                        if not hasattr(resp, 'candidates') or not resp.candidates:
                            block_reason = None
                            if hasattr(resp, 'prompt_feedback'):
                                block_reason = getattr(resp.prompt_feedback, 'block_reason', None)
                            if block_reason:
                                raise RuntimeError(f"VERTEX_CONTENT_BLOCKED:{block_reason}")
                        return getattr(resp, "text", "") or ""
                    except Exception as retry_err:
                        _log.error("[vertex] Retry in us-central1 also failed: %s", retry_err, exc_info=True)
                        pass
                if "NotFound" in name or "404" in str(e) or "not found" in str(e).lower():
                    raise RuntimeError(f"AI_MODEL_NOT_FOUND: {v_model} not available in {location}") from e
                raise

            # Should not reach here; if we do, return stub or raise
            if _stub_mode():
                return "Stub output (unreachable state)"
            raise RuntimeError("AI_GENERATION_UNREACHABLE")
    
    return breaker.call(_generate_internal)


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
    Generate a podcast cover image using Gemini 2.5 Flash Image model.
    
    Args:
        prompt: Description of the image to generate
        aspect_ratio: Image aspect ratio (default "1:1" for square podcast covers)
        negative_prompt: Things to avoid in the image (appended to prompt as guidance)
    
    Returns:
        Base64-encoded PNG image data, or None if generation fails
    """
    if _stub_mode():
        _log.info("STUB: Would generate image with prompt: %s", prompt)
        return None
    
    try:
        import base64
        
        if genai is None or _GenerativeModel is None or _configure is None:
            _log.error("Gemini SDK not available for image generation")
            return None
        
        # Configure Gemini API (same pattern as text generation)
        from api.core.config import settings  # type: ignore
        api_key_env = os.getenv("GEMINI_API_KEY")
        api_key_settings = getattr(settings, 'GEMINI_API_KEY', None)
        api_key = api_key_env or api_key_settings
        
        # Debug logging to help identify where API key is coming from
        if api_key:
            source = "os.getenv" if api_key_env else "settings"
            key_preview = f"{api_key[:10]}...{api_key[-4:]}" if len(api_key) > 14 else "***"
            _log.debug(f"GEMINI_API_KEY loaded from {source} (preview: {key_preview})")
        
        provider = (os.getenv("AI_PROVIDER") or getattr(settings, 'AI_PROVIDER', 'gemini')).lower()
        
        if provider not in ("gemini", "vertex"):
            provider = "gemini"
        
        if provider == "gemini":
            if not api_key:
                if _stub_mode():
                    return None
                _log.error("GEMINI_API_KEY not set for image generation")
                return None
            _configure(api_key=api_key)
        else:
            # Vertex path - use ADC
            try:
                from google.cloud import aiplatform  # type: ignore
                project = os.getenv("VERTEX_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
                location = os.getenv("VERTEX_LOCATION", "us-central1")
                if project:
                    aiplatform.init(project=project, location=location)
            except ImportError:
                _log.error("Vertex AI SDK not available")
                return None
        
        # Use Gemini 2.5 Flash Image model
        model_name = "gemini-2.5-flash-image"
        model = _GenerativeModel(model_name=model_name)  # type: ignore[misc]
        
        # Build full prompt (include negative prompt guidance if provided)
        # Note: Per Gemini docs, aspect ratio should ideally be set via generationConfig.imageConfig.aspectRatio
        # However, the older google.generativeai SDK may not support this parameter, so we include it in prompt as fallback
        full_prompt = prompt
        if negative_prompt:
            full_prompt = f"{full_prompt}\n\nAvoid: {negative_prompt}"
        
        # Add aspect ratio instruction clearly (as fallback if SDK doesn't support imageConfig parameter)
        # Format: "1:1" means square, which is standard for podcast covers
        if aspect_ratio != "1:1":
            full_prompt = f"{full_prompt}\n\nImage aspect ratio: {aspect_ratio}"
        else:
            # For square images, make it explicit since it's important for podcast covers
            full_prompt = f"{full_prompt}\n\nCreate a square image (1:1 aspect ratio)."
        
        # Build generation config
        # TODO: If upgrading to newer google.genai SDK, use generationConfig.imageConfig.aspectRatio instead
        generation_config = {
            "temperature": 0.7,
        }
        
        # Log FULL prompt and parameters being sent to Gemini
        _log.info("=" * 80)
        _log.info("GEMINI IMAGE GENERATION REQUEST - FULL DETAILS:")
        _log.info(f"MODEL: {model_name}")
        _log.info(f"PROMPT (full, {len(full_prompt)} chars): {full_prompt}")
        _log.info(f"ASPECT RATIO: {aspect_ratio} (requested)")
        _log.info("=" * 80)
        
        # Generate image using Gemini
        # For image generation models, generate_content returns image data
        # According to docs: response.parts contains part.inline_data with base64 image
        response = model.generate_content(
            full_prompt,
            generation_config=generation_config
        )
        
        # Extract image data from response
        # Per Gemini docs: https://ai.google.dev/gemini-api/docs/image-generation
        # Response structure: response.candidates[0].content.parts contains part.inline_data
        # The inline_data.data is already base64-encoded
        if response and hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content:
                if hasattr(candidate.content, 'parts'):
                    parts = candidate.content.parts
                    for part in parts:
                        # Check for inline_data (base64 image) - this is the standard format per docs
                        if hasattr(part, 'inline_data') and part.inline_data:
                            image_data = part.inline_data.data
                            mime_type = getattr(part.inline_data, 'mime_type', 'image/png')
                            if not image_data:
                                _log.error("inline_data exists but data is empty")
                                continue
                            
                            # Debug: log the type we received
                            _log.debug("image_data type: %s, first 50 chars: %s", type(image_data).__name__, str(image_data)[:50])
                            
                            # Convert bytes to base64 string if necessary
                            # According to Gemini API docs, inline_data.data should be base64-encoded string
                            # But it might come as bytes that need to be base64-encoded
                            if isinstance(image_data, bytes):
                                # If it's bytes, encode it to base64 string
                                import base64
                                image_data = base64.b64encode(image_data).decode('utf-8')
                                _log.debug("Converted bytes to base64 string (length: %d)", len(image_data))
                            elif not isinstance(image_data, str):
                                # If it's not a string or bytes, convert to string
                                image_data_str = str(image_data)
                                # Check if it's a Python byte string literal representation (b'...')
                                if image_data_str.startswith("b'") or image_data_str.startswith('b"'):
                                    _log.warning("Received byte string literal representation, attempting to extract bytes")
                                    try:
                                        import ast
                                        # Safely evaluate the byte string literal to get actual bytes
                                        image_data_bytes = ast.literal_eval(image_data_str)
                                        if isinstance(image_data_bytes, bytes):
                                            import base64
                                            image_data = base64.b64encode(image_data_bytes).decode('utf-8')
                                            _log.debug("Extracted bytes from literal and encoded to base64 (length: %d)", len(image_data))
                                        else:
                                            _log.warning("literal_eval did not return bytes, using string as-is")
                                            image_data = image_data_str
                                    except Exception as e:
                                        _log.error(f"Failed to parse byte string literal: {e}, using as-is")
                                        image_data = image_data_str
                                else:
                                    image_data = image_data_str
                            
                            # Ensure we have a clean base64 string (no data URL prefix yet)
                            if isinstance(image_data, str) and image_data.startswith('data:'):
                                # Already has data URL prefix, use as-is
                                _log.debug("Image data already has data URL prefix")
                                return image_data
                            
                            _log.info("Successfully generated podcast cover image (data length: %d chars, mime: %s)", 
                                     len(image_data) if image_data else 0, mime_type)
                            return f"data:{mime_type};base64,{image_data}"
                        # Also check for text that might contain image data
                        elif hasattr(part, 'text') and part.text:
                            text = part.text.strip()
                            # Check if it's a data URL
                            if text.startswith('data:image'):
                                _log.info("Successfully generated podcast cover image (from text part)")
                                return text
                            # Check if it's base64 data (long string, likely image)
                            elif len(text) > 1000 and not text.startswith('http') and not ' ' in text[:100]:
                                _log.info("Successfully generated podcast cover image (base64 from text part)")
                                return f"data:image/png;base64,{text}"
        
        # Fallback: check response.text directly (some SDK versions may return differently)
        if hasattr(response, 'text') and response.text:
            text = response.text.strip()
            if text.startswith('data:image'):
                _log.info("Successfully generated podcast cover image (from response.text)")
                return text
        
        _log.warning("No image data found in Gemini response")
        if hasattr(response, 'candidates'):
            _log.debug("Response candidates: %s", len(response.candidates) if response.candidates else 0)
            if response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content:
                    if hasattr(candidate.content, 'parts'):
                        parts = candidate.content.parts
                        _log.debug("Candidate content parts: %d", len(parts))
                        for i, part in enumerate(parts):
                            _log.debug("Part %d: has inline_data=%s, has text=%s", 
                                     i, hasattr(part, 'inline_data'), hasattr(part, 'text'))
                            if hasattr(part, 'inline_data'):
                                _log.debug("Part %d inline_data: %s", i, str(part.inline_data)[:200])
                            if hasattr(part, 'text'):
                                _log.debug("Part %d text preview: %s", i, str(part.text)[:200])
        else:
            _log.warning("Response has no 'candidates' attribute. Response type: %s", type(response))
            _log.debug("Response attributes: %s", dir(response))
        return None
            
    except ImportError as e:
        _log.error(f"Required SDK not installed for image generation: {e}")
        return None
    except Exception as e:
        error_msg = str(e)
        _log.error(f"Image generation failed: {e}", exc_info=True)
        
        # Check for specific API key errors
        if "API key was reported as leaked" in error_msg or "leaked" in error_msg.lower():
            raise RuntimeError("Gemini API key has been reported as leaked. Please generate a new API key in Google AI Studio and update your GEMINI_API_KEY environment variable.")
        elif "API key" in error_msg and ("invalid" in error_msg.lower() or "not found" in error_msg.lower()):
            raise RuntimeError("Invalid or missing Gemini API key. Please check your GEMINI_API_KEY environment variable.")
        elif "PermissionDenied" in str(type(e).__name__) or "403" in error_msg:
            raise RuntimeError(f"Gemini API access denied: {error_msg}. Please check your API key permissions.")
        
        # For other errors, return None to maintain backward compatibility
        return None
