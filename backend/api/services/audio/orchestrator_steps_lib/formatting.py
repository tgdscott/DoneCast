from __future__ import annotations

import os
from typing import Any


def parse_int_env(name: str, default: int) -> int:
    """Return a positive integer from the environment or ``default``."""
    try:
        raw = os.environ.get(name)
        if raw is None:
            return default
        value = int(str(raw).strip())
        if value <= 0:
            return default
        return value
    except Exception:
        return default


def format_bytes(num: int) -> str:
    """Human readable representation for byte counts."""
    units = ["bytes", "KiB", "MiB", "GiB", "TiB"]
    n = float(num)
    for unit in units:
        if n < 1024.0 or unit == units[-1]:
            if unit == "bytes":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} {units[-1]}"


def format_ms(ms: int) -> str:
    return fmt_ts(max(0.0, ms) / 1000.0)


def fmt_ts(s: Any) -> str:
    """Format seconds into ``MM:SS.mmm`` guarding against bad input."""
    try:
        ms = int(max(0.0, float(s)) * 1000)
        mm = ms // 60000
        ss = (ms % 60000) / 1000.0
        return f"{mm:02d}:{ss:06.3f}"
    except Exception:
        return "00:00.000"
