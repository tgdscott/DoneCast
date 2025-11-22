"""Performance metrics middleware for request tracking."""
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from api.core.logging import get_logger

log = get_logger("api.middleware.metrics")

# Thresholds for logging slow requests
SLOW_REQUEST_THRESHOLD = float(
    __import__("os").getenv("SLOW_REQUEST_THRESHOLD_SECONDS", "1.0")
)
VERY_SLOW_REQUEST_THRESHOLD = float(
    __import__("os").getenv("VERY_SLOW_REQUEST_THRESHOLD_SECONDS", "5.0")
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to track request performance metrics.
    
    Logs slow requests and adds timing headers to responses.
    """
    
    async def dispatch(self, request: Request, call_next):
        """Track request duration and log slow requests."""
        start_time = time.time()
        
        try:
            response = await call_next(request)
            duration = time.time() - start_time
            
            # Add timing header
            response.headers["X-Response-Time"] = f"{duration:.3f}"
            
            # Log slow requests
            if duration >= VERY_SLOW_REQUEST_THRESHOLD:
                log.error(
                    "Very slow request: %s %s took %.2fs (threshold: %.2fs)",
                    request.method,
                    request.url.path,
                    duration,
                    VERY_SLOW_REQUEST_THRESHOLD,
                    extra={
                        "request_id": getattr(
                            getattr(request, "state", None), "request_id", None
                        ),
                        "duration": duration,
                        "method": request.method,
                        "path": request.url.path,
                    }
                )
            elif duration >= SLOW_REQUEST_THRESHOLD:
                log.warning(
                    "Slow request: %s %s took %.2fs (threshold: %.2fs)",
                    request.method,
                    request.url.path,
                    duration,
                    SLOW_REQUEST_THRESHOLD,
                    extra={
                        "request_id": getattr(
                            getattr(request, "state", None), "request_id", None
                        ),
                        "duration": duration,
                        "method": request.method,
                        "path": request.url.path,
                    }
                )
            
            return response
            
        except Exception as e:
            # Even if request fails, track duration
            duration = time.time() - start_time
            log.error(
                "Request failed after %.2fs: %s %s - %s",
                duration,
                request.method,
                request.url.path,
                str(e),
                extra={
                    "request_id": getattr(
                        getattr(request, "state", None), "request_id", None
                    ),
                    "duration": duration,
                    "method": request.method,
                    "path": request.url.path,
                    "error": str(e),
                }
            )
            raise


