"""
Transcript discovery and download utilities.

This module centralizes all logic for locating, downloading, and materializing
transcripts from various sources (local filesystem, GCS bucket, HTTP URLs).
"""

from pathlib import Path
from typing import Optional, Iterable, Any, TYPE_CHECKING
from urllib.parse import urlparse
import json
import os
import uuid

from api.core.paths import TRANSCRIPTS_DIR
from api.services.audio.transcript_io import load_transcript_json
from api.services.episodes import repo as _ep_repo
from api.services.audio.common import sanitize_filename

if TYPE_CHECKING:
    from api.models.podcast import Episode
    from sqlmodel import Session
    from uuid import UUID as _UUID

try:
    from api.infrastructure import gcs as _gcs
except Exception:
    _gcs = None


def _stem_variants(value: Any) -> list[str]:
    """Return normalized stem candidates for a value.

    We try to account for case differences and filename sanitization so that
    lookups succeed whether the stored transcript uses the original stem,
    a lowercase variant, or a sanitized slug (e.g., spaces replaced with
    hyphens).
    """
    if value is None:
        return []
    try:
        text = str(value).strip()
    except Exception:
        return []
    if not text:
        return []
    try:
        base = Path(text).stem
    except Exception:
        base = text

    variants: list[str] = []
    seen: set[str] = set()

    def _add(candidate: str) -> None:
        candidate = candidate.strip()
        if not candidate:
            return
        if candidate in seen:
            return
        seen.add(candidate)
        variants.append(candidate)

    _add(base)
    _add(base.lower())
    # Allow swapping common separators so foo_bar.json and foo-bar.json match
    _add(base.replace("_", "-"))
    _add(base.replace("-", "_"))

    sanitized = sanitize_filename(base)
    _add(sanitized)
    _add(sanitized.replace("_", "-"))

    return variants


def _extend_candidates(values: Iterable[Any]) -> list[str]:
    """Extend a list of values into all normalized stem variants."""
    results: list[str] = []
    seen: set[str] = set()
    for value in values:
        for variant in _stem_variants(value):
            if variant in seen:
                continue
            seen.add(variant)
            results.append(variant)
    return results


def _download_transcript_from_bucket(stem: str, user_id: Optional[str] = None) -> Optional[Path]:
    """Attempt to download ``{stem}.json`` from the configured transcript bucket."""
    bucket = (os.getenv("TRANSCRIPTS_BUCKET") or os.getenv("MEDIA_BUCKET") or "").strip()
    if not bucket or not stem:
        return None
    if _gcs is None:
        return None

    # Try a range of common transcript JSON variants used by the pipeline
    variants = [
        f"{stem}.json",
        f"{stem}.words.json",
        f"{stem}.original.json",
        f"{stem}.original.words.json",
        f"{stem}.final.json",
        f"{stem}.final.words.json",
        f"{stem}.nopunct.json",  # least preferred, but fine for intent detection
    ]

    keys: list[str] = []
    for v in variants:
        if user_id:
            keys.append(f"transcripts/{user_id}/{v}")
        keys.append(f"transcripts/{v}")

    for key in keys:
        try:
            data = _gcs.download_bytes(bucket, key)
        except Exception:
            continue
        try:
            TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
            # Preserve the specific variant filename locally to avoid collisions
            path = TRANSCRIPTS_DIR / Path(key).name
            path.write_bytes(data)
            return path
        except Exception:
            continue
    return None


def _download_transcript_from_url(url: str) -> Optional[Path]:
    """Attempt to download a transcript JSON from an HTTP(S) URL."""
    if not isinstance(url, str) or not url.strip():
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    try:
        import requests
    except Exception:
        return None
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        stem = Path(parsed.path).stem or uuid.uuid4().hex
        TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        path = TRANSCRIPTS_DIR / f"{stem}.json"
        path.write_bytes(resp.content)
        return path
    except Exception:
        return None


