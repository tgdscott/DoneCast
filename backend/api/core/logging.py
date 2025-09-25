
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
    if _configured:
        return
    logger = logging.getLogger()
    logger.setLevel(level)

    # Remove existing handlers (avoid double logs if reloaded)
    for h in list(logger.handlers):
        logger.removeHandler(h)

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

    handler.addFilter(RedactFilter())
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
