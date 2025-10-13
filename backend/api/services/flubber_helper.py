from pathlib import Path
from typing import List, Dict, Any
import difflib
import logging
import os
from pydub import AudioSegment

from api.core.paths import FLUBBER_CTX_DIR, CLEANED_DIR, MEDIA_DIR

FLUBBER_CONTEXT_DIR = FLUBBER_CTX_DIR
FLUBBER_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)

_LOG = logging.getLogger(__name__)

def extract_flubber_contexts(
    main_content_filename: str,
    word_timestamps: List[Dict[str, Any]],
    window_before_s: float = 15.0,
    window_after_s: float = 10.0,
    *,
    fuzzy: bool = False,
    fuzzy_threshold: float = 0.8,
) -> List[Dict[str, Any]]:
    """Produce context audio snippets around each 'flubber' token without attempting rollback.

    Returns list of dicts with snippet file paths and timing metadata for manual UI trimming.
    """
    # Resolve audio either from cleaned_audio or media_uploads
    base = Path(main_content_filename)
    candidates = [
        CLEANED_DIR / base.name,
        MEDIA_DIR / base.name,
        base if base.is_absolute() else Path(".") / base,
    ]
    audio_path = None
    for c in candidates:
        if c.is_file():
            audio_path = c
            break
    if not audio_path:
        return []
    try:
        audio = AudioSegment.from_file(audio_path)
    except Exception:
        return []

    duration_s = len(audio) / 1000.0
    contexts: List[Dict[str, Any]] = []
    target = 'flubber'
    def is_match(tok: str) -> bool:
        t = (tok or '').strip().lower()
        if not t:
            return False
        if t == target:
            return True
        if not fuzzy:
            return False
        # Fuzzy compare for common STT mishears (e.g., "flober", "rubber", "flubber。")
        try:
            ratio = difflib.SequenceMatcher(a=t, b=target).ratio()
        except Exception:
            return False
        try:
            thr = float(fuzzy_threshold)
        except Exception:
            thr = 0.8
        # Clamp sane range
        if thr < 0.5:
            thr = 0.5
        if thr > 0.95:
            thr = 0.95
        return ratio >= thr

    flubber_indices = [i for i,w in enumerate(word_timestamps) if is_match(str(w.get('word','')))]
    for idx in flubber_indices:
        fl_word = word_timestamps[idx]
        t = float(fl_word.get('start', 0.0))
        t_end = float(fl_word.get('end', t))
        start_s = max(0.0, t - window_before_s)
        end_s = min(duration_s, t + window_after_s)
        start_ms = int(start_s * 1000)
        end_ms = int(end_s * 1000)
        snippet = audio[start_ms:end_ms]
        out_name = f"flubber_{int(start_ms)}_{int(end_ms)}.mp3"
        
        # Export to /tmp temporarily
        tmp_path = FLUBBER_CONTEXT_DIR / out_name
        try:
            _LOG.info(f"[flubber_helper] Exporting snippet to /tmp: {out_name}")
            snippet.export(tmp_path, format="mp3")
            _LOG.info(f"[flubber_helper] Snippet exported - size: {tmp_path.stat().st_size} bytes")
        except Exception as exc:
            _LOG.error(f"[flubber_helper] Failed to export snippet: {exc}", exc_info=True)
            continue
        
        # Upload to GCS and generate signed URL
        audio_url = None
        try:
            from infrastructure import gcs
            gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
            gcs_key = f"flubber_snippets/{out_name}"
            
            _LOG.info(f"[flubber_helper] Uploading snippet to GCS: gs://{gcs_bucket}/{gcs_key}")
            with open(tmp_path, "rb") as f:
                file_data = f.read()
            gcs.upload_bytes(gcs_bucket, gcs_key, file_data, content_type="audio/mpeg")
            _LOG.info(f"[flubber_helper] Snippet uploaded to GCS successfully")
            
            # Generate signed URL (valid for 1 hour)
            audio_url = gcs.get_signed_url(gcs_bucket, gcs_key, expiration=3600)
            _LOG.info(f"[flubber_helper] Generated signed URL for snippet: {audio_url}")
            
            # Clean up local file
            try:
                tmp_path.unlink(missing_ok=True)
            except:
                pass
        except Exception as exc:
            _LOG.error(f"[flubber_helper] Failed to upload snippet to GCS: {exc}", exc_info=True)
            # Fall back to local path if GCS upload fails
            audio_url = f"/static/flubber/{out_name}"
        
        contexts.append({
            'flubber_index': idx,
            'flubber_time_s': t,
            'flubber_end_s': t_end,
            'computed_end_s': min(duration_s, max(t_end + 0.2, t)),
            'snippet_start_s': start_s,
            'snippet_end_s': end_s,
            'snippet_path': str(tmp_path),  # Keep for backward compat
            'audio_url': audio_url,  # NEW: GCS signed URL
            'relative_flubber_ms': int((t - start_s) * 1000),
            'window_before_s': window_before_s,
            'window_after_s': window_after_s,
        })
    return contexts
