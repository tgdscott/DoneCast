from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import json

try:
    # Prefer httpx if present for better timeouts; fall back to requests
    import httpx  # type: ignore

    _HTTPX_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    import requests  # type: ignore

    _HTTPX_AVAILABLE = False


class ElevenLabsService:
    """Lightweight client wrapper for ElevenLabs Platform API (v1).

    - Caches list of voices in-memory for 10 minutes.
    - Provides simple search (name, labels) and pagination.
    """

    BASE_URL = "https://api.elevenlabs.io/v1"
    _CACHE_TTL_SEC = 10 * 60

    def __init__(self, platform_key: str) -> None:
        if not platform_key or not isinstance(platform_key, str):
            raise ValueError("A valid ElevenLabs platform key is required")
        self.platform_key = platform_key
        self._voices_cache: Optional[Dict[str, Any]] = None
        self._voices_cache_at: float = 0.0

    # --- Internal helpers ---
    def _headers(self) -> Dict[str, str]:
        return {"xi-api-key": self.platform_key}

    def _now(self) -> float:
        return time.time()

    def _cache_valid(self) -> bool:
        return bool(self._voices_cache and (self._now() - self._voices_cache_at) < self._CACHE_TTL_SEC)

    def _fetch_voices(self) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/voices"
        if _HTTPX_AVAILABLE:
            with httpx.Client(timeout=15.0) as client:  # type: ignore[name-defined]
                r = client.get(url, headers=self._headers())
                r.raise_for_status()
                return r.json()
        else:  # requests fallback
            r = requests.get(url, headers=self._headers(), timeout=15)
            r.raise_for_status()
            return r.json()

    def _fetch_voice(self, voice_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single voice by ID. Returns None if not found or on 404s.

        Best-effort; raises only on non-HTTP errors or hard failures.
        """
        url = f"{self.BASE_URL}/voices/{voice_id}"
        try:
            if _HTTPX_AVAILABLE:
                with httpx.Client(timeout=15.0) as client:  # type: ignore[name-defined]
                    r = client.get(url, headers=self._headers())
                    if r.status_code == 404:
                        return None
                    r.raise_for_status()
                    return r.json()
            else:
                r = requests.get(url, headers=self._headers(), timeout=15)
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r.json()
        except Exception:
            # Treat as not found in this context
            return None

    def _get_all_voices(self) -> List[Dict[str, Any]]:
        if not self._cache_valid():
            data = self._fetch_voices() or {}
            # Expected shape from ElevenLabs: { "voices": [ ... ] }
            self._voices_cache = data
            self._voices_cache_at = self._now()
        data = self._voices_cache or {}
        voices = data.get("voices")
        if not isinstance(voices, list):
            return []
        return voices  # type: ignore[return-value]

    @staticmethod
    def compute_common_name(v: Dict[str, Any]) -> Optional[str]:
        """Best-effort friendly/common display name.

        Preference order:
        - labels.common_name
        - labels.display_name
        - labels.friendly_name
        - top-level name
        """
        try:
            labels = v.get("labels") or {}
            if isinstance(labels, dict):
                for key in ("common_name", "display_name", "friendly_name"):
                    val = labels.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
        except Exception:
            pass
        nm = v.get("name")
        return nm if isinstance(nm, str) and nm.strip() else None

    @staticmethod
    def pick_preview_url(v: Dict[str, Any]) -> Optional[str]:
        pu = v.get("preview_url")
        if isinstance(pu, str) and pu:
            return pu
        try:
            samples = v.get("samples") or []
            if isinstance(samples, list) and samples:
                s0 = samples[0] or {}
                spu = s0.get("preview_url")
                if isinstance(spu, str) and spu:
                    return spu
        except Exception:
            pass
        return None

    # --- Public API ---
    def list_voices(self, search: str = "", page: int = 1, size: int = 25) -> Dict[str, Any]:
        """List voices with optional search and pagination.

        Returns a dict: { items: [...], page, size, total }
    Each item: { voice_id, name, common_name, description, preview_url, labels }
        """
        # Normalize paging
        try:
            page_i = max(1, int(page))
        except Exception:
            page_i = 1
        try:
            size_i = max(1, min(200, int(size)))
        except Exception:
            size_i = 25

        raw = self._get_all_voices()
        q = (search or "").strip().lower()

        def to_str_labels(lbl: Any) -> str:
            try:
                return json.dumps(lbl, ensure_ascii=False, sort_keys=True)
            except Exception:
                return str(lbl)

        filtered: List[Dict[str, Any]]
        if q:
            filtered = []
            for v in raw:
                name = (v.get("name") or "").lower()
                cname = (self.compute_common_name(v) or "").lower()
                labels_str = to_str_labels(v.get("labels"))
                if q in name or q in cname or q in labels_str.lower():
                    filtered.append(v)
        else:
            filtered = list(raw)

        total = len(filtered)
        start = (page_i - 1) * size_i
        end = start + size_i
        page_items = filtered[start:end]

        items = []
        for v in page_items:
            item = {
                "voice_id": v.get("voice_id"),
                "name": v.get("name"),
                "common_name": self.compute_common_name(v),
                "description": v.get("description"),
                "preview_url": self.pick_preview_url(v),
                "labels": v.get("labels"),
            }
            items.append(item)

        return {"items": items, "page": page_i, "size": size_i, "total": total}

    def get_voice(self, voice_id: str) -> Optional[Dict[str, Any]]:
        """Return a normalized VoiceItem-like dict for a single id, or None if not found."""
        v = self._fetch_voice(str(voice_id))
        if not v:
            return None
        return {
            "voice_id": v.get("voice_id") or voice_id,
            "name": v.get("name"),
            "common_name": self.compute_common_name(v),
            "description": v.get("description"),
            "preview_url": self.pick_preview_url(v),
            "labels": v.get("labels"),
        }
