from __future__ import annotations

from typing import List, Optional


def parse_tags(raw_tags) -> List[str]:
    if not raw_tags:
        return []
    try:
        if isinstance(raw_tags, str):
            parts = [p.strip() for p in raw_tags.split(',')]
        elif isinstance(raw_tags, (list, tuple)):
            parts = [str(p).strip() for p in raw_tags]
        else:
            parts = []
        clean: List[str] = []
        for t in parts:
            if not t:
                continue
            if len(t) > 30:
                t = t[:30]
            clean.append(t)
            if len(clean) >= 20:
                break
        return clean
    except Exception:
        return []
