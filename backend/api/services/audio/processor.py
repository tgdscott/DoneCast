from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json, re

from api.services.audio.orchestrator import run_episode_pipeline
from api.core.paths import FINAL_DIR as _FINAL_DIR, CLEANED_DIR as _CLEANED_DIR, TRANSCRIPTS_DIR as _TRANSCRIPTS_DIR, AI_SEGMENTS_DIR as _AI_SEGMENTS_DIR


# Preserve module-level constants used elsewhere
OUTPUT_DIR = _FINAL_DIR
AI_SEGMENTS_DIR = _AI_SEGMENTS_DIR
CLEANED_DIR = _CLEANED_DIR
TRANSCRIPTS_DIR = _TRANSCRIPTS_DIR

# Private helper: write nopunct sidecar next to the canonical transcript JSON
_NOPUNCT_RE = re.compile(r"[^\w\s']+", flags=re.UNICODE)

def _write_nopunct_sidecar_from_main(main_json_path: Path) -> Path:
    """
    Given the canonical transcript JSON (e.g. TRANSCRIPTS_DIR/<slug>.json),
    write a nopunct sidecar at TRANSCRIPTS_DIR/<slug>.nopunct.json where each token's 'word'
    has punctuation removed (keeping letters/digits/underscore/space/apostrophe).
    Returns the sidecar path. Raises on I/O/JSON errors.
    """
    main_json_path = Path(main_json_path)
    out_path = main_json_path.with_suffix(".nopunct.json")
    words = json.loads(main_json_path.read_text(encoding="utf-8"))
    out_words = []
    for w in words:
        w2 = dict(w)
        if isinstance(w2.get("word"), str):
            w2["word"] = _NOPUNCT_RE.sub("", w2["word"])
        out_words.append(w2)
    out_path.write_text(json.dumps(out_words, ensure_ascii=False), encoding="utf-8")
    return out_path


class StreamingLog(list):
    """A list-like logger that also appends each entry to a file immediately."""
    def __init__(self, file_path: Path):
        super().__init__()
        self.file_path = file_path
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    def append(self, item: str):  # type: ignore[override]
        try:
            super().append(item)
        finally:
            try:
                with open(self.file_path, 'a', encoding='utf-8') as fh:
                    fh.write((str(item or '').replace('\n',' ') + '\n'))
            except Exception:
                pass


class AudioProcessingError(Exception):
    pass


def process_and_assemble_episode(
    template: Any,
    main_content_filename: str,
    output_filename: str,
    cleanup_options: Dict[str, Any],
    tts_overrides: Dict[str, str],
    cover_image_path: Optional[str] = None,
    elevenlabs_api_key: Optional[str] = None,
    tts_provider: str = "elevenlabs",
    *,
    mix_only: bool = False,
    words_json_path: Optional[str] = None,
    log_path: Optional[str] = None,
) -> Tuple[Path, List[str], List[str]]:
    """Thin façade that delegates to the orchestrator (AP-8B).

    Canonical entry-point has moved to api.services.audio.orchestrator.run_episode_pipeline().
    This façade remains for compatibility and is slated for removal after 2025-10-15.
    Preserves the public API and return shape used by callers.
    """
    # Prepare log object consistent with previous behavior
    if log_path:
        try:
            log: List[str] = StreamingLog(Path(log_path))  # type: ignore[assignment]
        except Exception:
            log = []
    else:
        log = []

    # Build paths and cfg dicts for the orchestrator
    paths: Dict[str, Any] = {
        "template": template,
        "audio_in": main_content_filename,
        "output_name": output_filename,
        "words_json": words_json_path,
        "cover_art": cover_image_path,
        "log_path": log_path,
    }
    cfg: Dict[str, Any] = {
        "cleanup_options": cleanup_options or {},
        "tts_overrides": tts_overrides or {},
        "tts_provider": tts_provider,
        "elevenlabs_api_key": elevenlabs_api_key,
        "mix_only": bool(mix_only),
        # Forbid fallback transcription during assembly; only explicit env overrides will allow it
        "forbid_transcribe": True,
    }

    # Delegate to the orchestrator and adapt the return to the legacy tuple
    try:
        out = run_episode_pipeline(paths, cfg, log)

        # Ensure nopunct sidecar exists for the canonical transcript
        try:
            episode_slug = output_filename
            main_path = TRANSCRIPTS_DIR / f"{episode_slug}.json"
            sidecar = main_path.with_suffix(".nopunct.json")
            if main_path.exists() and not sidecar.exists():
                _write_nopunct_sidecar_from_main(main_path)
                try:
                    if callable(log):  # support callable log
                        log(f"[transcripts] wrote sidecar {sidecar}")  # type: ignore[misc]
                    elif isinstance(log, list):  # typical list logger
                        log.append(f"[transcripts] wrote sidecar {sidecar}")
                except Exception:
                    pass
        except Exception as e:
            try:
                if callable(log):
                    log(f"[transcripts] failed to write nopunct sidecar: {e}")  # type: ignore[misc]
                elif isinstance(log, list):
                    log.append(f"[transcripts] failed to write nopunct sidecar: {e}")
            except Exception:
                pass
    except RuntimeError as e:
        # Preserve historical exception type surfaced by processor
        raise AudioProcessingError(str(e))

    fp = out.get("final_path")
    if isinstance(fp, Path):
        final_path = fp
    elif isinstance(fp, str):
        final_path = Path(fp)
    else:
        raise AudioProcessingError("orchestrator did not return final_path")

    log_list = out.get("log", log)
    ai_note_additions = out.get("ai_note_additions", [])
    return final_path, log_list, ai_note_additions
