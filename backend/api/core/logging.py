
from __future__ import annotations
import logging
import sys
import os
import re
from typing import Optional
from .logging_redactor import install_redaction_filter

_configured = False

class _OneLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Reserve asctime/level/name/message
        base = super().format(record)
        return base.replace("\n", " | ")

def configure_logging(level: int = logging.INFO) -> None:
    global _configured
    logger = logging.getLogger()
    logger.setLevel(level)

    # Drop any previously attached redaction filters so we can re-add with current settings
    for f in list(logger.filters):
        name = f.__class__.__name__
        if name in {"RedactionFilter", "RedactFilter"}:
            logger.removeFilter(f)
    for h in list(logger.handlers):
        for f in list(h.filters):
            name = f.__class__.__name__
            if name in {"RedactionFilter", "RedactFilter"}:
                try:
                    h.removeFilter(f)
                except Exception:
                    pass

    handler = logging.StreamHandler(sys.stdout)
    fmt = _OneLineFormatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(fmt)

    class RedactFilter(logging.Filter):
        # Simple patterns for redaction (emails, bearer/api keys tokens)
        EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
        # crude token/api key like sequences (long base64/hex-ish strings)
        TOKEN_RE = re.compile(r"(?i)(bearer\s+[A-Za-z0-9\-._~+/]+=*|sk_[A-Za-z0-9]{16,}|api_key=\w{16,}|api[_-]?token=\w{16,})")

        def filter(self, record: logging.LogRecord) -> bool:
            try:
                msg = record.getMessage()
                redacted = self.EMAIL_RE.sub("<redacted-email>", msg)
                redacted = self.TOKEN_RE.sub("<redacted-secret>", redacted)
                if redacted != msg:
                    record.msg = redacted
                    record.args = ()
            except Exception:
                pass
            return True

    redact_filter = RedactFilter()
    handler.addFilter(redact_filter)
    # Ensure all existing handlers also redact
    for h in logger.handlers:
        h.addFilter(redact_filter)
    # Attach at the logger level so caplog-style collectors see redacted messages.
    logger.addFilter(redact_filter)
    # Also attach global redaction filter (masks emails/tokens/Authorization)
    install_redaction_filter(logger)
    logger.addHandler(handler)
    _configured = True

    # Quiet noisy libraries a bit
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

def get_logger(name: Optional[str] = None) -> logging.Logger:
    if not name:
        name = __name__
    if not _configured:
        configure_logging()
    return logging.getLogger(name)
