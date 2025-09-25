from pathlib import Path
from typing import List, Dict, Any
import difflib
from pydub import AudioSegment

from api.core.paths import FLUBBER_CTX_DIR, CLEANED_DIR, MEDIA_DIR

FLUBBER_CONTEXT_DIR = FLUBBER_CTX_DIR
FLUBBER_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)

def extract_flubber_contexts(
    main_content_filename: str,
    word_timestamps: List[Dict[str, Any]],
    window_before_s: float = 15.0,
    window_after_s: float = 15.0,
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
        out_path = FLUBBER_CONTEXT_DIR / out_name
        try:
            snippet.export(out_path, format="mp3")
        except Exception:
            continue
        contexts.append({
            'flubber_index': idx,
            'flubber_time_s': t,
            'flubber_end_s': t_end,
            'computed_end_s': min(duration_s, max(t_end + 0.2, t)),
            'snippet_start_s': start_s,
            'snippet_end_s': end_s,
            'snippet_path': str(out_path),
            'relative_flubber_ms': int((t - start_s) * 1000),
            'window_before_s': window_before_s,
            'window_after_s': window_after_s,
        })
    return contexts
