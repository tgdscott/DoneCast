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

# PostHog initialization
try:
    import posthog
    _posthog_key = os.getenv("POSTHOG_API_KEY")
    if _posthog_key:
        posthog.project_api_key = _posthog_key
        posthog.host = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")
        _log.info("PostHog initialized for LLM analytics")
    else:
        posthog = None
except ImportError:
    posthog = None
    _log.warning("PostHog library not found, LLM analytics disabled")


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
    default_model = "gemini-1.5-flash"
    
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
    start_time = time.time()
    model_name_used = "unknown"
    input_tokens = 0
    output_tokens = 0
    
    # Stub path short-circuit: if missing SDK/key and STUB_MODE set
    if _stub_mode() and (genai is None or _configure is None or _GenerativeModel is None or not getattr(__import__('api.core.config', fromlist=['settings']), 'settings', None).GEMINI_API_KEY):  # type: ignore
        return "Stub output (Gemini disabled)"
    
    # Circuit breaker protection for actual API calls
    from api.core.circuit_breaker import get_circuit_breaker
    breaker = get_circuit_breaker("gemini")
    
    def _generate_internal():
        nonlocal model_name_used
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
            # Resolve model with GEMINI-specific inputs, but allow VERTEX_MODEL as fallback
            # This ensures consistency if user sets VERTEX_MODEL but uses AI_PROVIDER=gemini
            model_name = (
                os.getenv("GEMINI_MODEL")
                or getattr(settings, "GEMINI_MODEL", None)
                or os.getenv("VERTEX_MODEL")
                or getattr(settings, "VERTEX_MODEL", None)
                or "gemini-1.5-flash"
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
                model_name_used = model_name
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
            
            # CRITICAL: Production default to gemini-1.5-flash, dev default to gemini-1.5-flash
            # This ensures production uses the optimized model even if VERTEX_MODEL env var is missing/overridden
            env = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or getattr(settings, "APP_ENV", "dev")).strip().lower()
            is_production = env in {"prod", "production", "stage", "staging"}
            # Use gemini-1.5-flash for both dev and production
            default_model = "gemini-1.5-flash"
            
            v_model = (
                os.getenv("VERTEX_MODEL") 
                or getattr(settings, "VERTEX_MODEL", None) 
                or getattr(settings, "GEMINI_MODEL", None) 
                or default_model
            )
            model_name_used = v_model
            
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
    
    try:
        result = breaker.call(_generate_internal)
        
        # Track success in PostHog
        if posthog:
            try:
                duration = time.time() - start_time
                # Estimate tokens (rough approx: 4 chars per token)
                input_est = len(content) // 4
                output_est = len(result) // 4
                
                posthog.capture(
                    distinct_id="system",  # Server-side event
                    event="$ai_generation",
                    properties={
                        "$ai_provider": "gemini",
                        "$ai_model": model_name_used,
                        "$ai_input": content,
                        "$ai_output": result,
                        "$ai_latency": duration,
                        "$ai_input_tokens": input_est,
                        "$ai_output_tokens": output_est,
                        "success": True
                    }
                )
            except Exception as ph_err:
                _log.warning("Failed to send PostHog event: %s", ph_err)
                
        return result
        
    except Exception as e:
        # Track failure in PostHog
        if posthog:
            try:
                duration = time.time() - start_time
                posthog.capture(
                    distinct_id="system",
                    event="$ai_generation",
                    properties={
                        "$ai_provider": "gemini",
                        "$ai_model": model_name_used,
                        "$ai_input": content,
                        "$ai_error": str(e),
                        "$ai_latency": duration,
                        "success": False
                    }
                )
            except Exception:
                pass
        raise


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
    
    Supports both public Gemini API and Vertex AI providers based on AI_PROVIDER setting.
    
    Args:
        prompt: Description of the image to generate
        aspect_ratio: Image aspect ratio (default "1:1" for square podcast covers)
        negative_prompt: Things to avoid in the image (appended to prompt as guidance)
    
    Returns:
        Base64-encoded PNG image data (as data URL), or None if generation fails
    """
    if _stub_mode():
        _log.info("STUB: Would generate image with prompt: %s", prompt)
        return None
    
    try:
        import base64
        from api.core.config import settings  # type: ignore
        
        # Determine provider
        provider = (os.getenv("AI_PROVIDER") or getattr(settings, 'AI_PROVIDER', 'gemini')).lower()
        if provider not in ("gemini", "vertex"):
            provider = "gemini"
        
        # Model name (same for both providers)
        model_name = "gemini-2.5-flash-image"
        
        # Build full prompt
        full_prompt = prompt
        if negative_prompt:
            full_prompt = f"{full_prompt}\n\nAvoid: {negative_prompt}"
        
        # Add aspect ratio instruction
        if aspect_ratio != "1:1":
            full_prompt = f"{full_prompt}\n\nImage aspect ratio: {aspect_ratio}"
        else:
            full_prompt = f"{full_prompt}\n\nCreate a square image (1:1 aspect ratio)."
        
        # Build generation config
        generation_config = {
            "temperature": 0.7,
        }
        
        # Log request details
        _log.info("=" * 80)
        _log.info("IMAGE GENERATION REQUEST - provider=%s model=%s", provider, model_name)
        _log.info(f"PROMPT ({len(full_prompt)} chars): {full_prompt}")
        _log.info(f"ASPECT RATIO: {aspect_ratio}")
        _log.info("=" * 80)
        
        # === PUBLIC GEMINI API PATH ===
        if provider == "gemini":
            if genai is None or _GenerativeModel is None or _configure is None:
                _log.error("Gemini SDK not available for image generation")
                return None
            
            # Get API key
            api_key = os.getenv("GEMINI_API_KEY") or getattr(settings, 'GEMINI_API_KEY', None)
            if not api_key:
                _log.error("GEMINI_API_KEY not set for image generation (provider=gemini)")
                return None
            
            # Configure public API
            _configure(api_key=api_key)
            _log.debug("Using public Gemini API with API key")
            
            # Create model using public SDK
            model = _GenerativeModel(model_name=model_name)  # type: ignore[misc]
            
            # Generate image
            response = model.generate_content(
                full_prompt,
                generation_config=generation_config
            )
        
        # === VERTEX AI PATH ===
        else:  # provider == "vertex"
            # Import Vertex AI SDK
            try:
                from google.cloud import aiplatform  # type: ignore
                # Import GenerativeModel from Vertex AI (NOT public SDK!)
                try:
                    from vertexai.generative_models import GenerativeModel as VertexModel  # type: ignore
                except ImportError:
                    from vertexai.preview.generative_models import GenerativeModel as VertexModel  # type: ignore
            except ImportError as e:
                _log.error("Vertex AI SDK not available: %s", e)
                return None
            
            # Initialize Vertex AI
            project = os.getenv("VERTEX_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
            location = os.getenv("VERTEX_LOCATION", "us-central1")
            
            if not project:
                _log.error("VERTEX_PROJECT not set for image generation (provider=vertex)")
                return None
            
            try:
                aiplatform.init(project=project, location=location)
                _log.debug("Using Vertex AI: project=%s location=%s", project, location)
            except Exception as e:
                _log.error("Failed to initialize Vertex AI: %s", e)
                return None
            
            # Create model using Vertex SDK
            model = VertexModel(model_name)
            
            # Convert dict config to Vertex GenerationConfig if needed
            vertex_config = None
            if generation_config:
                try:
                    try:
                        from vertexai.generative_models import GenerationConfig  # type: ignore
                    except ImportError:
                        from vertexai.preview.generative_models import GenerationConfig  # type: ignore
                    vertex_config = GenerationConfig(**generation_config)
                except Exception as config_err:
                    _log.warning("Failed to create Vertex GenerationConfig: %s, using None", config_err)
            
            # Generate image
            response = model.generate_content(
                full_prompt,
                generation_config=vertex_config
            )
        
        # === EXTRACT IMAGE DATA (same for both providers) ===
        if response and hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content:
                if hasattr(candidate.content, 'parts'):
                    parts = candidate.content.parts
                    for part in parts:
                        # Check for inline_data (base64 image)
                        if hasattr(part, 'inline_data') and part.inline_data:
                            image_data = part.inline_data.data
                            mime_type = getattr(part.inline_data, 'mime_type', 'image/png')
                            
                            if not image_data:
                                _log.error("inline_data exists but data is empty")
                                continue
                            
                            # Convert bytes to base64 string if necessary
                            if isinstance(image_data, bytes):
                                image_data = base64.b64encode(image_data).decode('utf-8')
                                _log.debug("Converted bytes to base64 (length: %d)", len(image_data))
                            elif not isinstance(image_data, str):
                                # Handle edge cases with string representation
                                image_data_str = str(image_data)
                                if image_data_str.startswith("b'") or image_data_str.startswith('b"'):
                                    try:
                                        import ast
                                        image_data_bytes = ast.literal_eval(image_data_str)
                                        if isinstance(image_data_bytes, bytes):
                                            image_data = base64.b64encode(image_data_bytes).decode('utf-8')
                                        else:
                                            image_data = image_data_str
                                    except Exception:
                                        image_data = image_data_str
                                else:
                                    image_data = image_data_str
                            
                            # Return as data URL
                            if isinstance(image_data, str) and image_data.startswith('data:'):
                                _log.info("✓ Image generated successfully (data URL format)")
                                return image_data
                            
                            _log.info("✓ Image generated successfully (data length: %d chars, mime: %s)", 
                                     len(image_data) if image_data else 0, mime_type)
                            return f"data:{mime_type};base64,{image_data}"
                        
                        # Fallback: check for text that might contain image data
                        elif hasattr(part, 'text') and part.text:
                            text = part.text.strip()
                            if text.startswith('data:image'):
                                _log.info("✓ Image generated successfully (from text part)")
                                return text
                            elif len(text) > 1000 and not text.startswith('http') and ' ' not in text[:100]:
                                _log.info("✓ Image generated successfully (base64 from text)")
                                return f"data:image/png;base64,{text}"
        
        # No image data found
        _log.warning("No image data found in response")
        if hasattr(response, 'candidates') and response.candidates:
            _log.debug("Response has %d candidate(s) but no image data", len(response.candidates))
        else:
            _log.debug("Response type: %s", type(response).__name__)
        
        return None
            
    except ImportError as e:
        _log.error("Required SDK not installed for image generation: %s", e)
        return None
    except Exception as e:
        error_msg = str(e)
        _log.error("Image generation failed: %s", e, exc_info=True)
        
        # Check for specific errors
        if "API key was reported as leaked" in error_msg or "leaked" in error_msg.lower():
            raise RuntimeError("Gemini API key has been reported as leaked. Please generate a new API key in Google AI Studio and update your GEMINI_API_KEY environment variable.")
        elif "API key" in error_msg and ("invalid" in error_msg.lower() or "not found" in error_msg.lower()):
            raise RuntimeError("Invalid or missing Gemini API key. Please check your GEMINI_API_KEY environment variable.")
        elif "PermissionDenied" in str(type(e).__name__) or "403" in error_msg:
            raise RuntimeError(f"Gemini API access denied: {error_msg}. Please check your API key permissions.")
        
        return None
