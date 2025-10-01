from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Optional, Iterable, Dict, Any
from pathlib import Path
from urllib.parse import urlparse
import json, os
import uuid

from api.core.paths import TRANSCRIPTS_DIR
import logging
from api.services.audio.transcript_io import load_transcript_json
from api.services.episodes import repo as _ep_repo
from api.models.podcast import Episode, MediaItem, MediaCategory
from uuid import UUID as _UUID
from api.core.database import get_session
from sqlmodel import Session, select
from api.models.podcast import PodcastTemplate
from api.services.ai_content.schemas import (
    SuggestTitleIn,
    SuggestTitleOut,
    SuggestNotesIn,
    SuggestNotesOut,
    SuggestTagsIn,
    SuggestTagsOut,
)
from api.services.ai_content.generators.title import suggest_title
from api.services.ai_content.generators.notes import suggest_notes
from api.services.ai_content.generators.tags import suggest_tags
from api.services.intent_detection import analyze_intents, get_user_commands
from api.routers.auth import get_current_user
from api.models.user import User
from api.services.audio.common import sanitize_filename

try:  # Optional dependency for transcript downloads from GCS
    from api.infrastructure import gcs as _gcs  # type: ignore
except Exception:  # pragma: no cover - optional dependency missing
    _gcs = None  # type: ignore

try:
    # Limiter is attached to app.state by main.py; get a safe reference for decorators
    from api.limits import limiter as _limiter
except Exception:  # pragma: no cover
    _limiter = None  # type: ignore


router = APIRouter(prefix="/ai", tags=["ai"])
_log = logging.getLogger(__name__)


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
    results: list[str] = []
    seen: set[str] = set()
    for value in values:
        for variant in _stem_variants(value):
            if variant in seen:
                continue
            seen.add(variant)
            results.append(variant)
    return results

def _is_dev_env() -> bool:
    val = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").strip().lower()
    return val in {"dev", "development", "local", "test", "testing"}


def _download_transcript_from_bucket(stem: str, user_id: Optional[str] = None) -> Optional[Path]:
    """Attempt to download ``{stem}.json`` from the configured transcript bucket."""

    bucket = (os.getenv("TRANSCRIPTS_BUCKET") or os.getenv("MEDIA_BUCKET") or "").strip()
    if not bucket or not stem:
        return None
    if _gcs is None:  # pragma: no cover - optional dependency missing in tests
        return None

    keys: list[str] = []
    if user_id:
        keys.append(f"transcripts/{user_id}/{stem}.json")
    keys.append(f"transcripts/{stem}.json")

    for key in keys:
        try:
            data = _gcs.download_bytes(bucket, key)  # type: ignore[attr-defined]
        except Exception:
            continue
        try:
            TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
            path = TRANSCRIPTS_DIR / f"{stem}.json"
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
    except Exception:  # pragma: no cover - optional dependency missing in some envs
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


