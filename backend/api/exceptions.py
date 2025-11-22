from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError
import traceback
import uuid
from api.core.logging import get_logger
from api.core.cors import add_cors_headers_to_response

def error_payload(code: str, message: str, details=None, request: Request | None = None, error_id: str | None = None):
    """Create error payload with user-friendly messages.
    
    Maps technical error codes to user-friendly messages while preserving
    technical details for debugging.
    """
    # Map technical error codes to user-friendly messages
    USER_FRIENDLY_MESSAGES = {
        "internal_error": "We're experiencing technical difficulties. Please try again in a moment.",
        "validation_error": "Please check your input and try again.",
        "rate_limit_exceeded": "Too many requests. Please wait a moment before trying again.",
        "service_unavailable": "A service we depend on is temporarily unavailable. Please try again shortly.",
        "http_error": message,  # Use original message for HTTP errors (usually already user-friendly)
        "circuit_breaker_open": "A service is temporarily unavailable. Please try again in a moment.",
        "timeout": "The request took too long to complete. Please try again.",
        "request_too_large": "Your request is too large. Please reduce the size and try again.",
    }
    
    # Determine if error is retryable
    retryable_codes = {
        "rate_limit_exceeded",
        "service_unavailable",
        "internal_error",
        "circuit_breaker_open",
        "timeout",
    }
    
    user_message = USER_FRIENDLY_MESSAGES.get(code, message)
    
    out = {
        "error": {
            "code": code,
            "message": user_message,
            "technical_message": message if user_message != message else None,  # Only include if different
            "details": details,
            "retryable": code in retryable_codes,
        }
    }
    
    rid = getattr(getattr(request, "state", None), "request_id", None)
    if rid:
        out["error"]["request_id"] = rid
    if error_id:
        out["error"]["error_id"] = error_id
    return out

def install_exception_handlers(app):
    log = get_logger("api.exceptions")
    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(request: Request, exc: StarletteHTTPException):
        log.warning(
            "HTTPException %s %s -> %s: %s",
            request.method, request.url.path, exc.status_code, exc.detail,
            extra={"request_id": getattr(getattr(request, "state", None), "request_id", None)}
        )
        response = JSONResponse(
            error_payload("http_error", exc.detail, {"status_code": exc.status_code}, request),
            status_code=exc.status_code
        )
        return add_cors_headers_to_response(response, request)

    @app.exception_handler(ValidationError)
    async def validation_exc_handler(request: Request, exc: ValidationError):
        log.info(
            "ValidationError %s %s",
            request.method, request.url.path,
            extra={"request_id": getattr(getattr(request, "state", None), "request_id", None), "errors": exc.errors()}
        )
        response = JSONResponse(
            error_payload("validation_error", "Validation failed", exc.errors(), request),
            status_code=422
        )
        return add_cors_headers_to_response(response, request)

    @app.exception_handler(Exception)
    async def unhandled_exc_handler(request: Request, exc: Exception):
        err_id = str(uuid.uuid4())
        rid = getattr(getattr(request, "state", None), "request_id", None)
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        log.error(
            "Unhandled exception [%s] %s %s\nTraceback:\n%s",
            err_id, request.method, request.url.path, tb,
            extra={"request_id": rid}
        )
        response = JSONResponse(
            error_payload("internal_error", "Something went wrong", None, request, error_id=err_id),
            status_code=500
        )
        return add_cors_headers_to_response(response, request)
