import logging
from typing import Optional, Any

import redis
from api.core.config import settings

log = logging.getLogger("api.core.redis_client")

_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> Optional[redis.Redis]:
    """
    Lazy-initializes and returns a Redis client.
    Returns None if connection fails (fail-open strategy).
    """
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    # Assume settings are available as per instructions
    # We use getattr to be safe during the transition period before settings are updated
    host = getattr(settings, "REDIS_HOST", None)
    port = getattr(settings, "REDIS_PORT", None)

    if not host or not port:
        return None

    try:
        client = redis.Redis(
            host=host,
            port=port,
            socket_timeout=1.0,
            decode_responses=True
        )
        # Verify connection
        client.ping()
        _redis_client = client
        return _redis_client
    except Exception as e:
        log.warning(f"Redis connection failed: {e}. Falling back to database.")
        return None


def redis_get(key: str) -> Optional[str]:
    """
    Fail-open Redis GET wrapper.
    """
    try:
        client = get_redis_client()
        if not client:
            return None
        return client.get(key)
    except Exception as e:
        log.warning(f"Redis GET failed for {key}: {e}")
        return None


def redis_setex(key: str, time: int, value: Any) -> bool:
    """
    Fail-open Redis SETEX wrapper.
    """
    try:
        client = get_redis_client()
        if not client:
            return False
        return client.setex(key, time, value)
    except Exception as e:
        log.warning(f"Redis SETEX failed for {key}: {e}")
        return False


def redis_set(key: str, value: Any) -> bool:
    """
    Fail-open Redis SET wrapper.
    """
    try:
        client = get_redis_client()
        if not client:
            return False
        return client.set(key, value)
    except Exception as e:
        log.warning(f"Redis SET failed for {key}: {e}")
        return False
