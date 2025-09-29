import os
from typing import Optional

from api.core.paths import FINAL_DIR, MEDIA_DIR


def _final_url_for(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    base = os.path.basename(str(path))
    try:
        if (FINAL_DIR / base).is_file():
            return f"/static/final/{base}"
    except Exception:
        pass
    try:
        if (MEDIA_DIR / base).is_file():
            return f"/static/media/{base}"
    except Exception:
        pass
    return f"/static/final/{base}"


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