def _discover_or_materialize_transcript(episode_id: Optional[str] = None) -> Optional[str]:
    try:
        TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        # Prefer newest .txt transcript
        txts = sorted(TRANSCRIPTS_DIR.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        if txts:
            return str(txts[0])
        # Fallback: construct text from newest working JSON
        jsons = [p for p in TRANSCRIPTS_DIR.glob("*.json") if not p.name.endswith(".nopunct.json")]
        jsons.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        if jsons:
            words = load_transcript_json(jsons[0])
            text = " ".join([str(w.get("word", "")).strip() for w in words if w.get("word")])
            stem = (str(episode_id) if episode_id else uuid.uuid4().hex)[:8]
            out = TRANSCRIPTS_DIR / f"ai_{stem}.tmp.txt"
            out.write_text(text, encoding="utf-8")
            return str(out)
    except Exception:
        pass
    return None


def _discover_transcript_for_episode(session: Session, episode_id: str, hint: Optional[str] = None) -> Optional[str]:
    """
    Find a transcript specific to this episode:
      - Build base stems from Episode.working_audio_name, Episode.final_audio_path, meta_json hints
      - Also include an optional `hint` (filename) passed by the UI
      - Prefer {stem}.txt then {stem}.json; if JSON, materialize a temp .txt
    """
    ep: Optional[Episode]
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
    try:
        ep = _ep_repo.get_episode_by_id(session, ep_uuid) if ep_uuid else None  # returns Episode or None
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
            # Broader match: look for files that contain the stem (e.g., *.original.txt or sanitized variants)
            try:
                lowered = [s.lower() for s in hint_stems]
                # Collect candidates; prefer .txt (including *.original.txt), else .json (excluding .nopunct.json)
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
        import json as _json

        meta = _json.loads(getattr(ep, "meta_json", "{}") or "{}")
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


def _discover_transcript_json_path(
    session: Session,
    episode_id: Optional[str] = None,
    hint: Optional[str] = None,
) -> Optional[Path]:
    """Return the best matching transcript JSON path for an episode or hint."""

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
        ep: Optional[Episode]
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
        ]
        for path in preferred:
            if path.exists():
                return path
        try:
            matches = [
                p
                for p in TRANSCRIPTS_DIR.glob("*.json")
                if stem in p.stem and not p.name.endswith(".nopunct.json")
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


def _gather_user_sfx_entries(session: Session, current_user: User) -> Iterable[Dict[str, Any]]:
    try:
        stmt = (
            select(MediaItem)
            .where(
                MediaItem.user_id == current_user.id,
                MediaItem.trigger_keyword != None,  # noqa: E711
                MediaItem.category == MediaCategory.sfx,
            )
        )
        for item in session.exec(stmt):
            trigger = getattr(item, "trigger_keyword", None)
            if not trigger:
                continue
            label = getattr(item, "friendly_name", None) or Path(str(item.filename)).stem
            yield {
                "phrase": trigger,
                "label": label,
                "source": f"media:{item.id}",
            }
    except Exception:
        return []


def _get_template_settings(session: Session, podcast_id):
    if podcast_id is None or (isinstance(podcast_id, str) and not podcast_id.strip()):
        return {}
    try:
        tmpl = session.exec(select(PodcastTemplate).where(PodcastTemplate.podcast_id == podcast_id)).first()
    except Exception:
        tmpl = None
    if not tmpl:
        return {}
    try:
        return json.loads(getattr(tmpl, 'ai_settings_json', '{}') or '{}')
    except Exception:
        return {}


@router.post("/title", response_model=SuggestTitleOut)
@(_limiter.limit("10/minute") if _limiter and hasattr(_limiter, "limit") else (lambda f: f))
def post_title(request: Request, inp: SuggestTitleIn, session: Session = Depends(get_session)) -> SuggestTitleOut:
    if not inp.transcript_path:
        inp.transcript_path = _discover_transcript_for_episode(session, str(inp.episode_id), getattr(inp, 'hint', None)) or _discover_or_materialize_transcript(str(inp.episode_id))
    if not inp.transcript_path:
        raise HTTPException(status_code=409, detail="TRANSCRIPT_NOT_READY")
    settings = _get_template_settings(session, inp.podcast_id)
    if settings:
        extra = settings.get('title_instructions')
        if extra and not getattr(inp, 'extra_instructions', None):
            inp.extra_instructions = str(extra)
    try:
        return suggest_title(inp)
    except RuntimeError as e:
        # Normalize known runtime markers for structured response
        msg = str(e)
        mapped = _map_ai_runtime_error(msg)
        raise HTTPException(status_code=mapped["status"], detail=mapped)
    except Exception as e:  # pragma: no cover - defensive catch
        _log.exception("[ai_title] unexpected error: %s", e)
        if os.getenv("AI_STUB_MODE") == "1" or _is_dev_env():
            return SuggestTitleOut(title="Stub Title (error fallback)")
        raise HTTPException(status_code=500, detail={"error":"AI_INTERNAL_ERROR"})


@router.post("/notes", response_model=SuggestNotesOut)
@(_limiter.limit("10/minute") if _limiter and hasattr(_limiter, "limit") else (lambda f: f))
def post_notes(request: Request, inp: SuggestNotesIn, session: Session = Depends(get_session)) -> SuggestNotesOut:
    if not inp.transcript_path:
        inp.transcript_path = _discover_transcript_for_episode(session, str(inp.episode_id), getattr(inp, 'hint', None)) or _discover_or_materialize_transcript(str(inp.episode_id))
    if not inp.transcript_path:
        raise HTTPException(status_code=409, detail="TRANSCRIPT_NOT_READY")
    settings = _get_template_settings(session, inp.podcast_id)
    if settings:
        extra = settings.get('notes_instructions')
        if extra and not getattr(inp, 'extra_instructions', None):
            inp.extra_instructions = str(extra)
    try:
        return suggest_notes(inp)
    except RuntimeError as e:
        mapped = _map_ai_runtime_error(str(e))
        raise HTTPException(status_code=mapped["status"], detail=mapped)
    except Exception as e:  # pragma: no cover
        _log.exception("[ai_notes] unexpected error: %s", e)
        if os.getenv("AI_STUB_MODE") == "1" or _is_dev_env():
            return SuggestNotesOut(description="Stub Notes (error fallback)", bullets=["stub", "notes"])
        raise HTTPException(status_code=500, detail={"error":"AI_INTERNAL_ERROR"})


@router.post("/tags", response_model=SuggestTagsOut)
@(_limiter.limit("10/minute") if _limiter and hasattr(_limiter, "limit") else (lambda f: f))
def post_tags(request: Request, inp: SuggestTagsIn, session: Session = Depends(get_session)) -> SuggestTagsOut:
    if not inp.transcript_path:
        inp.transcript_path = _discover_transcript_for_episode(session, str(inp.episode_id), getattr(inp, 'hint', None)) or _discover_or_materialize_transcript(str(inp.episode_id))
    if not inp.transcript_path:
        raise HTTPException(status_code=409, detail="TRANSCRIPT_NOT_READY")
    settings = _get_template_settings(session, inp.podcast_id)
    if settings:
        extra = settings.get('tags_instructions')
        if extra and not getattr(inp, 'extra_instructions', None):
            inp.extra_instructions = str(extra)
        if hasattr(inp, 'tags_always_include'):
            inp.tags_always_include = list(settings.get('tags_always_include') or [])
        # Respect opt-out: if auto_generate_tags is false, return only the pinned tags
        if settings.get('auto_generate_tags') is False:
            return SuggestTagsOut(tags=list(inp.tags_always_include or []))
    try:
        return suggest_tags(inp)
    except RuntimeError as e:
        mapped = _map_ai_runtime_error(str(e))
        raise HTTPException(status_code=mapped["status"], detail=mapped)
    except Exception as e:  # pragma: no cover
        _log.exception("[ai_tags] unexpected error: %s", e)
        if os.getenv("AI_STUB_MODE") == "1" or _is_dev_env():
            return SuggestTagsOut(tags=["stub", "tags"])
        raise HTTPException(status_code=500, detail={"error":"AI_INTERNAL_ERROR"})

@router.get("/dev-status")
def ai_dev_status(request: Request):
    """Diagnostic endpoint reporting AI configuration state."""
    try:
        from api.core.config import settings as _settings  # type: ignore
    except Exception:
        _settings = None  # type: ignore
    key_present = bool(os.getenv("GEMINI_API_KEY") or getattr(_settings, "GEMINI_API_KEY", None))
    provider = (os.getenv("AI_PROVIDER") or getattr(_settings, "AI_PROVIDER", "gemini")).lower()
    model = (
        os.getenv("VERTEX_MODEL")
        or getattr(_settings, "VERTEX_MODEL", None)
        or os.getenv("GEMINI_MODEL")
        or getattr(_settings, "GEMINI_MODEL", None)
        or "gemini-1.5-flash"
    )
    vertex_project = (
        os.getenv("VERTEX_PROJECT")
        or os.getenv("VERTEX_PROJECT_ID")
        or getattr(_settings, "VERTEX_PROJECT", None)
        or getattr(_settings, "VERTEX_PROJECT_ID", None)
    )
    return {
        "provider": provider,
        "model": model,
        "stub_mode": os.getenv("AI_STUB_MODE") == "1",
        "gemini_key_present": key_present,
        "vertex_project": vertex_project,
        "vertex_location": os.getenv("VERTEX_LOCATION") or getattr(_settings, "VERTEX_LOCATION", None) or "us-central1",
    }


# --- Internal helpers -------------------------------------------------------
def _map_ai_runtime_error(msg: str) -> Dict[str, Any]:
    base = {"error": msg}
    # Default classification
    status = 503
    normalized = msg.upper()
    if "MODEL_NOT_FOUND" in normalized:
        base = {"error": "MODEL_NOT_FOUND"}
    elif "VERTEX_PROJECT_NOT_SET" in normalized:
        base = {"error": "VERTEX_PROJECT_NOT_SET"}
    elif "VERTEX_INIT_FAILED" in normalized:
        base = {"error": "VERTEX_INIT_FAILED"}
    elif "VERTEX_MODEL_CLASS_UNAVAILABLE" in normalized:
        base = {"error": "VERTEX_MODEL_CLASS_UNAVAILABLE"}
    elif "VERTEX_SDK_NOT_AVAILABLE" in normalized:
        base = {"error": "VERTEX_SDK_NOT_AVAILABLE"}
    elif "AI_INTERNAL_ERROR" in normalized:
        status = 500
        base = {"error": "AI_INTERNAL_ERROR"}
    # Provide status as int; some type checkers expect str values for JSON but FastAPI will serialize ints fine.
    base["status"] = int(status)  # type: ignore[assignment]
    return base


@router.get("/transcript-ready")
def transcript_ready(request: Request, episode_id: Optional[str] = None, hint: Optional[str] = None, session: Session = Depends(get_session)):
    """Return whether a transcript is ready.

    Accepts either:
        - episode_id (preferred), optionally with hint
        - or just hint (filename stem) when an Episode row isn't available yet
    """
    # If no episode_id, we still leverage the hint-only discovery path inside
    # _discover_transcript_for_episode by passing a dummy ID that won't resolve
    # to an Episode, which triggers the hint fallback branch.
    eid = episode_id if episode_id else "00000000-0000-0000-0000-000000000000"
    p = _discover_transcript_for_episode(session, str(eid), hint)
    return {"ready": bool(p), "transcript_path": p}


@router.get("/intent-hints")
def intent_hints(
    request: Request,
    episode_id: Optional[str] = None,
    hint: Optional[str] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return detected command keywords for a transcript."""

    path = _discover_transcript_json_path(session, episode_id, hint)
    if not path:
        raise HTTPException(status_code=409, detail="TRANSCRIPT_NOT_READY")

    try:
        words = load_transcript_json(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="TRANSCRIPT_NOT_FOUND")
    except Exception as exc:  # pragma: no cover - unexpected parse errors
        _log.warning("[intent-hints] failed to load transcript %s: %s", path, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="TRANSCRIPT_LOAD_ERROR")

    commands_cfg = get_user_commands(current_user)
    sfx_entries = list(_gather_user_sfx_entries(session, current_user))
    intents = analyze_intents(words, commands_cfg, sfx_entries)

    return {
        "ready": True,
        "transcript": path.name,
        "intents": intents,
    }
