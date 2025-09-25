from __future__ import annotations

import logging
import re
from typing import Iterable


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Common API key/token patterns (loose on purpose)
TOKEN_LIKE_RE = re.compile(
    r"(?i)"  # case-insensitive
    r"("
    r"(?:bearer\s+[A-Za-z0-9._~+\-/]+=*)"  # Authorization: Bearer ...
    r"|(?:sk_[A-Za-z0-9]{16,})"              # Stripe-like keys
    r"|(?:api[_-]?key\s*[=:]\s*\w{12,})"  # api_key=...
    r"|(?:api[_-]?token\s*[=:]\s*\w{12,})"# api-token=...
    r"|(?:token\s*[=:]\s*\w{12,})"        # token=...
    r")"
)

# Authorization header redaction (remove the value part entirely)
AUTH_HEADER_RE = re.compile(r"(?im)^(authorization:\s*)(.+)$")


class RedactionFilter(logging.Filter):
    """Logging filter that redacts sensitive info with ***.

    - Emails
    - Authorization headers values
    - Token-like secrets (bearer, sk_, api_key, api-token, token)
    """

    def __init__(self, replacement: str = "***") -> None:
        super().__init__()
        self.replacement = replacement

    def filter(self, record: logging.LogRecord) -> bool:  # always keep record
        try:
            msg = record.getMessage()
            msg = AUTH_HEADER_RE.sub(lambda m: f"{m.group(1)}{self.replacement}", msg)
            msg = EMAIL_RE.sub(self.replacement, msg)
            msg = TOKEN_LIKE_RE.sub(self.replacement, msg)
            if msg != record.getMessage():
                record.msg = msg
                record.args = ()
        except Exception:
            pass
        return True


def install_redaction_filter(logger: logging.Logger | None = None, *, replacement: str = "***") -> None:
    """Attach the redaction filter to all stream/file handlers on the provided logger (root if None)."""
    logger = logger or logging.getLogger()
    filt = RedactionFilter(replacement=replacement)
    for h in list(logger.handlers):
        try:
            h.addFilter(filt)
        except Exception:
            pass

__all__ = ["RedactionFilter", "install_redaction_filter"]
