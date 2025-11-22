"""Request size limit middleware to prevent resource exhaustion."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi import HTTPException
from api.core.logging import get_logger

log = get_logger("api.middleware.request_size_limit")

# Maximum request size: 100MB (configurable via env var)
MAX_REQUEST_SIZE = int(
    __import__("os").getenv("MAX_REQUEST_SIZE_BYTES", str(100 * 1024 * 1024))
)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce maximum request size limits.
    
    Prevents resource exhaustion from excessively large requests.
    """
    
    async def dispatch(self, request: Request, call_next):
        """Check request size before processing."""
        # Only check POST, PUT, PATCH requests (GET requests don't have bodies)
        if request.method in ("POST", "PUT", "PATCH"):
            content_length = request.headers.get("content-length")
            
            if content_length:
                try:
                    size = int(content_length)
                    if size > MAX_REQUEST_SIZE:
                        log.warning(
                            "Request size limit exceeded: %d bytes (max: %d bytes) for %s %s",
                            size, MAX_REQUEST_SIZE, request.method, request.url.path
                        )
                        raise HTTPException(
                            status_code=413,
                            detail=(
                                f"Request too large. Maximum size: "
                                f"{MAX_REQUEST_SIZE / 1024 / 1024:.0f}MB. "
                                f"Your request: {size / 1024 / 1024:.1f}MB"
                            )
                        )
                except ValueError:
                    # Invalid content-length header - let it through, FastAPI will handle it
                    log.debug(
                        "Invalid content-length header: %s",
                        content_length
                    )
        
        return await call_next(request)


