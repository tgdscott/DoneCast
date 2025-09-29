import logging
from pathlib import Path
from typing import List

from sqlmodel import select
from uuid import UUID

from .app import celery_app
from api.core.database import get_session
from api.core.paths import FINAL_DIR, MEDIA_DIR
from api.models.podcast import Episode
from pydub import AudioSegment

def _normalize_cuts(cuts: List[dict]) -> List[dict]:
    try:
        normalized = []
        for cut in cuts or []:
            try:
                start_ms = int((cut.get('start_ms') or 0))
                end_ms = int((cut.get('end_ms') or 0))
            except Exception:
                continue
            if end_ms > start_ms and (end_ms - start_ms) >= 20:
                normalized.append({'start_ms': start_ms, 'end_ms': end_ms})
        normalized.sort(key=lambda item: item['start_ms'])
        merged: List[dict] = []
        for cut in normalized:
            if not merged or cut['start_ms'] > merged[-1]['end_ms']:
                merged.append(cut)
            else:
                merged[-1]['end_ms'] = max(merged[-1]['end_ms'], cut['end_ms'])
        return merged
    except Exception:
        return []

@celery_app.task(name="manual_cut_episode")
def manual_cut_episode(episode_id: str, cuts: List[dict]):
    """Remove the specified cut ranges from the episode's final audio and write a new final file.

    Cuts are objects: { start_ms, end_ms } representing segments to REMOVE.
    """
    log = logging.getLogger("ppp.tasks.manual_cut")
    session = next(get_session())
    try:
        ep = session.exec(select(Episode).where(Episode.id == UUID(str(episode_id)))).first()
    except Exception:
        ep = None
    if not ep:
        log.error("manual_cut_episode: episode not found %s", episode_id)
        return {"ok": False, "error": "episode not found"}

    # Resolve source final path
    src_name = None
    try:
        if getattr(ep, 'final_audio_path', None):
            src_name = Path(str(ep.final_audio_path)).name
    except Exception:
        src_name = None
    if not src_name:
        log.error("manual_cut_episode: no final audio path for episode %s", episode_id)
        return {"ok": False, "error": "no final audio"}

    src_path = FINAL_DIR / src_name
    if not src_path.is_file():
        # try media dir as fallback
        alt = MEDIA_DIR / src_name
        if alt.is_file():
            src_path = alt
    if not src_path.is_file():
        log.error("manual_cut_episode: source file not found %s", str(src_path))
        return {"ok": False, "error": "source file missing"}

    # Load and apply cuts
    try:
        audio = AudioSegment.from_file(src_path)
        length = len(audio)
    except Exception as ex:
        log.exception("manual_cut_episode: failed to load audio")
        return {"ok": False, "error": f"load failed: {ex}"}

    merged = _normalize_cuts(cuts)
    if not merged:
        return {"ok": True, "message": "no cuts to apply", "final_audio_path": str(ep.final_audio_path), "duration_ms": length}

    # Clamp to bounds
    to_remove = []
    for c in merged:
        s = max(0, min(length, int(c['start_ms'])))
        e = max(0, min(length, int(c['end_ms'])))
        if e > s:
            to_remove.append((s, e))
    to_remove.sort(key=lambda x: x[0])
    if not to_remove:
        return {"ok": True, "message": "no valid cuts after clamp", "final_audio_path": str(ep.final_audio_path), "duration_ms": length}

    # Build kept segments
    kept = []
    cur = 0
    for s, e in to_remove:
        if s > cur:
            kept.append(audio[cur:s])
        cur = e
    if cur < length:
        kept.append(audio[cur:length])
    try:
        result = kept[0]
        for seg in kept[1:]:
            result += seg
    except Exception:
        result = audio  # fallback (shouldn't happen)

    # Write new final file next to FINAL_DIR
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    base_stem = Path(src_name).stem
    out_name = f"{base_stem}-cut.mp3"
    out_path = FINAL_DIR / out_name
    # Avoid overwriting by incrementing suffix
    idx = 1
    while out_path.exists() and idx < 100:
        out_path = FINAL_DIR / f"{base_stem}-cut-{idx}.mp3"
        idx += 1
    try:
        result.export(out_path, format="mp3")
    except Exception as ex:
        log.exception("manual_cut_episode: export failed")
        return {"ok": False, "error": f"export failed: {ex}"}

    # Update episode
    try:
        ep.final_audio_path = out_path.name
        try:
            ep.duration_ms = len(result)
        except Exception:
            pass
        session.add(ep)
        session.commit()
    except Exception:
        session.rollback()
        log.exception("manual_cut_episode: failed to update episode")
        return {"ok": False, "error": "db update failed"}

    return {"ok": True, "final_audio_path": out_path.name, "duration_ms": len(result)}


