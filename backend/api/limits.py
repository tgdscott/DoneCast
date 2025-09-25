import os
from typing import Callable

try:
    from slowapi import Limiter as _Limiter
    from slowapi.util import get_remote_address as _get_remote_address
except Exception:  # pragma: no cover - slowapi may be missing locally before install
    _Limiter = None  # type: ignore
    _get_remote_address = None  # type: ignore


DISABLE = os.getenv("DISABLE_RATE_LIMITS") == "1"
DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "600/hour")
STORAGE = os.getenv("RATE_LIMIT_REDIS_URL")


class NoopLimiter:
    def limit(self, _spec: str) -> Callable:
        def _decorator(fn):
            return fn
        return _decorator


def _build_limiter():
    if DISABLE or _Limiter is None:
        return NoopLimiter()
    kwargs = {}
    if STORAGE:
        # slowapi/limits uses storage_uri for backends like redis://...
        kwargs["storage_uri"] = STORAGE
    # Provide a safe fallback key function if slowapi util isn't available
    def _fallback_key_func(request):  # type: ignore
        try:
            return request.client.host  # type: ignore[attr-defined]
        except Exception:
            return "anon"
    keyf = _get_remote_address or _fallback_key_func
    return _Limiter(key_func=keyf, default_limits=[DEFAULT], **kwargs)


limiter = _build_limiter()

__all__ = ["limiter", "NoopLimiter", "DISABLE", "DEFAULT", "STORAGE"]
