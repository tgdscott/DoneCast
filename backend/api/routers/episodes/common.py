import os
from typing import Optional


def _final_url_for(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    return f"/static/final/{os.path.basename(str(path))}"


def _cover_url_for(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    p = str(path)
    if p.lower().startswith(("http://", "https://")):
        return p
    return f"/static/media/{os.path.basename(p)}"


def _status_value(s):
    try:
        return str(getattr(s, 'value', s) or '').lower()
    except Exception:
        return str(s or '').lower()


__all__ = [
    "_final_url_for",
    "_cover_url_for",
    "_status_value",
]
