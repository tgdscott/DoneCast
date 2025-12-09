import logging
import uuid
import traceback
from typing import Optional, Mapping, Any
from fastapi import HTTPException

_log = logging.getLogger("api.exceptions")


def audit_and_raise_conflict(detail: str, context: Optional[Mapping[str, Any]] = None) -> None:
    """Log a loud, auditable 409 then raise the original HTTPException.

    - Keeps the original `detail` string for backwards compatibility with callers/tests.
    - Emits an `X-Debug-ID` header on the response (via HTTPException.headers).
    - Logs the full stack and supplied context at ERROR level with the debug id so operators
      can trace exactly why a `TRANSCRIPT_NOT_READY` (or other 409) was returned.
    """
    debug_id = uuid.uuid4().hex
    try:
        stack = "\n".join(traceback.format_stack()[:-1])
    except Exception:
        stack = "(failed to capture stack)"

    try:
        ctx_str = "" if context is None else repr(dict(context))
    except Exception:
        ctx_str = "(failed to stringify context)"

    # Emit an obvious, searchable ERROR log with rich context
    _log.error(
        "event=conflict_audit debug_id=%s detail=%s context=%s",
        debug_id,
        detail,
        ctx_str,
        exc_info=False,
    )
    # Also log the stack trace on its own line so it's easy to find in aggregated logs
    _log.error("event=conflict_stack debug_id=%s stack=\n%s", debug_id, stack)

    # Preserve original detail string (important for frontend/tests) but add header for ops.
    raise HTTPException(status_code=409, detail=detail, headers={"X-Debug-ID": debug_id})


def audit_conflict_log_only(detail: str, context: Optional[Mapping[str, Any]] = None) -> str:
    """Log the conflict loudly and return the generated debug id without raising an exception.

    Use this from non-request contexts (service layer, background tasks) to emit the
    same searchable logs while allowing callers to control their raised exception types.
    Returns the hex debug id string for correlation.
    """
    debug_id = uuid.uuid4().hex
    try:
        stack = "\n".join(traceback.format_stack()[:-1])
    except Exception:
        stack = "(failed to capture stack)"
    try:
        ctx_str = "" if context is None else repr(dict(context))
    except Exception:
        ctx_str = "(failed to stringify context)"
    _log.error(
        "event=conflict_audit debug_id=%s detail=%s context=%s",
        debug_id,
        detail,
        ctx_str,
        exc_info=False,
    )
    _log.error("event=conflict_stack debug_id=%s stack=\n%s", debug_id, stack)
    return debug_id