def discover_or_materialize_transcript(
    episode_id: Optional[str] = None, hint: Optional[str] = None
) -> Optional[str]:
    """Locate or synthesize a transcript bound to the provided identifiers.

    Historically this helper returned the newest transcript in ``TRANSCRIPTS_DIR``
    regardless of which episode created it. That behaviour caused AI suggestion
    endpoints to occasionally reuse transcripts from unrelated episodes. The
    updated implementation limits discovery to files whose stem (including
    common pipeline variants like ``.original`` or temporary ``ai_*`` files)
    matches the episode identifier or optional ``hint`` provided by the client.
    
    Returns the path to a .txt transcript (or None if not found).
    """
    candidates = set(_extend_candidates([episode_id, hint]))
    if not candidates:
        return None

    try:
        TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None

    def _path_variants(path: Path) -> set[str]:
        stem = path.stem
        variants = set(_stem_variants(stem))
        if "." in stem:
            variants.update(_stem_variants(stem.split(".", 1)[0]))
        if stem.endswith(".tmp"):
            variants.update(_stem_variants(stem[:-4]))
        if stem.startswith("ai_"):
            variants.update(_stem_variants(stem[3:]))
        if stem.startswith("ai_") and stem.endswith(".tmp"):
            variants.update(_stem_variants(stem[3:-4]))
        return variants

    def _matches(path: Path) -> bool:
        try:
            variants = _path_variants(path)
        except Exception:
            return False
        return any(v in candidates for v in variants)

    try:
        txt_matches = sorted(
            [p for p in TRANSCRIPTS_DIR.glob("*.txt") if _matches(p)],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        txt_matches = []

    if txt_matches:
        return str(txt_matches[0])

    try:
        json_matches = sorted(
            [
                p
                for p in TRANSCRIPTS_DIR.glob("*.json")
                if not p.name.endswith(".nopunct.json") and _matches(p)
            ],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        json_matches = []

    if json_matches:
        json_path = json_matches[0]
        try:
            words = load_transcript_json(json_path)
            text = " ".join([str(w.get("word", "")).strip() for w in words if w.get("word")])
            out = TRANSCRIPTS_DIR / f"ai_{json_path.stem}.tmp.txt"
            out.write_text(text, encoding="utf-8")
            return str(out)
        except Exception:
            return None

    return None


def discover_transcript_for_episode(
    session: "Session", episode_id: str, hint: Optional[str] = None
) -> Optional[str]:
    """
    Find a transcript specific to this episode:
      - Build base stems from Episode.working_audio_name, Episode.final_audio_path, meta_json hints
      - Also include an optional `hint` (filename) passed by the UI
      - Prefer {stem}.txt then {stem}.json; if JSON, materialize a temp .txt
      
    Returns the path to a .txt transcript (or None if not found).
    """
    from uuid import UUID as _UUID
    
    # Normalize hint to a stem once so we can use it even if Episode lookup fails
    hint_stem: Optional[str] = None
    if hint:
        try:
            hint_stem = Path(str(hint)).stem
        except Exception:
            hint_stem = None
    hint_stems = _extend_candidates([hint_stem]) if hint_stem else []
    
    try:
        ep_uuid = _UUID(str(episode_id))
    except Exception:
        ep_uuid = None
    
    ep: Optional["Episode"]
    try:
        ep = _ep_repo.get_episode_by_id(session, ep_uuid) if ep_uuid else None
    except Exception:
        ep = None
    
    if not ep:
        # Fallback: allow hint-only discovery even without an Episode row
        if hint_stems:
            TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
            # Prefer exact .txt, then .json for each normalized hint stem
            for stem in hint_stems:
                txt_cand = TRANSCRIPTS_DIR / f"{stem}.txt"
                if txt_cand.exists():
                    return str(txt_cand)
            for stem in hint_stems:
                json_cand = TRANSCRIPTS_DIR / f"{stem}.json"
                if json_cand.exists():
                    try:
                        words = load_transcript_json(json_cand)
                        text = " ".join([str(w.get("word", "")).strip() for w in words if w.get("word")])
                        out = TRANSCRIPTS_DIR / f"ai_{json_cand.stem}.tmp.txt"
                        out.write_text(text, encoding="utf-8")
                        return str(out)
                    except Exception:
                        pass
            # Broader match: look for files that contain the stem
            try:
                lowered = [s.lower() for s in hint_stems]
                txts = [
                    p
                    for p in TRANSCRIPTS_DIR.glob("*.txt")
                    if any(stem in p.stem.lower() for stem in lowered)
                ]
                txts.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                if txts:
                    return str(txts[0])
                jsons = [
                    p
                    for p in TRANSCRIPTS_DIR.glob("*.json")
                    if any(stem in p.stem.lower() for stem in lowered) and not p.name.endswith(".nopunct.json")
                ]
                jsons.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                if jsons:
                    try:
                        words = load_transcript_json(jsons[0])
                        text = " ".join([str(w.get("word", "")).strip() for w in words if w.get("word")])
                        out = TRANSCRIPTS_DIR / f"ai_{jsons[0].stem}.tmp.txt"
                        out.write_text(text, encoding="utf-8")
                        return str(out)
                    except Exception:
                        pass
            except Exception:
                pass
        return None

    stems: list[str] = []
    seen: set[str] = set()

    for cand in [getattr(ep, "working_audio_name", None), getattr(ep, "final_audio_path", None)]:
        for variant in _stem_variants(cand):
            if variant in seen:
                continue
            seen.add(variant)
            stems.append(variant)

    # add hint if provided
    for variant in hint_stems:
        if variant in seen:
            continue
        seen.add(variant)
        stems.append(variant)

    # meta_json may contain source names
    try:
        meta = json.loads(getattr(ep, "meta_json", "{}") or "{}")
        for k in ("source_filename", "main_content_filename", "output_filename"):
            v = meta.get(k)
            for variant in _stem_variants(v):
                if variant in seen:
                    continue
                seen.add(variant)
                stems.append(variant)
    except Exception:
        pass

    if not stems and hint_stems:
        stems.extend(hint_stems)
        stems = list(dict.fromkeys(stems))

    if not stems:
        return None

    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    # Prefer exact .txt, then .json
    txt_match = None
    json_match = None
    for s in stems:
        cand = TRANSCRIPTS_DIR / f"{s}.txt"
        if cand.exists():
            txt_match = cand
            break
    if not txt_match:
        for s in stems:
            cand = TRANSCRIPTS_DIR / f"{s}.json"
            if cand.exists():
                json_match = cand
                break

    if txt_match:
        return str(txt_match)
    if json_match:
        try:
            words = load_transcript_json(json_match)
            text = " ".join([str(w.get("word", "")).strip() for w in words if w.get("word")])
            out = TRANSCRIPTS_DIR / f"ai_{json_match.stem}.tmp.txt"
            out.write_text(text, encoding="utf-8")
            return str(out)
        except Exception:
            return None
    return None


def discover_transcript_json_path(
    session: "Session",
    episode_id: Optional[str] = None,
    hint: Optional[str] = None,
) -> Optional[Path]:
    """Return the best matching transcript JSON path for an episode or hint."""
    from uuid import UUID as _UUID
    
    candidates: list[str] = []
    seen: set[str] = set()
    remote_sources: list[str] = []
    user_id: Optional[str] = None
    hint_stem: Optional[str] = None
    
    if hint:
        try:
            hint_stem = Path(str(hint)).stem
        except Exception:
            hint_stem = None
        if isinstance(hint, str) and hint.strip():
            remote_sources.append(hint.strip())
    
    if hint_stem:
        for variant in _stem_variants(hint_stem):
            if variant in seen:
                continue
            seen.add(variant)
            candidates.append(variant)

    if episode_id:
        try:
            ep_uuid = _UUID(str(episode_id))
        except Exception:
            ep_uuid = None
        ep: Optional["Episode"]
        try:
            ep = _ep_repo.get_episode_by_id(session, ep_uuid) if ep_uuid else None
        except Exception:
            ep = None
        if ep:
            try:
                user_id = str(getattr(ep, "user_id", "") or "") or None
            except Exception:
                user_id = None
            for attr in ("working_audio_name", "final_audio_path"):
                stem = getattr(ep, attr, None)
                for variant in _stem_variants(stem):
                    if variant in seen:
                        continue
                    seen.add(variant)
                    candidates.append(variant)
            try:
                meta = json.loads(getattr(ep, "meta_json", "{}") or "{}")
                for key in ("source_filename", "main_content_filename", "output_filename"):
                    val = meta.get(key)
                    for variant in _stem_variants(val):
                        if variant in seen:
                            continue
                        seen.add(variant)
                        candidates.append(variant)
                transcripts_meta = meta.get("transcripts") or {}
                if isinstance(transcripts_meta, dict):
                    for val in transcripts_meta.values():
                        for variant in _stem_variants(val):
                            if variant in seen:
                                continue
                            seen.add(variant)
                            candidates.append(variant)
                        if isinstance(val, str) and val.strip():
                            remote_sources.append(val.strip())
                extra_stem = meta.get("transcript_stem")
                for variant in _stem_variants(extra_stem):
                    if variant in seen:
                        continue
                    seen.add(variant)
                    candidates.append(variant)
            except Exception:
                pass

    if not candidates:
        return None

    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    def _resolve_for_stem(stem: str) -> Optional[Path]:
        preferred = [
            TRANSCRIPTS_DIR / f"{stem}.json",
            TRANSCRIPTS_DIR / f"{stem}.original.json",
            TRANSCRIPTS_DIR / f"{stem}.words.json",
            TRANSCRIPTS_DIR / f"{stem}.original.words.json",
            TRANSCRIPTS_DIR / f"{stem}.final.json",
            TRANSCRIPTS_DIR / f"{stem}.final.words.json",
            TRANSCRIPTS_DIR / f"{stem}.nopunct.json",
        ]
        for path in preferred:
            if path.exists():
                return path
        try:
            matches = [
                p
                for p in TRANSCRIPTS_DIR.glob("*.json")
                if stem in p.stem
            ]
            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            if matches:
                return matches[0]
        except Exception:
            return None
        return None

    attempted_download: set[str] = set()
    for stem in candidates:
        resolved = _resolve_for_stem(stem)
        if resolved:
            return resolved
        if stem not in attempted_download:
            attempted_download.add(stem)
            downloaded = _download_transcript_from_bucket(stem, user_id)
            if downloaded:
                return downloaded

    for source in dict.fromkeys(remote_sources):
        parsed = urlparse(source)
        stem_hint = Path(parsed.path).stem if parsed.scheme else Path(source).stem
        downloaded = None
        if parsed.scheme in {"http", "https"}:
            downloaded = _download_transcript_from_url(source)
        elif parsed.scheme == "gs":
            downloaded = _download_transcript_from_bucket(stem_hint, user_id)
        else:
            downloaded = _resolve_for_stem(Path(source).stem)
        if downloaded:
            return downloaded

    return None
