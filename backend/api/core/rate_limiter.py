import time
from typing import Callable, Optional
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# Use the shared Redis client helper (sync client; fail-open if unavailable)
from api.core.redis_client import get_redis_client

class RateLimitingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, limit: int = 100, window: int = 60) -> None:
        super().__init__(app)
        self.limit = limit  # Max requests
        self.window = window  # Time window in seconds

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 1. Get identifier (using client IP for simplicity in a public API context)
        # NOTE: In a production environment behind a reverse proxy (Nginx, Cloudflare), 
        # use the 'X-Forwarded-For' or similar header.
        client_ip = request.client.host if request.client else "unknown"
        
        # 2. Define the Redis key
        # Use a combination of IP and the current time window's starting time
        current_time_window = int(time.time() // self.window) * self.window
        key = f"rate_limit:{client_ip}:{current_time_window}"
        
        # 3. Access Redis (fail-open if missing or connection fails)
        redis = get_redis_client()
        if redis is None:
            return await call_next(request)

        # Use Redis pipelining for atomic INCR + EXPIRE
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, self.window)

        # Execute the pipeline (synchronous client; block briefly)
        try:
            results = pipe.execute()
            count: Optional[int] = results[0] if results else None
        except Exception:
            # Log error but allow request to pass if Redis is down (fail-open)
            return await call_next(request)
        if count is None:
            return await call_next(request)
            
        # 4. Check the limit
        if count > self.limit:
            # HTTP 429 Too Many Requests
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {self.window} seconds."
            )

        # 5. Allow the request to proceed
        response = await call_next(request)
        
        # Optionally add headers for client feedback
        response.headers["X-RateLimit-Limit"] = str(self.limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, self.limit - count))
        
        return response