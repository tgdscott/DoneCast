from fastapi import APIRouter, Depends, HTTPException, Body, status
from typing import List, Dict, Any, Optional, cast
from pathlib import Path
import json
from uuid import UUID

from api.core.database import get_session
from api.models.podcast import Episode
from sqlmodel import select
from api.routers.auth import get_current_user
from api.models.user import User
try:
    from pydub import AudioSegment
except ImportError:
    AudioSegment = None  # type: ignore
import shutil

from api.services import flubber_helper
from api.services import transcription

from api.core.paths import MEDIA_DIR, CLEANED_DIR, FLUBBER_CTX_DIR, TRANSCRIPTS_DIR

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flubber", tags=["flubber"], responses={404: {"description": "Not found"}})

def _load_episode_meta(ep: Episode) -> Dict[str, Any]:
    base_name = (ep.final_audio_path or '')
    transcripts_dir = TRANSCRIPTS_DIR
    if not transcripts_dir.is_dir():
        return {}
    try:
        for f in transcripts_dir.glob("*.meta.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get('cleaned_audio') == base_name or data.get('original_audio') == base_name:
                return data
    except Exception:
        return {}
    return {}

def _load_ep_meta_json_field(ep: Episode) -> Dict[str, Any]:
    try:
        if getattr(ep, 'meta_json', None):
            return json.loads(ep.meta_json or "{}")
    except Exception:
        pass
    return {}

def _save_ep_meta_json_field(session, ep: Episode, meta: Dict[str, Any]):
    try:
        ep.meta_json = json.dumps(meta)
        session.add(ep)
        session.commit()
    except Exception:
        session.rollback()
        raise

@router.get("/contexts/{episode_id}", summary="List flubber context snippets for an episode")
def list_flubber_contexts(episode_id: str, session=Depends(get_session), current_user: User = Depends(get_current_user)):
    try:
        ep = session.exec(select(Episode).where(Episode.id == UUID(str(episode_id)))).first()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid episode id")
    if not ep or ep.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Episode not found")
    meta = _load_episode_meta(ep)
    stored = _load_ep_meta_json_field(ep)
    contexts = stored.get('flubber_contexts') or meta.get('flubber_contexts') or []
    out = []
    for c in contexts:
        p = Path(c.get('snippet_path',''))
        url = None
        if p.is_file():
            url = f"/static/flubber/{p.name}"
        out.append({**c, 'url': url})
    return {'episode_id': episode_id, 'count': len(out), 'contexts': out}

@router.post("/prepare/{episode_id}", status_code=status.HTTP_200_OK, summary="Prepare flubber contexts and persist in Episode.meta_json")
def prepare_flubber_contexts(
    episode_id: str,
    window_before_s: float = Body(15.0),
    window_after_s: float = Body(15.0),
    session=Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    try:
        ep = session.exec(select(Episode).where(Episode.id == UUID(str(episode_id)))).first()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid episode id")
    if not ep or ep.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Episode not found")

    # Determine source audio and words
    meta_file_data = _load_episode_meta(ep)
    source_audio_name: Optional[str] = None
    if meta_file_data.get('original_audio'):
        source_audio_name = meta_file_data['original_audio']
    elif ep.final_audio_path:
        source_audio_name = ep.final_audio_path
    if not source_audio_name:
        raise HTTPException(status_code=400, detail="Cannot determine source audio for contexts")

    # Strict: do NOT re-transcribe. If words aren't present yet, return 425 (Too Early) and let client retry later.
    try:
        stem = Path(str(source_audio_name)).stem
        tr_dir = TRANSCRIPTS_DIR
        # Prefer new naming
        tr_new = tr_dir / f"{stem}.json"
        tr_legacy = tr_dir / f"{stem}.words.json"
        tr = tr_new if tr_new.is_file() else tr_legacy
        if not tr.is_file():
            raise HTTPException(status_code=425, detail="Transcript not ready yet; please retry shortly")
        try:
            words = json.loads(tr.read_text(encoding="utf-8"))
        except Exception:
            raise HTTPException(status_code=500, detail="Corrupt transcript file; please re-run upload")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to load word timestamps for source audio")

    contexts = flubber_helper.extract_flubber_contexts(
        source_audio_name,
        words,
        window_before_s=window_before_s,
        window_after_s=window_after_s,
    )
    # Persist into Episode.meta_json
    stored = _load_ep_meta_json_field(ep)
    stored['flubber_contexts'] = contexts
    _save_ep_meta_json_field(session, ep, stored)

    out = []
    for c in contexts:
        p = Path(c.get('snippet_path',''))
        url = f"/static/flubber/{p.name}" if p.is_file() else None
        out.append({**c, 'url': url})
    return {'episode_id': episode_id, 'count': len(out), 'contexts': out}

@router.post("/apply/{episode_id}", status_code=status.HTTP_200_OK, summary="Apply flubber cuts to cleaned audio and output new cleaned variant")
def apply_flubber_cuts(
    episode_id: str,
    cuts: List[Dict[str, float]] = Body(..., description="List of cut ranges. You can provide start_ms/end_ms (preferred) or start_s/end_s. If end is omitted, it will be auto-set to 200ms after the next flubber token."),
    session=Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    try:
        ep = session.exec(select(Episode).where(Episode.id == UUID(str(episode_id)))).first()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid episode id")
    if not ep or ep.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Episode not found")
    # Resolve base audio to apply cuts: prefer working_audio_name (cleaned content), else cleaned from meta
    cleaned_dir = CLEANED_DIR
    media_dir = MEDIA_DIR
    base_audio_name = None
    if getattr(ep, 'working_audio_name', None):
        base_audio_name = ep.working_audio_name
    else:
        meta = _load_episode_meta(ep)
        base_audio_name = meta.get('cleaned_audio')
    if not base_audio_name:
        raise HTTPException(status_code=404, detail="No working/cleaned audio available for flubber cuts")
    
    # If base_audio_name is a full GCS URL, extract just the filename for local path
    original_audio_name = base_audio_name
    if base_audio_name.startswith("gs://"):
        base_audio_name = Path(base_audio_name).name
        logger.info(f"[flubber] Extracted base filename from GCS URL: {base_audio_name}")
    
    base_path = cleaned_dir / base_audio_name
    if not base_path.is_file():
        # fallback: if a copy exists in media uploads (for preview)
        alt = media_dir / base_audio_name
        if alt.is_file():
            base_path = alt
    
    # Production: Download from GCS if not found locally
    if not base_path.is_file():
        logger.info(f"[flubber] File not found locally: {base_path}, attempting GCS download...")
        try:
            import os
            from infrastructure import gcs
            from sqlmodel import select
            from api.models.podcast import MediaItem
            
            # Try to find the media item (use original_audio_name which may be full GCS URL)
            logger.info(f"[flubber] Querying database for MediaItem with filename: {original_audio_name}")
            media = session.exec(
                select(MediaItem).where(MediaItem.filename == original_audio_name)
            ).first()
            
            if media:
                logger.info(f"[flubber] MediaItem found - id: {media.id}, user_id: {media.user_id}")
                
                # MediaItem.filename can be either:
                # 1. Simple filename (legacy): "abc123.mp3"
                # 2. Full GCS URL (current): "gs://bucket/user_id/media/main_content/abc123.mp3"
                stored_filename = media.filename
                gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
                
                logger.info(f"[flubber] Stored filename in DB: {stored_filename}")
                
                if stored_filename.startswith("gs://"):
                    # Extract key from full GCS URL: gs://bucket/key/path
                    parts = stored_filename.replace("gs://", "").split("/", 1)
                    if len(parts) == 2:
                        gcs_key = parts[1]  # Everything after bucket name
                        logger.info(f"[flubber] Extracted GCS key from URL: {gcs_key}")
                    else:
                        logger.error(f"[flubber] Invalid GCS URL format: {stored_filename}")
                        raise HTTPException(status_code=500, detail="Invalid GCS URL format in database")
                else:
                    # Legacy format: construct path
                    gcs_key = f"{media.user_id.hex}/media/main_content/{stored_filename}"
                    logger.info(f"[flubber] Constructed GCS key (legacy): {gcs_key}")
                
                logger.info(f"[flubber] Downloading from GCS: gs://{gcs_bucket}/{gcs_key}")
                
                # Download from GCS
                data = gcs.download_bytes(gcs_bucket, gcs_key)
                if data:
                    logger.info(f"[flubber] GCS download successful - {len(data)} bytes received")
                    
                    # Save to local path
                    base_path.parent.mkdir(parents=True, exist_ok=True)
                    base_path.write_bytes(data)
                    logger.info(f"[flubber] File written to local cache: {base_path} ({base_path.stat().st_size} bytes)")
                    # File now exists locally
                else:
                    logger.error(f"[flubber] GCS download returned no data for: gs://{gcs_bucket}/{gcs_key}")
                    raise HTTPException(status_code=404, detail="Working audio file not found in GCS")
            else:
                logger.error(f"[flubber] MediaItem not found in database for filename: {original_audio_name}")
                raise HTTPException(status_code=404, detail="Working audio file missing")
        except HTTPException:
            raise
        except Exception as e:
            logger.error("[flubber] Failed to download from GCS: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to retrieve file: {str(e)}")
    
    # Final check
    if not base_path.is_file():
        logger.error(f"[flubber] Audio file still missing after download attempt: {base_path}")
        raise HTTPException(status_code=404, detail="Working audio file missing")
    
    logger.info(f"[flubber] Audio file ready: {base_path}")
    
    if AudioSegment is None:
        logger.error("[flubber] AudioSegment is None - pydub not installed")
        raise HTTPException(status_code=503, detail="Audio processing unavailable (pydub not installed)")
    
    logger.info(f"[flubber] Loading audio from {base_path}...")
    try:
        audio = AudioSegment.from_file(base_path)
        logger.info(f"[flubber] Audio loaded successfully - duration: {len(audio)}ms, channels: {audio.channels}, frame_rate: {audio.frame_rate}")
    except Exception as exc:
        logger.error(f"[flubber] Failed to load audio from {base_path}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load audio: {str(exc)}")
    # Helper to load words for this audio (prefer precomputed transcript if available)
    def _load_words_for_audio(name: str) -> List[Dict[str, Any]]:
        stem = Path(name).stem
        tr_dir = TRANSCRIPTS_DIR
        tr_new = tr_dir / f"{stem}.json"
        tr_legacy = tr_dir / f"{stem}.words.json"
        tr = tr_new if tr_new.is_file() else tr_legacy
        if tr.is_file():
            try:
                return json.loads(tr.read_text(encoding="utf-8"))
            except Exception:
                return []
        # No fallback transcription here by design
        return []

    def _is_flubber(tok: str) -> bool:
        t = (tok or "").strip().lower()
        if not t:
            return False
        if t == "flubber":
            return True
        # fuzzy equivalence (common STT variants)
        try:
            import difflib
            return difflib.SequenceMatcher(a=t, b="flubber").ratio() >= 0.8
        except Exception:
            return False

    words: List[Dict[str, Any]] = []
    intervals = []
    for c in cuts:
        # Accept start/end in seconds or milliseconds; end may be omitted for auto mode
        has_ms = ('start_ms' in c) or ('end_ms' in c)
        s = None; e = None
        try:
            if has_ms:
                if 'start_ms' in c:
                    s = float(c['start_ms'])/1000.0
                elif 'start_s' in c:
                    s = float(c['start_s'])
                if 'end_ms' in c:
                    e = float(c['end_ms'])/1000.0
                elif 'end_s' in c:
                    e = float(c['end_s'])
            else:
                # seconds
                if 'start_s' in c and c.get('start_s') is not None:
                    _vs = c.get('start_s')
                    s = float(cast(float, _vs))
                if 'end_s' in c and c.get('end_s') is not None:
                    _ve = c.get('end_s')
                    e = float(cast(float, _ve))
        except Exception:
            s = None; e = None
        if s is None:
            raise HTTPException(status_code=400, detail="Each cut requires at least start_s or start_ms")
        if e is None:
            # Auto-compute end: 200ms after the next flubber token at/after s
            if not words:
                words = _load_words_for_audio(base_audio_name)
            # Find the first flubber starting at or after s
            end_found = None
            for w in words:
                try:
                    w_start = float(w.get('start', 0.0))
                    w_end = float(w.get('end', w_start))
                    if w_end < s:
                        continue
                    if _is_flubber(str(w.get('word', ''))):
                        end_found = max(w_end + 0.200, s)  # ensure end >= start
                        break
                except Exception:
                    continue
            if end_found is None:
                raise HTTPException(status_code=400, detail="Could not auto-determine end: no flubber found after start")
            e = end_found
        if e <= s:
            continue
        intervals.append((max(0.0, s), max(0.0, e)))
    intervals.sort()
    merged = []
    for s,e in intervals:
        if not merged or s > merged[-1][1] + 1e-3:
            merged.append([s,e])
        else:
            merged[-1][1] = max(merged[-1][1], e)
    if AudioSegment is None:
        raise HTTPException(status_code=503, detail="Audio processing unavailable (pydub not installed)")
    cursor_ms = 0
    out_audio = AudioSegment.empty()
    removed_ms = 0
    for s,e in merged:
        s_ms = int(s*1000); e_ms = int(e*1000)
        if s_ms > cursor_ms:
            out_audio += audio[cursor_ms:s_ms]
        if e_ms > s_ms:
            removed_ms += (e_ms - s_ms)
        cursor_ms = e_ms
    if cursor_ms < len(audio):
        out_audio += audio[cursor_ms:]
    # Export to cleaned_audio and also copy to media_uploads for preview via /static/media
    new_name = (base_path.stem + "_flubberfix.mp3") if base_path.suffix else (str(base_path.name) + "_flubberfix.mp3")
    new_path = cleaned_dir / new_name
    out_audio.export(new_path, format="mp3")
    # Best-effort copy to media for URL access
    try:
        shutil.copyfile(new_path, media_dir / new_name)
    except Exception:
        pass
    # Persist working_audio_name and flubber_cuts_ms into Episode.meta_json
    stored = _load_ep_meta_json_field(ep)
    # store as ms tuples for precision
    stored['flubber_cuts_ms'] = [(int(s*1000), int(e*1000)) for s, e in merged]
    ep.working_audio_name = new_name
    _save_ep_meta_json_field(session, ep, stored)
    return {
        'episode_id': episode_id,
        'applied_cuts': merged,
        'removed_ms': removed_ms,
        'working_audio_name': new_name,
        'working_audio_url': f"/static/media/{new_name}"
    }


@router.post("/prepare-by-file", status_code=status.HTTP_200_OK, summary="Prepare flubber contexts by uploaded filename (pre-episode)")
def prepare_flubber_by_file(
    payload: Dict[str, Any] = Body(..., description="{ filename, window_before_s?, window_after_s?, intents?: { flubber?: 'yes'|'no'|'unknown' }, fuzzy_threshold?: number (e.g., 0.75 or 75), insist?: boolean, retry_after_s?: number }"),
    current_user: User = Depends(get_current_user)
):
    """Generate flubber context snippets for a raw uploaded file before an Episode exists.

    Returns contexts with snippet URLs; does not persist to Episode.meta_json.
    """
    filename = (payload or {}).get('filename')
    if not filename or not isinstance(filename, str):
        raise HTTPException(status_code=400, detail="filename is required")
    window_before_s = float((payload or {}).get('window_before_s', 15.0))
    window_after_s = float((payload or {}).get('window_after_s', 15.0))
    # Uploaded files live under media_uploads with user prefix; validate existence
    src = MEDIA_DIR / filename
    if not src.is_file():
        raise HTTPException(status_code=404, detail="uploaded file not found")
    # Obtain word timestamps; prefer existing transcript if present
    try:
        stem = Path(filename).stem
        tr_dir = TRANSCRIPTS_DIR
        tr_new = tr_dir / f"{stem}.json"
        tr_legacy = tr_dir / f"{stem}.words.json"
        tr = tr_new if tr_new.is_file() else tr_legacy
        if tr.is_file():
            try:
                words = json.loads(tr.read_text(encoding="utf-8"))
            except Exception:
                raise HTTPException(status_code=500, detail="Corrupt transcript file; please re-run upload")
        else:
            # No cached transcript yet: attempt on-demand transcription to avoid user-visible stalls
            try:
                words = transcription.get_word_timestamps(filename)
                # Best-effort cache to transcripts to speed up subsequent calls
                try:
                    tr_dir.mkdir(exist_ok=True)
                    (tr_new).write_text(json.dumps(words), encoding="utf-8")
                except Exception:
                    pass
            except Exception:
                # If on-demand transcription fails, signal the client to retry later
                from fastapi import Response
                headers = {"Retry-After": str(int((payload or {}).get('retry_after_s', 2))) }
                raise HTTPException(status_code=425, detail="Transcript not ready yet; please retry shortly", headers=headers)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to fetch word timestamps for uploaded file")
    # Extract contexts into flubber_contexts dir and build URLs
    intents = (payload or {}).get('intents') or {}
    user_says_flubber = str((intents.get('flubber') if isinstance(intents, dict) else '') or '').lower()
    fuzzy_threshold = None
    try:
        if 'fuzzy_threshold' in (payload or {}):
            val = (payload or {}).get('fuzzy_threshold')
            if val is not None:
                fv = float(val)
                # Accept percent (e.g., 65) or ratio (0.65)
                if fv > 1.5 and fv <= 100.0:
                    fv = fv / 100.0
                fuzzy_threshold = fv
    except Exception:
        fuzzy_threshold = None
    # Decide matching strategy
    force_fuzzy = isinstance(fuzzy_threshold, float)
    contexts = []
    try:
        # If caller provided a threshold, honor it directly
        if force_fuzzy:
            contexts = flubber_helper.extract_flubber_contexts(
                filename,
                words,
                window_before_s=window_before_s,
                window_after_s=window_after_s,
                fuzzy=True,
                fuzzy_threshold=fuzzy_threshold,  # type: ignore[arg-type]
            )
        else:
            # First pass: exact only
            contexts = flubber_helper.extract_flubber_contexts(
                filename,
                words,
                window_before_s=window_before_s,
                window_after_s=window_after_s,
                fuzzy=False,
            )
            # If user said yes and we found nothing, retry once with default fuzzy
            if user_says_flubber == 'yes' and not contexts:
                contexts = flubber_helper.extract_flubber_contexts(
                    filename,
                    words,
                    window_before_s=window_before_s,
                    window_after_s=window_after_s,
                    fuzzy=True,
                    fuzzy_threshold=0.8,
                )
    except Exception:
        contexts = []
    out = []
    for c in contexts:
        p = Path(c.get('snippet_path',''))
        url = f"/static/flubber/{p.name}" if p.is_file() else None
        out.append({**c, 'url': url})
    # Insist policy: by default, surface 425 to encourage the client to retry until found
    insist = True if (payload is None or 'insist' not in payload) else bool(payload.get('insist'))
    if insist and not out:
        headers = {"Retry-After": str(int((payload or {}).get('retry_after_s', 2))) }
        raise HTTPException(status_code=425, detail="Flubber not found yet; please retry shortly", headers=headers)
    return { 'count': len(out), 'contexts': out }
