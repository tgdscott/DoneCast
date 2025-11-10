from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError
import traceback
import uuid
from api.core.logging import get_logger
from api.core.cors import add_cors_headers_to_response

def error_payload(code: str, message: str, details=None, request: Request | None = None, error_id: str | None = None):
    out = {"error": {"code": code, "message": message, "details": details}}
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
