from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from pydub import AudioSegment

from api.services import transcription
from api.services.audio.common import MEDIA_DIR, sanitize_filename
from api.core.paths import (
    FINAL_DIR as _FINAL_DIR,
    CLEANED_DIR as _CLEANED_DIR,
    TRANSCRIPTS_DIR as _TRANSCRIPTS_DIR,
    WS_ROOT as _WS_ROOT,
)
from api.services.audio.transcript_io import write_working_json

from .transcripts import (
    build_phrases,
    write_phrase_txt,
    write_nopunct_sidecar,
)

OUTPUT_DIR = _FINAL_DIR
CLEANED_DIR = _CLEANED_DIR
TRANSCRIPTS_DIR = _TRANSCRIPTS_DIR
WS_ROOT = _WS_ROOT


def load_content_and_init_transcripts(
    main_content_filename: str,
    words_json_path: Optional[str],
    output_filename: str,
    log: List[str],
    *,
    forbid_transcribe: bool = False,
) -> Tuple[Path, AudioSegment, List[Dict[str, Any]], str]:
    raw_requested = str(main_content_filename or "").strip()
    requested = Path(raw_requested) if raw_requested else Path()
    candidates: List[Path] = []
    seen: Set[str] = set()

    def _push(path_like: Path) -> None:
        try:
            resolved = Path(path_like)
        except Exception:
            return
        key = str(resolved)
        if key in seen:
            return
        seen.add(key)
        candidates.append(resolved)

    def _append_log(entry: str) -> None:
        try:
            if callable(log):  # type: ignore[call-overload]
                log(entry)  # type: ignore[misc]
            elif isinstance(log, list):
                log.append(entry)
        except Exception:
            pass

    if raw_requested:
        if requested.is_absolute():
            _push(requested)
        else:
            _push(requested)

    name_only = Path(requested.name) if requested.name else requested
    alt_names: Set[str] = set()

    def _collect_alt(name: str) -> None:
        candidate = str(name or "").strip()
        if not candidate:
            return
        alt_names.add(candidate)

    if name_only.name:
        base_name = name_only.name
        _collect_alt(base_name)
        _collect_alt(base_name.lower())
        _collect_alt(base_name.upper())
        try:
            sanitized = sanitize_filename(base_name)
            if sanitized:
                _collect_alt(sanitized)
        except Exception:
            pass
        try:
            uploader_variant = re.sub(r"[^A-Za-z0-9._-]", "_", base_name).strip("._")
            if uploader_variant:
                _collect_alt(uploader_variant)
        except Exception:
            pass

        prefix_candidates = [
            "cleaned_",
            "cleaned-",
            "precut_",
            "precut-",
            "denoised_",
            "normalized_",
            "mixdown_",
            "mixdown-",
            "mix_",
        ]
        lower_base = base_name.lower()
        for prefix in prefix_candidates:
            if lower_base.startswith(prefix):
                trimmed = base_name[len(prefix) :]
                _collect_alt(trimmed)
                _collect_alt(trimmed.lower())
                try:
                    sanitized_trim = sanitize_filename(trimmed)
                    if sanitized_trim:
                        _collect_alt(sanitized_trim)
                except Exception:
                    pass

        stems: Set[str] = set()
        try:
            if name_only.stem:
                stems.add(name_only.stem)
                stems.add(name_only.stem.lower())
        except Exception:
            pass
        for alt in list(alt_names):
            try:
                alt_path = Path(alt)
                if alt_path.stem:
                    stems.add(alt_path.stem)
                    stems.add(alt_path.stem.lower())
            except Exception:
                continue
        suffixes: Set[str] = set()
        try:
            if name_only.suffix:
                suffixes.add(name_only.suffix)
                suffixes.add(name_only.suffix.lower())
                suffixes.add(name_only.suffix.upper())
        except Exception:
            pass
        suffixes.update({".mp3", ".wav", ".m4a", ".aac"})
        for stem in stems:
            if not stem:
                continue
            for suffix in suffixes:
                try:
                    _collect_alt(f"{stem}{suffix}")
                except Exception:
                    continue

    for alt in alt_names:
        try:
            alt_path = Path(alt)
        except Exception:
            continue
        if str(alt_path) and alt_path != requested:
            _push(alt_path)
    base_roots: List[Optional[Path]] = [
        MEDIA_DIR,
        MEDIA_DIR / "media_uploads",
        CLEANED_DIR,
        WS_ROOT,
        WS_ROOT / "media_uploads",
    ]

    try:
        base_roots.append(Path.cwd() / "media_uploads")
    except Exception:
        pass

    for root in base_roots:
        try:
            if requested.is_absolute():
                _push(requested)
            if root is not None:
                if not requested.is_absolute() and str(requested):
                    _push(root / requested)
                _push(root / name_only)
                for alt in alt_names:
                    try:
                        _push(root / Path(alt))
                    except Exception:
                        continue
        except Exception:
            continue

    content_path: Optional[Path] = None
    for cand in candidates:
        try:
            if cand.exists():
                content_path = cand
                break
        except Exception:
            continue
    if content_path is None:
        search_dirs: List[Path] = []
        seen_dirs: Set[str] = set()
        for cand in candidates:
            try:
                parent = cand.parent
            except Exception:
                continue
            try:
                key = str(parent.resolve()) if parent else str(parent)
            except Exception:
                key = str(parent)
            if not key or key in seen_dirs:
                continue
            seen_dirs.add(key)
            if parent:
                search_dirs.append(parent)
        extras = [
            MEDIA_DIR,
            MEDIA_DIR / "media_uploads",
            WS_ROOT,
            WS_ROOT / "media_uploads",
        ]
        try:
            extras.extend([Path.cwd(), Path.cwd() / "media_uploads"])
        except Exception:
            pass
        for extra_root in extras:
            try:
                key = str(extra_root.resolve())
            except Exception:
                key = str(extra_root)
            if not key or key in seen_dirs:
                continue
            seen_dirs.add(key)
            search_dirs.append(extra_root)

        alt_name_lowers = {n.lower() for n in alt_names}
        alt_stems = {Path(n).stem for n in alt_names if n}
        alt_stem_lowers = {s.lower() for s in alt_stems if s}

        for directory in search_dirs:
            try:
                if not directory or not directory.exists() or not directory.is_dir():
                    continue
            except Exception:
                continue
            try:
                for entry in directory.iterdir():
                    try:
                        entry_name = entry.name
                    except Exception:
                        continue
                    lower_name = entry_name.lower()
                    entry_stem = entry.stem
                    lower_stem = entry_stem.lower() if isinstance(entry_stem, str) else ""
                    if (
                        entry_name in alt_names
                        or lower_name in alt_name_lowers
                        or entry_stem in alt_stems
                        or lower_stem in alt_stem_lowers
                    ):
                        content_path = entry
                        _append_log(
                            f"[MEDIA_FALLBACK] located main content via directory scan: {entry}"
                        )
                        break
                if content_path is not None:
                    break
            except Exception:
                continue

    if content_path is None:
        raise RuntimeError(f"Main content file not found: {main_content_filename}")
    main_content_audio = AudioSegment.from_file(content_path)
    log.append(f"Loaded main content: {main_content_filename}")

    words: List[Dict[str, Any]] = []
    if words_json_path:
        try:
            with open(words_json_path, "r", encoding="utf-8") as fh:
                words = json.load(fh)
        except Exception as e:
            raw_toggle = (
                os.getenv("ALLOW_ASSEMBLY_TRANSCRIBE")
                or os.getenv("ASSEMBLY_ALLOW_TRANSCRIBE")
                or os.getenv("ALLOW_TRANSCRIPTION")
            )
            allow = (not forbid_transcribe) and bool(
                raw_toggle and str(raw_toggle).strip().lower() in {"1", "true", "yes", "on"}
            )
            if allow:
                log.append(
                    f"[WORDS_FALLBACK] Failed to load provided words '{words_json_path}': {e}; transcribing."
                )
            else:
                log.append(
                    f"[WORDS_FALLBACK] Failed to load provided words '{words_json_path}': {e}; skipping transcription (assembly transcribe disabled)."
                )
    if not words:
        raw_toggle = (
            os.getenv("ALLOW_ASSEMBLY_TRANSCRIBE")
            or os.getenv("ASSEMBLY_ALLOW_TRANSCRIBE")
            or os.getenv("ALLOW_TRANSCRIPTION")
        )
        allow = (not forbid_transcribe) and bool(
            raw_toggle and str(raw_toggle).strip().lower() in {"1", "true", "yes", "on"}
        )
        if allow:
            try:
                words = transcription.get_word_timestamps(main_content_filename)
            except Exception as e:
                words = []
                log.append(
                    f"[WORDS_UNAVAILABLE] {type(e).__name__}: {e}; proceeding without transcript."
                )
        else:
            log.append(
                "[WORDS_UNAVAILABLE] assembly transcribe disabled; proceeding without transcript."
            )

    sanitized_output_filename = sanitize_filename(output_filename)
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        orig_txt = TRANSCRIPTS_DIR / f"{sanitized_output_filename}.original.txt"
        if not orig_txt.exists():
            phrases = build_phrases(words)
            write_phrase_txt(orig_txt, phrases)
            log.append(
                f"[TRANSCRIPTS] wrote original phrase transcript {orig_txt.name} phrases={len(phrases)}"
            )

        working_json_path = write_working_json(
            words, sanitized_output_filename, TRANSCRIPTS_DIR, log
        )

        try:
            src_json = Path(words_json_path) if words_json_path else working_json_path
            write_nopunct_sidecar(src_json, sanitized_output_filename, TRANSCRIPTS_DIR)
            log.append(
                f"[TRANSCRIPTS] wrote punctuation-sanitized JSON {sanitized_output_filename}.nopunct.json entries={len(words)}"
            )
        except Exception as e:
            try:
                if callable(log):  # type: ignore[call-overload]
                    log(f"[transcripts] failed to write nopunct sidecar: {e}")  # type: ignore[misc]
                elif isinstance(log, list):
                    log.append(f"[transcripts] failed to write nopunct sidecar: {e}")
            except Exception:
                pass
    except Exception as e:
        log.append(f"[TRANSCRIPTS_ERROR] init transcripts: {e}")

    return content_path, main_content_audio, words, sanitized_output_filename


__all__ = ["load_content_and_init_transcripts"]
