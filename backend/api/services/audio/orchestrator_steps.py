from __future__ import annotations

"""
Extracted step helpers for the audio orchestrator.

These mirror contiguous blocks from orchestrator.run_episode_pipeline, preserving
log messages, filenames, and control flow. No behavior changes.

Note: orchestrator.py is intentionally not modified yet; these helpers prepare
for a later wiring step and can be used by other callers for granular ops.
"""

import audioop
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast, Set

from pydub import AudioSegment

from api.services import transcription, ai_enhancer
from api.services.audio.common import MEDIA_DIR, match_target_dbfs, sanitize_filename
from api.core.paths import (
    FINAL_DIR as _FINAL_DIR,
    CLEANED_DIR as _CLEANED_DIR,
    TRANSCRIPTS_DIR as _TRANSCRIPTS_DIR,
    AI_SEGMENTS_DIR as _AI_SEGMENTS_DIR,
    WS_ROOT as _WS_ROOT,
)
from api.services.audio.commands import execute_intern_commands, handle_flubber
from api.services.audio.flubber_pipeline import (
    build_flubber_contexts,
    compute_flubber_spans,
    normalize_and_merge_spans,
)
from api.services.audio.intern_pipeline import (
    build_intern_prompt,
    select_sfx_markers,
    annotate_words_with_sfx,
)
from api.services.audio.cleanup import rebuild_audio_from_words
from api.services.audio.silence_pipeline import compress_long_pauses_guarded
from api.services.audio.filler_pipeline import remove_fillers as remove_fillers_from_pipeline
from api.services.audio.silence_pipeline import (
    detect_pauses as detect_silence_pauses,
    guard_and_pad as guard_and_pad_pauses,
    retime_words as retime_words_for_pauses,
)
from api.services.audio.tts_pipeline import (
    chunk_prompt_for_tts,
    synthesize_chunks,
)
from api.services.audio.transcript_io import write_working_json
from api.services.audio.audio_export import (
    normalize_master,
    mux_tracks,
    write_derivatives,
    embed_metadata,
)


# Export/IO dirs (centralized under workspace root)
OUTPUT_DIR = _FINAL_DIR
AI_SEGMENTS_DIR = _AI_SEGMENTS_DIR
CLEANED_DIR = _CLEANED_DIR
TRANSCRIPTS_DIR = _TRANSCRIPTS_DIR
WS_ROOT = _WS_ROOT

def _parse_int_env(name: str, default: int) -> int:
    try:
        raw = os.environ.get(name)
        if raw is None:
            return default
        value = int(str(raw).strip())
        if value <= 0:
            return default
        return value
    except Exception:
        return default


def _format_bytes(num: int) -> str:
    units = ["bytes", "KiB", "MiB", "GiB", "TiB"]
    n = float(num)
    for unit in units:
        if n < 1024.0 or unit == units[-1]:
            if unit == "bytes":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} {units[-1]}"


def _format_ms(ms: int) -> str:
    return _fmt_ts(max(0.0, ms) / 1000.0)


MAX_MIX_BUFFER_BYTES = _parse_int_env("CLOUDPOD_MAX_MIX_BUFFER_BYTES", 2 * 1024 * 1024 * 1024)  # 2 GB - supports ~3.4 hours audio
BACKGROUND_LOOP_CHUNK_MS = 30_000  # mix background music in 30s chunks to cap allocations


class TemplateTimelineTooLargeError(RuntimeError):
    """Raised when template offsets require an impractically large mix timeline."""


def _estimate_mix_bytes(duration_ms: int, frame_rate: int, channels: int, sample_width: int) -> int:
    if duration_ms <= 0:
        return 0
    frames = int(math.ceil(duration_ms * frame_rate / 1000.0))
    return frames * max(1, channels) * max(1, sample_width)


def _raise_timeline_limit(
    *,
    duration_ms: int,
    bytes_needed: int,
    limit_bytes: int,
    placements: List[Tuple[dict, AudioSegment, int, int]],
) -> None:
    label = None
    start_ms = 0
    end_ms = duration_ms
    if placements:
        seg, _aud, st_ms, en_ms = max(placements, key=lambda item: item[3])
        label = str(
            seg.get("name")
            or seg.get("title")
            or (seg.get("source") or {}).get("label")
            or (seg.get("source") or {}).get("filename")
            or seg.get("segment_type")
            or "segment"
        )
        start_ms = st_ms
        end_ms = en_ms
    msg = (
        "Template timeline requires "
        f"{_format_bytes(bytes_needed)} of PCM (> {_format_bytes(limit_bytes)} limit) "
        f"for a {_format_ms(duration_ms)} mix."
    )
    if label is not None:
        msg += (
            f" Longest placement '{label}' spans {_format_ms(start_ms)}–{_format_ms(end_ms)}."
        )
    msg += " Adjust template offsets or shorten background rules to continue."
    raise TemplateTimelineTooLargeError(msg)


class _StreamingMixBuffer:
    """Accumulate overlays directly into a mutable PCM buffer.

    This avoids materializing a giant ``AudioSegment`` for the entire duration at each
    overlay step, which previously doubled memory pressure during template mixing.
    """

    def __init__(
        self,
        frame_rate: int,
        channels: int,
        sample_width: int,
        *,
        initial_duration_ms: int = 0,
        limit_bytes: Optional[int] = None,
    ) -> None:
        self.frame_rate = max(1, int(frame_rate))
        self.channels = max(1, int(channels))
        self.sample_width = max(1, int(sample_width))
        self._limit_bytes = int(limit_bytes or MAX_MIX_BUFFER_BYTES)
        # Delay allocating the backing store until we actually mix audio. Large
        # episodes (60+ minutes) can require hundreds of megabytes of PCM data;
        # eagerly reserving the full duration caused Cloud Run instances to run
        # out of memory before mixing even started. Track the requested duration
        # so we can pad with silence when exporting, but start with an empty
        # buffer.
        self._buffer = bytearray()
        self._capacity_frames = 0
        self._min_frame = self._ms_to_frames(initial_duration_ms)
        self._final_frame = self._min_frame

    def _ms_to_frames(self, ms: int) -> int:
        if ms <= 0:
            return 0
        return int(math.ceil(ms * self.frame_rate / 1000.0))

    def _ms_to_start_frame(self, ms: int) -> int:
        if ms <= 0:
            return 0
        return int(math.floor(ms * self.frame_rate / 1000.0))

    def _ensure_capacity(self, end_frame: int) -> None:
        if end_frame <= self._capacity_frames:
            return
        needed_bytes = end_frame * self.channels * self.sample_width
        if needed_bytes > self._limit_bytes:
            raise TemplateTimelineTooLargeError(
                (
                    "Mix buffer requires "
                    f"{_format_bytes(needed_bytes)} (> {_format_bytes(self._limit_bytes)})"
                )
            )
        if needed_bytes > len(self._buffer):
            try:
                self._buffer.extend(b"\x00" * (needed_bytes - len(self._buffer)))
            except MemoryError as exc:
                raise MemoryError(
                    f"streaming mix buffer cannot allocate {needed_bytes} bytes"
                ) from exc
        self._capacity_frames = end_frame

    def overlay(self, segment: AudioSegment, position_ms: int, *, label: str = "segment") -> None:
        seg = (
            segment.set_frame_rate(self.frame_rate)
            .set_channels(self.channels)
            .set_sample_width(self.sample_width)
        )
        raw = seg.raw_data
        if not raw:
            return
        start_frame = max(0, self._ms_to_start_frame(position_ms))
        start_byte = start_frame * self.channels * self.sample_width
        frames = len(raw) // (self.channels * self.sample_width)
        end_frame = start_frame + frames
        try:
            self._ensure_capacity(end_frame)
        except TemplateTimelineTooLargeError as exc:
            start_ms = int(start_frame * 1000.0 / self.frame_rate)
            end_ms = int(end_frame * 1000.0 / self.frame_rate)
            raise TemplateTimelineTooLargeError(
                (
                    f"Mix placement '{label}' spanning {_format_ms(start_ms)}–{_format_ms(end_ms)} "
                    "exceeds the configured mix buffer limit. "
                    "Reduce template offsets or shorten background music spans."
                )
            ) from exc
        end_byte = start_byte + len(raw)
        existing = bytes(self._buffer[start_byte:end_byte])
        if len(existing) < len(raw):
            existing = existing + b"\x00" * (len(raw) - len(existing))
        mixed = audioop.add(existing, raw, self.sample_width)
        self._buffer[start_byte:end_byte] = mixed
        self._final_frame = max(self._final_frame, end_frame)

    def to_segment(self) -> AudioSegment:
        target_frames = max(self._final_frame, self._min_frame)
        if target_frames > self._capacity_frames:
            self._ensure_capacity(target_frames)
        data = bytes(
            self._buffer[: target_frames * self.channels * self.sample_width]
        )
        return AudioSegment(
            data=data,
            sample_width=self.sample_width,
            frame_rate=self.frame_rate,
            channels=self.channels,
        )


# --- Mix-time helpers for background loops ---
def _loop_chunk(seg: AudioSegment, duration_ms: int) -> AudioSegment:
    if duration_ms <= 0:
        return AudioSegment.silent(duration=0)
    seg_len = len(seg)
    if seg_len <= 0:
        return AudioSegment.silent(duration=duration_ms)
    repeat = int(math.ceil(float(duration_ms) / float(seg_len)))
    if repeat <= 1:
        return seg[:duration_ms]
    looped = seg * repeat
    return looped[:duration_ms]


def _envelope_factor(
    at_ms: int, total_ms: int, fade_in_ms: int, fade_out_ms: int
) -> float:
    if total_ms <= 0:
        return 0.0
    at_ms = max(0, min(total_ms, at_ms))
    if fade_in_ms > 0 and at_ms < fade_in_ms:
        return max(0.0, min(1.0, at_ms / float(fade_in_ms)))
    if fade_out_ms > 0 and at_ms > total_ms - fade_out_ms:
        remaining = total_ms - at_ms
        return max(0.0, min(1.0, remaining / float(fade_out_ms)))
    return 1.0


def _factor_to_db(factor: float) -> float:
    if factor <= 0.0:
        return -120.0
    return 20.0 * math.log10(factor)


def _apply_gain_ramp(segment: AudioSegment, start_factor: float, end_factor: float) -> AudioSegment:
    start_factor = max(0.0, min(1.0, start_factor))
    end_factor = max(0.0, min(1.0, end_factor))
    if abs(start_factor - end_factor) < 1e-6:
        if abs(start_factor - 1.0) < 1e-6:
            return segment
        gain_db = _factor_to_db(start_factor)
        if abs(gain_db) < 1e-6:
            return segment
        return segment.apply_gain(gain_db)
    return segment.fade(
        from_gain=_factor_to_db(start_factor),
        to_gain=_factor_to_db(end_factor),
        start=0,
        end=len(segment),
    )


# --- Shared small helpers (kept local to match orchestrator behavior) ---
def _fmt_ts(s: float) -> str:
    try:
        ms = int(max(0.0, float(s)) * 1000)
        mm = ms // 60000
        ss = (ms % 60000) / 1000.0
        return f"{mm:02d}:{ss:06.3f}"
    except Exception:
        return "00:00.000"


def _build_phrases(words_list: List[Dict[str, Any]], gap_s: float = 0.8) -> List[Dict[str, Any]]:
    phrases: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    prev_end: Optional[float] = None
    prev_speaker: Optional[str] = None
    for w in (words_list or []):
        if not isinstance(w, dict):
            continue
        txt = str((w.get('word') or '')).strip()
        if txt == '':
            continue
        st = float(w.get('start') or 0.0)
        en = float(w.get('end') or st)
        spk = (w.get('speaker') or '') or 'Speaker'
        gap = (st - float(prev_end)) if (prev_end is not None) else 0.0
        if cur is None or spk != prev_speaker or (gap_s and gap >= gap_s):
            if cur is not None:
                phrases.append(cur)
            cur = {
                'speaker': spk,
                'start': st,
                'end': en,
                'text': txt,
            }
        else:
            cur['end'] = en
            cur['text'] = (cur['text'] + ' ' + txt).strip()
        prev_end = en
        prev_speaker = spk
    if cur is not None:
        phrases.append(cur)
    return phrases


def _write_phrase_txt(path: Path, phrases: List[Dict[str, Any]]):
    lines: List[str] = []
    for p in phrases:
        lines.append(f"[{_fmt_ts(p.get('start', 0.0))} - {_fmt_ts(p.get('end', 0.0))}] {p.get('speaker','Speaker')}: {p.get('text','').strip()}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + ('\n' if lines else ''))


def _offset_phrases(phrases: List[Dict[str, Any]], offset_s: float, *, speaker_override: Optional[str] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in phrases:
        out.append({
            'speaker': speaker_override or p.get('speaker') or 'Speaker',
            'start': float(p.get('start', 0.0)) + float(offset_s or 0.0),
            'end': float(p.get('end', 0.0)) + float(offset_s or 0.0),
            'text': p.get('text', ''),
        })
    return out


# Local helper: write nopunct sidecar from a words.json file
_PUNCT_RE = re.compile(r"[^\w\s']+", flags=re.UNICODE)

def _write_nopunct_sidecar(words_json_path: Path, out_basename: str, dest_dir: Path) -> Path:
    """
    Create a sidecar transcript with punctuation removed from each token's `word`.
    Preserves start/end/speaker fields; only mutates `word`.
    Writes `<out_basename>.nopunct.json` to `dest_dir` and returns the Path.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    with open(words_json_path, "r", encoding="utf-8") as f:
        words = json.load(f)

    def _strip_punct(token: str) -> str:
        # keep letters/digits/underscore/space/apostrophe
        return _PUNCT_RE.sub("", token)

    out_words: List[Dict[str, Any]] = []
    for w in words:
        w2 = dict(w)
        if "word" in w2 and isinstance(w2["word"], str):
            w2["word"] = _strip_punct(w2["word"])
        out_words.append(w2)

    out_path = dest_dir / f"{out_basename}.nopunct.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_words, f, ensure_ascii=False)
    return out_path

# --- Step helpers ---
def load_content_and_init_transcripts(
    main_content_filename: str,
    words_json_path: Optional[str],
    output_filename: str,
    log: List[str],
    *,
    forbid_transcribe: bool = False,
) -> Tuple[Path, AudioSegment, List[Dict[str, Any]], str]:
    """Load content, obtain words, and write initial transcripts.

    Returns: (content_path, main_content_audio, words, sanitized_output_filename)
    """
    # Load content
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
            # Keep the relative path exactly as provided first for callers already pointing at MEDIA_DIR
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
                combined = f"{stem}{suffix}" if suffix else stem
                _collect_alt(combined)

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

    # Words
    words: List[Dict[str, Any]] = []
    if words_json_path:
        try:
            with open(words_json_path, 'r', encoding='utf-8') as fh:
                words = json.load(fh)
        except Exception as e:
            # Respect assembly transcribe kill-switch: do NOT auto-transcribe during assembly unless explicitly enabled.
            raw_toggle = os.getenv("ALLOW_ASSEMBLY_TRANSCRIBE") or os.getenv("ASSEMBLY_ALLOW_TRANSCRIBE") or os.getenv("ALLOW_TRANSCRIPTION")
            allow = (not forbid_transcribe) and bool(raw_toggle and str(raw_toggle).strip().lower() in {"1", "true", "yes", "on"})
            if allow:
                log.append(f"[WORDS_FALLBACK] Failed to load provided words '{words_json_path}': {e}; transcribing.")
            else:
                log.append(f"[WORDS_FALLBACK] Failed to load provided words '{words_json_path}': {e}; skipping transcription (assembly transcribe disabled).")
    if not words:
        # Only attempt on explicit opt-in
        raw_toggle = os.getenv("ALLOW_ASSEMBLY_TRANSCRIBE") or os.getenv("ASSEMBLY_ALLOW_TRANSCRIBE") or os.getenv("ALLOW_TRANSCRIPTION")
        allow = (not forbid_transcribe) and bool(raw_toggle and str(raw_toggle).strip().lower() in {"1", "true", "yes", "on"})
        if allow:
            try:
                words = transcription.get_word_timestamps(main_content_filename)
            except Exception as e:
                words = []
                log.append(f"[WORDS_UNAVAILABLE] {type(e).__name__}: {e}; proceeding without transcript.")
        else:
            log.append("[WORDS_UNAVAILABLE] assembly transcribe disabled; proceeding without transcript.")

    # Initial transcripts
    sanitized_output_filename = sanitize_filename(output_filename)
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        orig_txt = TRANSCRIPTS_DIR / f"{sanitized_output_filename}.original.txt"
        if not orig_txt.exists():
            _phr = _build_phrases(words)
            _write_phrase_txt(orig_txt, _phr)
            log.append(f"[TRANSCRIPTS] wrote original phrase transcript {orig_txt.name} phrases={len(_phr)}")

        # Write the working transcript JSON (e.g., verify-ep.json)
        working_json_path = write_working_json(words, sanitized_output_filename, TRANSCRIPTS_DIR, log)

        # Immediately attempt to write the nopunct sidecar regardless of mix_only
        try:
            src_json = Path(words_json_path) if words_json_path else working_json_path
            _write_nopunct_sidecar(src_json, sanitized_output_filename, TRANSCRIPTS_DIR)
            log.append(f"[TRANSCRIPTS] wrote punctuation-sanitized JSON {sanitized_output_filename}.nopunct.json entries={len(words)}")
        except Exception as e:
            # non-fatal: log and continue so production doesn’t break mixing if sidecar fails
            try:
                # Support both callable log and list[str]
                if callable(log):  # type: ignore[call-overload]
                    log(f"[transcripts] failed to write nopunct sidecar: {e}")  # type: ignore[misc]
                elif isinstance(log, list):
                    log.append(f"[transcripts] failed to write nopunct sidecar: {e}")
            except Exception:
                pass
    except Exception as e:
        log.append(f"[TRANSCRIPTS_ERROR] init transcripts: {e}")

    return content_path, main_content_audio, words, sanitized_output_filename


def detect_and_prepare_ai_commands(
    words: List[Dict[str, Any]],
    cleanup_options: Dict[str, Any],
    words_json_path: Optional[str],
    mix_only: bool,
    log: List[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]], int, int]:
    """Scan for intern/flubber tokens, build prompts, and finalize commands config.

    Returns: (mutable_words, commands_cfg, ai_cmds, intern_count, flubber_count)
    """
    insane_verbose = bool(cleanup_options.get('insaneVerbose') or cleanup_options.get('debugCommands'))
    force_commands = bool(cleanup_options.get('forceCommands') or cleanup_options.get('forceIntern'))
    intern_intent = str((cleanup_options.get('internIntent') or '')).strip().lower()
    flubber_intent = str((cleanup_options.get('flubberIntent') or '')).strip().lower()
    commands_cfg = cleanup_options.get('commands', {}) or {}
    orig_commands_keys = list((commands_cfg or {}).keys())
    intern_count = 0
    flubber_count = 0
    if words:
        for idx, w in enumerate(words):
            raw_tok = str((w or {}).get('word') or '').lower()
            tok = ''.join(ch for ch in raw_tok if ch.isalnum())
            if tok == 'intern':
                intern_count += 1
                if insane_verbose:
                    fwd = ' '.join([str((fw or {}).get('word') or '') for fw in words[idx+1:idx+8]])
                    log.append(f"[AI_SCAN_CTX] intern at {float((w or {}).get('start', 0.0)):.3f}s -> '{fwd[:120]}'")
            elif tok == 'flubber':
                flubber_count += 1
    log.append(f"[AI_SCAN] intern_tokens={intern_count} flubber_tokens={flubber_count}")

    if mix_only and not force_commands:
        def _allow(intent: str) -> bool:
            v = (intent or '').strip().lower()
            return v not in {"no", "false", "0"}

        new_cfg: Dict[str, Any] = {}
        if _allow(flubber_intent):
            if 'flubber' in (commands_cfg or {}) or flubber_count > 0:
                new_cfg['flubber'] = (commands_cfg or {}).get('flubber') or {'action': 'rollback_restart', 'max_lookback_words': 50}
                log.append("[AI_ENABLE_FLUBBER_BY_INTENT] mix_only=True -> flubber enabled")
        if _allow(intern_intent):
            if 'intern' in (commands_cfg or {}) or intern_count > 0:
                new_cfg['intern'] = (commands_cfg or {}).get('intern') or {'action': 'ai_command'}
                log.append("[AI_ENABLE_INTERN_BY_INTENT] mix_only=True -> intern enabled")
        else:
            if 'intern' in (commands_cfg or {}):
                log.append("[AI_DISABLED_BY_INTENT] intern config present but intent=no")
        commands_cfg = new_cfg
    elif mix_only and force_commands:
        log.append("[AI_FORCED] mix_only=True but forceCommands=True -> commands enabled")
    elif (not mix_only) and (not commands_cfg):
        commands_cfg = {
            'flubber': {'action': 'rollback_restart', 'max_lookback_words': 50},
            'intern': {'action': 'ai_command', 'keep_command_token_in_transcript': True, 'insert_pad_ms': 350},
        }
    try:
        log.append(f"[AI_CFG] mix_only={mix_only} commands_keys={list((commands_cfg or {}).keys())}")
        log.append(
            f"[AI_CFG_DETAIL] orig_cfg_keys={orig_commands_keys} force={force_commands} insane={insane_verbose} words_json={'yes' if words_json_path else 'no'}"
        )
    except Exception:
        log.append(f"[AI_CFG] mix_only={mix_only} commands_keys=?")

    mutable_words = [dict(w) for w in words]
    _sfx_markers = select_sfx_markers(mutable_words, commands_cfg, log)
    ai_cmds = build_intern_prompt(mutable_words, commands_cfg, log, insane_verbose=insane_verbose)
    log.append(f"[AI_CMDS] detected={len(ai_cmds)}")
    if (intern_count or flubber_count) and not ai_cmds:
        log.append(f"[AI_CMDS_MISMATCH] tokens_seen intern={intern_count} flubber={flubber_count} but ai_cmds=0; cfg_keys={list((commands_cfg or {}).keys())}")

    try:
        _intern_cfg = (commands_cfg or {}).get('intern') or {}
        if bool(_intern_cfg.get('remove_end_marker')):
            for _cmd in (ai_cmds or []):
                try:
                    es = _cmd.get('end_marker_start')
                    ee = _cmd.get('end_marker_end')
                    if isinstance(es, (int, float)) and isinstance(ee, (int, float)) and ee >= es:
                        for _w in (mutable_words or []):
                            try:
                                st = float((_w or {}).get('start') or 0.0)
                                if st >= float(es) and st <= float(ee):
                                    if isinstance(_w.get('word'), str):
                                        _w['word'] = ''
                            except Exception:
                                pass
                except Exception:
                    pass
    except Exception:
        pass

    try:
        mutable_words = annotate_words_with_sfx(mutable_words, _sfx_markers, log=None)
    except Exception:
        pass

    try:
        _flubber_cfg = (commands_cfg or {}).get('flubber') or {}
        _flubber_contexts = build_flubber_contexts(mutable_words, _flubber_cfg, log)
        _raw_flubber_spans = compute_flubber_spans(mutable_words, _flubber_contexts, _flubber_cfg, log)
        flubber_spans = normalize_and_merge_spans(_raw_flubber_spans, _flubber_cfg, log)
        if 'flubber' in (commands_cfg or {}):
            handle_flubber(mutable_words, _flubber_cfg, log)
        else:
            if any(str((w or {}).get('word') or '').lower() == 'flubber' for w in mutable_words):
                try:
                    handle_flubber(mutable_words, {'max_lookback_words': 50}, log)
                    log.append("[FLUBBER_TRANSCRIPT_ONLY] applied default rollback for transcript")
                except RuntimeError:
                    log.append("[FLUBBER_TRANSCRIPT_ONLY] abort ignored (transcript-only)")
    except RuntimeError as e:
        if 'FLUBBER_ABORT' in str(e):
            raise RuntimeError("Flubber abort: multiple triggers too close")
        else:
            raise

    return mutable_words, commands_cfg, ai_cmds, intern_count, flubber_count


def primary_cleanup_and_rebuild(
    content_path: Path,
    mutable_words: List[Dict[str, Any]],
    cleanup_options: Dict[str, Any],
    mix_only: bool,
    log: List[str],
) -> Tuple[AudioSegment, List[Dict[str, Any]], Dict[str, int], int]:
    """Remove fillers per config and rebuild audio; also update words if needed."""
    raw_filler_list = (cleanup_options.get('fillerWords', []) or []) if isinstance(cleanup_options, dict) else []
    filler_words = set([str(w).strip().lower() for w in raw_filler_list if str(w).strip()])
    remove_fillers_flag = bool((cleanup_options or {}).get('removeFillers', True)) if isinstance(cleanup_options, dict) else True
    remove_fillers = bool(filler_words) and remove_fillers_flag and (not mix_only)
    try:
        reason: List[str] = []
        if not filler_words:
            reason.append('no_filler_words')
        if not remove_fillers_flag:
            reason.append('flag_off')
        if mix_only:
            reason.append('mix_only')
        log.append(f"[FILLERS_CFG] remove_fillers={remove_fillers} filler_count={len(filler_words)} reasons={','.join(reason) if reason else 'ok'}")
        try:
            log.append(f"[FILLERS_NORM_LIST] {sorted(list(filler_words))[:12]}")
        except Exception:
            pass
    except Exception:
        pass
    result_audio, filler_freq_map, filler_removed_count = rebuild_audio_from_words(
        AudioSegment.from_file(content_path),
        mutable_words,
        filler_words=filler_words,
        remove_fillers=remove_fillers,
        filler_lead_trim_ms=int(cleanup_options.get('fillerLeadTrimMs', 60)) if isinstance(cleanup_options, dict) else 60,
        log=log,
    )
    cleaned_audio = result_audio
    try:
        if remove_fillers:
            total_fills = int(filler_removed_count)
            top_k = sorted(((v, k) for k, v in (filler_freq_map or {}).items()), reverse=True)[:8]
            log.append(f"[FILLERS_AUDIO_STATS] removed_count={total_fills} kinds={len(filler_freq_map or {})} top={[ (k, v) for v, k in top_k ]}")
    except Exception:
        pass
    if remove_fillers and filler_words:
        try:
            mutable_words, _fmetrics = remove_fillers_from_pipeline(mutable_words, list(filler_words), log)
        except Exception:
            pass
    return cleaned_audio, mutable_words, filler_freq_map, int(filler_removed_count)


def execute_intern_commands_step(
    ai_cmds: List[Dict[str, Any]],
    cleaned_audio: AudioSegment,
    content_path: Path,
    tts_provider: str,
    elevenlabs_api_key: Optional[str],
    mix_only: bool,
    mutable_words: List[Dict[str, Any]],
    log: List[str],
) -> Tuple[AudioSegment, List[str]]:
    """Execute intern commands and return updated audio plus notes."""
    ai_note_additions: List[str] = []
    if ai_cmds:
        try:
            try:
                orig_audio = AudioSegment.from_file(content_path)
            except Exception as e:
                # Fallback to minimal silence if original audio isn't accessible
                try:
                    log.append(f"[INTERN_ORIG_WARN] {type(e).__name__}: {e}; using 1ms silence for orig audio")
                except Exception:
                    pass
                orig_audio = AudioSegment.silent(duration=1)
            cleaned_audio = execute_intern_commands(
                ai_cmds,
                cleaned_audio,
                orig_audio,
                tts_provider,
                elevenlabs_api_key,
                ai_enhancer,
                log,
                insane_verbose=bool(False),  # insanity is already baked into ai_cmds if enabled
                mutable_words=mutable_words,
                fast_mode=bool(mix_only),
            )
            ai_note_additions = [c.get('note', '') for c in ai_cmds if c.get('note')]
        except ai_enhancer.AIEnhancerError as e:
            try:
                log.append(f"[INTERN_ERROR] {e}; skipping intern audio insertion")
            except Exception:
                pass
        except Exception as e:
            try:
                log.append(f"[INTERN_ERROR] {type(e).__name__}: {e}; skipping intern audio insertion")
            except Exception:
                pass
    return cleaned_audio, ai_note_additions


def compress_pauses_step(
    cleaned_audio: AudioSegment,
    cleanup_options: Dict[str, Any],
    mix_only: bool,
    mutable_words: List[Dict[str, Any]],
    log: List[str],
) -> Tuple[AudioSegment, List[Dict[str, Any]]]:
    """Optionally compress long pauses and retime words."""
    remove_pauses = bool(cleanup_options.get('removePauses', True)) if not mix_only else False
    if remove_pauses:
        silence_cfg = {
            'maxPauseSeconds': float(cleanup_options.get('maxPauseSeconds', 1.5)),
            'targetPauseSeconds': float(cleanup_options.get('targetPauseSeconds', 0.5)),
            'pauseCompressionRatio': float(cleanup_options.get('pauseCompressionRatio', 0.4)),
            'pauseRelDb': 16.0,
            'maxPauseRemovalPct': float(cleanup_options.get('maxPauseRemovalPct', 0.1)),
            'pauseSimilarityGuard': float(cleanup_options.get('pauseSimilarityGuard', 0.85)),
            'pausePadPreMs': float(cleanup_options.get('pausePadPreMs', 0.0)),
            'pausePadPostMs': float(cleanup_options.get('pausePadPostMs', 0.0)),
        }
        _raw_spans = detect_silence_pauses(mutable_words, silence_cfg, log)
        _spans = guard_and_pad_pauses(_raw_spans, silence_cfg, log)

        cleaned_audio = compress_long_pauses_guarded(
            cleaned_audio,
            max_pause_s=float(cleanup_options.get('maxPauseSeconds', 1.5)),
            min_target_s=float(cleanup_options.get('targetPauseSeconds', 0.5)),
            ratio=float(cleanup_options.get('pauseCompressionRatio', 0.4)),
            rel_db=16.0,
            removal_guard_pct=float(cleanup_options.get('maxPauseRemovalPct', 0.1)),
            similarity_guard=float(cleanup_options.get('pauseSimilarityGuard', 0.85)),
            log=log,
        )
        mutable_words = retime_words_for_pauses(mutable_words, _spans, silence_cfg, log)
    return cleaned_audio, mutable_words


def export_cleaned_audio_step(
    main_content_filename: str,
    cleaned_audio: AudioSegment,
    log: List[str],
) -> Tuple[str, Path]:
    """Export cleaned audio to CLEANED_DIR and return (filename, path)."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    out_stem = Path(main_content_filename).stem
    cleaned_filename = f"cleaned_{out_stem}.mp3" if not out_stem.startswith("cleaned_") else f"{out_stem}.mp3"
    cleaned_path = CLEANED_DIR / cleaned_filename
    cleaned_audio.export(cleaned_path, format="mp3")
    log.append(f"Saved cleaned content to {cleaned_filename}")
    return cleaned_filename, cleaned_path


def build_template_and_final_mix_step(
    template: Any,
    cleaned_audio: AudioSegment,
    cleaned_filename: str,
    cleaned_path: Path,
    main_content_filename: str,
    tts_overrides: Dict[str, Any],
    tts_provider: str,
    elevenlabs_api_key: Optional[str],
    output_filename: str,
    cover_image_path: Optional[str],
    log: List[str],
) -> Tuple[Path, List[Tuple[dict, AudioSegment, int, int]]]:
    """Prepare template segments, synthesize TTS, apply music rules, and export final mix.

    Returns: (final_path, placements)
    """
    # Parse template sections
    try:
        template_segments = json.loads(getattr(template, 'segments_json', '[]'))
    except Exception:
        template_segments = []
    try:
        template_background_music_rules = json.loads(getattr(template, 'background_music_rules_json', '[]'))
    except Exception:
        template_background_music_rules = []
    try:
        template_timing = json.loads(getattr(template, 'timing_json', '{}')) or {}
    except Exception:
        template_timing = {}
    try:
        log.append(
            f"[TEMPLATE_PARSE] segments={len(template_segments)} bg_rules={len(template_background_music_rules)} timing_keys={list((template_timing or {}).keys())}"
        )
    except Exception:
        pass

    # Media roots: rely on centralized MEDIA_DIR only (no ad-hoc roots)
    _MEDIA_ROOTS: List[Path] = []
    try:
        _MEDIA_ROOTS.append(MEDIA_DIR.resolve())
    except Exception:
        _MEDIA_ROOTS.append(MEDIA_DIR)

    def _resolve_media_file(name: Optional[str]) -> Optional[Path]:
        if not name:
            return None
        try:
            base = Path(name).name
            base_lower = base.lower()
            base_noext = Path(base_lower).stem
            best: Optional[Path] = None
            best_mtime = -1.0
            for root in _MEDIA_ROOTS:
                try:
                    direct = root / base
                    if direct.exists():
                        mt = direct.stat().st_mtime
                        if mt > best_mtime:
                            best, best_mtime = direct, mt
                    for p in root.glob('*'):
                        try:
                            nm = p.name.lower()
                            if nm.endswith(base_lower) or Path(nm).stem.endswith(base_noext):
                                mt = p.stat().st_mtime
                                if mt > best_mtime:
                                    best, best_mtime = p, mt
                        except Exception:
                            pass
                except Exception:
                    pass
            return best
        except Exception:
            return None
        return None

    processed_segments: List[Tuple[dict, AudioSegment]] = []
    for seg in template_segments:
        audio = None
        seg_type = str((seg.get('segment_type') if isinstance(seg, dict) else None) or 'content').lower()
        source = seg.get('source') if isinstance(seg, dict) else None
        if seg_type == 'content':
            audio = match_target_dbfs(cleaned_audio)
            try:
                log.append(f"[TEMPLATE_CONTENT] len_ms={len(audio)}")
            except Exception:
                pass
        elif source and source.get('source_type') == 'static':
            raw_name = (source.get('filename') or '')
            
            # Handle GCS URLs (intro/outro/music/sfx uploaded via media library)
            if raw_name.startswith("gs://"):
                import tempfile
                from infrastructure import gcs
                temp_path = None
                try:
                    # Parse gs://bucket/key format
                    gcs_str = raw_name[5:]  # Remove "gs://"
                    bucket, key = gcs_str.split("/", 1)
                    
                    # Download bytes from GCS
                    file_bytes = gcs.download_bytes(bucket, key)
                    if not file_bytes:
                        raise RuntimeError(f"Failed to download from GCS: {raw_name}")
                    
                    # Write to temp file for pydub
                    temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
                    os.close(temp_fd)
                    
                    with open(temp_path, "wb") as f:
                        f.write(file_bytes)
                    
                    audio = AudioSegment.from_file(temp_path)
                    log.append(f"[TEMPLATE_STATIC_GCS_OK] seg_id={seg.get('id')} gcs={raw_name} len_ms={len(audio)}")
                except Exception as e:
                    log.append(f"[TEMPLATE_STATIC_GCS_ERROR] seg_id={seg.get('id')} gcs={raw_name} error={type(e).__name__}: {e}")
                    audio = None
                finally:
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.unlink(temp_path)
                        except Exception:
                            pass
            
            # Handle local files (backward compatibility)
            else:
                static_path = MEDIA_DIR / raw_name
                if static_path.exists():
                    audio = AudioSegment.from_file(static_path)
                    try:
                        log.append(f"[TEMPLATE_STATIC_OK] seg_id={seg.get('id')} file={static_path.name} len_ms={len(audio)}")
                    except Exception:
                        pass
                else:
                    alt = _resolve_media_file(raw_name)
                    if alt and alt.exists():
                        try:
                            audio = AudioSegment.from_file(alt)
                            log.append(f"[TEMPLATE_STATIC_RESOLVED] seg_id={seg.get('id')} requested={raw_name} -> {alt.name} len_ms={len(audio)}")
                        except Exception as e:
                            try:
                                log.append(f"[TEMPLATE_STATIC_RESOLVE_ERROR] {type(e).__name__}: {e}")
                            except Exception:
                                pass
                    if not audio:
                        try:
                            log.append(f"[TEMPLATE_STATIC_MISSING] seg_id={seg.get('id')} file={raw_name}")
                        except Exception:
                            pass
        elif source and source.get('source_type') == 'tts':
            script = tts_overrides.get(str(seg.get('id')), source.get('script') or '')
            script = str(script or '')
            try:
                log.append(f"[TEMPLATE_TTS] seg_id={seg.get('id')} len={len(script)}")
            except Exception:
                pass
            try:
                if script.strip() == "":
                    log.append("[TEMPLATE_TTS_EMPTY] empty script -> inserting 500ms silence")
                    audio = AudioSegment.silent(duration=500)
                else:
                    _tts_cfg = {
                        'provider': tts_provider,
                        'api_key': elevenlabs_api_key,
                        'voice_id': source.get('voice_id'),
                        'max_chars_per_chunk': max(1, len(script) + 1),
                        'pause_ms': 0,
                        'crossfade_ms': 0,
                        'sample_rate': None,
                        'retries': 2,
                        'backoff_seconds': 1.0,
                    }
                    _tmp_tts_log: List[str] = []
                    _chunks = chunk_prompt_for_tts(script, _tts_cfg, _tmp_tts_log)
                    _paths = synthesize_chunks(_chunks or [{'id': 'chunk-001', 'text': script, 'pause_ms': 0}], ai_enhancer, _tts_cfg, _tmp_tts_log)
                    if _paths:
                        audio = AudioSegment.from_file(_paths[0])
                    else:
                        audio = ai_enhancer.generate_speech_from_text(
                            script,
                            source.get('voice_id'),
                            api_key=elevenlabs_api_key,
                            provider=tts_provider,
                        )
            except ai_enhancer.AIEnhancerError as e:
                try:
                    log.append(f"[TEMPLATE_TTS_ERROR] {e}; inserting 500ms silence instead")
                except Exception:
                    pass
                audio = AudioSegment.silent(duration=500)
            except Exception as e:
                try:
                    log.append(f"[TEMPLATE_TTS_ERROR] {type(e).__name__}: {e}; inserting 500ms silence instead")
                except Exception:
                    pass
                audio = AudioSegment.silent(duration=500)
            try:
                if audio is not None:
                    log.append(f"[TEMPLATE_TTS_OK] seg_id={seg.get('id')} len_ms={len(audio)}")
            except Exception:
                pass
        if audio:
            if seg_type != 'content':
                audio = match_target_dbfs(audio)
            processed_segments.append((seg, audio))

    try:
        _by_type: Dict[str, int] = {}
        for s, a in processed_segments:
            _t = (s.get('segment_type') or 'content')
            _by_type[_t] = _by_type.get(_t, 0) + 1
        log.append(f"[TEMPLATE_PROCESSED] count={len(processed_segments)} by_type={_by_type}")
    except Exception:
        pass

    try:
        has_content = any(str((s.get('segment_type') or 'content')).lower() == 'content' for s, _ in processed_segments)
    except Exception:
        has_content = True
    if not has_content:
        try:
            content_audio = match_target_dbfs(cleaned_audio)
            insert_index = None
            for idx, (s, _a) in enumerate(processed_segments):
                if str((s.get('segment_type') or 'content')).lower() == 'outro':
                    insert_index = idx
                    break
            content_seg = ({'segment_type': 'content', 'name': 'Content (auto)'}, content_audio)
            if insert_index is not None:
                processed_segments.insert(insert_index, content_seg)
            else:
                processed_segments.append(content_seg)
            log.append("[TEMPLATE_AUTO_CONTENT] inserted content segment (template had none)")
        except Exception:
            pass

    def _concat(segs: List[AudioSegment]) -> AudioSegment:
        if not segs:
            return AudioSegment.silent(duration=0)
        acc = segs[0]
        for ss in segs[1:]:
            acc += ss
        return acc

    _content_frags = [a for s, a in processed_segments if (s.get('segment_type') or 'content') == 'content']
    stitched_content: AudioSegment = _concat(_content_frags) if _content_frags else match_target_dbfs(cleaned_audio)
    
    # Get template timing with proper error handling (avoid lazy-loading in invalid session)
    try:
        template_timing = json.loads(getattr(template, 'timing_json', '{}')) or {} if template else {}
    except Exception:
        template_timing = {}
    
    cs_off_ms = int(float(template_timing.get('content_start_offset_s') or 0.0) * 1000)
    os_off_ms = int(float(template_timing.get('outro_start_offset_s') or 0.0) * 1000)

    placements: List[Tuple[dict, AudioSegment, int, int]] = []
    pos_ms = 0
    used_content_once = False
    for seg, aud in processed_segments:
        seg_type = str((seg.get('segment_type') or 'content')).lower()
        seg_audio = aud
        if seg_type == 'content':
            if used_content_once:
                try:
                    log.append("[TEMPLATE_WARN] Multiple 'content' segments detected; using aggregated content once")
                except Exception:
                    pass
                continue
            seg_audio = stitched_content
            start = pos_ms + cs_off_ms
            used_content_once = True
        elif seg_type == 'outro':
            start = pos_ms + os_off_ms
        else:
            start = pos_ms
        if start < 0:
            trim = -start
            try:
                seg_audio = cast(AudioSegment, seg_audio[int(trim):])
            except Exception:
                pass
            start = 0
        end = start + len(seg_audio)
        try:
            log.append(f"[TEMPLATE_OFFSET_APPLIED] type={seg_type} start={start} end={end} len={len(seg_audio)}")
        except Exception:
            pass
        placements.append((seg, seg_audio, start, end))
        pos_ms = max(pos_ms, end)

    if not placements:
        try:
            log.append("[TEMPLATE_FALLBACK_CONTENT_ONLY] no placements built; using content only")
        except Exception:
            pass
        placements.append(({'segment_type': 'content', 'name': 'Content'}, stitched_content, 0, len(stitched_content)))
        pos_ms = len(stitched_content)

    try:
        _kinds: List[Tuple[str, int, int]] = []
        for _s, _a, _st, _en in placements:
            _kinds.append((str(_s.get('segment_type') or 'content'), _st, _en))
        log.append(f"[TEMPLATE_PLACEMENTS] count={len(placements)} kinds={_kinds}")
    except Exception:
        pass

    total_duration_ms = pos_ms if pos_ms > 0 else max(1, len(stitched_content))
    estimated_bytes = _estimate_mix_bytes(
        total_duration_ms,
        cleaned_audio.frame_rate,
        cleaned_audio.channels,
        cleaned_audio.sample_width,
    )
    if estimated_bytes > MAX_MIX_BUFFER_BYTES:
        try:
            log.append(
                "[TEMPLATE_TIMELINE_TOO_LARGE] "
                f"duration_ms={total_duration_ms} bytes_needed={estimated_bytes} "
                f"limit={MAX_MIX_BUFFER_BYTES}"
            )
        except Exception:
            pass
        _raise_timeline_limit(
            duration_ms=total_duration_ms,
            bytes_needed=estimated_bytes,
            limit_bytes=MAX_MIX_BUFFER_BYTES,
            placements=placements,
        )
    mix_buffer = _StreamingMixBuffer(
        cleaned_audio.frame_rate,
        cleaned_audio.channels,
        cleaned_audio.sample_width,
        initial_duration_ms=total_duration_ms,
    )
    for _seg, _aud, _st, _en in placements:
        if len(_aud) > 0:
            label = (
                _seg.get("name")
                or _seg.get("title")
                or (_seg.get("source") or {}).get("label")
                or (_seg.get("source") or {}).get("filename")
                or _seg.get("segment_type")
                or "segment"
            )
            mix_buffer.overlay(_aud, _st, label=str(label))

    try:
        def _apply(
            bg_seg: AudioSegment,
            start_ms: int,
            end_ms: int,
            *,
            vol_db: float,
            fade_in_ms: int,
            fade_out_ms: int,
            label: str,
        ) -> None:
            dur = max(0, end_ms - start_ms)
            if dur <= 0:
                return
            try:
                fi = max(0, int(fade_in_ms or 0))
                fo = max(0, int(fade_out_ms or 0))
                if fi + fo >= dur and dur > 0:
                    if fi > 0 and fo > 0:
                        total = fi + fo
                        fi = int((fi / total) * (dur - 1))
                        fo = max(0, (dur - 1) - fi)
                    else:
                        fi = 0
                        fo = max(0, dur - 1)
            except Exception:
                fi = max(0, int(fade_in_ms or 0))
                fo = max(0, int(fade_out_ms or 0))

            base_seg = cast(AudioSegment, bg_seg)
            if len(base_seg) <= 0:
                return
            try:
                if vol_db is not None:
                    base_seg = base_seg.apply_gain(float(vol_db))
            except Exception:
                pass

            remaining = dur
            chunk_offset = 0
            chunk_limit = max(1000, int(BACKGROUND_LOOP_CHUNK_MS))
            while remaining > 0:
                chunk_ms = min(chunk_limit, remaining)
                chunk = _loop_chunk(base_seg, chunk_ms)
                if len(chunk) <= 0:
                    break

                boundaries = [0, len(chunk)]
                fi_boundary = fi - chunk_offset
                if fi > 0 and 0 < fi_boundary < len(chunk):
                    boundaries.append(int(fi_boundary))
                fo_start = dur - fo
                fo_boundary = fo_start - chunk_offset
                if fo > 0 and 0 < fo_boundary < len(chunk):
                    boundaries.append(int(fo_boundary))
                boundaries = sorted({int(max(0, min(len(chunk), b))) for b in boundaries})

                for idx in range(len(boundaries) - 1):
                    sub_start = boundaries[idx]
                    sub_end = boundaries[idx + 1]
                    if sub_end <= sub_start:
                        continue
                    sub = chunk[sub_start:sub_end]
                    global_start = chunk_offset + sub_start
                    start_factor = _envelope_factor(global_start, dur, fi, fo)
                    end_factor = _envelope_factor(global_start + len(sub), dur, fi, fo)
                    if not (
                        abs(start_factor - 1.0) < 1e-6 and abs(end_factor - 1.0) < 1e-6
                    ):
                        sub = _apply_gain_ramp(sub, start_factor, end_factor)
                    mix_buffer.overlay(
                        cast(AudioSegment, sub),
                        start_ms + global_start,
                        label=f"background:{label}",
                    )

                chunk_offset += len(chunk)
                remaining -= len(chunk)
                if len(chunk) < chunk_ms:
                    break
            try:
                log.append(f"[MUSIC_RULE_APPLY] label={label} pos_ms={start_ms} dur_ms={dur} vol_db={vol_db} fade_in_ms={fade_in_ms} fade_out_ms={fade_out_ms}")
            except Exception:
                pass

        for rule in (template_background_music_rules or []):
            req_name = (rule.get('music_filename') or rule.get('music') or '')
            music_path = MEDIA_DIR / req_name
            if not music_path.exists():
                altm = _resolve_media_file(req_name)
                if altm and altm.exists():
                    music_path = altm
                    try:
                        log.append(f"[MUSIC_RULE_RESOLVED] requested={req_name} -> {music_path.name}")
                    except Exception:
                        pass
                else:
                    try:
                        log.append(f"[MUSIC_RULE_SKIP] missing_file={req_name}")
                    except Exception:
                        pass
                    continue
            bg = AudioSegment.from_file(music_path)
            apply_to = [str(t).lower() for t in (rule.get('apply_to_segments') or [])]
            vol_db = float(rule.get('volume_db') if rule.get('volume_db') is not None else -15)
            fade_in_ms = int(max(0.0, float(rule.get('fade_in_s') or 0.0)) * 1000)
            fade_out_ms = int(max(0.0, float(rule.get('fade_out_s') or 0.0)) * 1000)
            start_off_s = float(rule.get('start_offset_s') or 0.0)
            end_off_s = float(rule.get('end_offset_s') or 0.0)
            try:
                log.append(f"[MUSIC_RULE_OK] file={music_path.name} apply_to={apply_to} vol_db={vol_db} start_off_s={start_off_s} end_off_s={end_off_s}")
            except Exception:
                pass

            label_to_intervals: Dict[str, List[Tuple[int, int]]] = {}
            try:
                log.append(f"[MUSIC_RULE_MATCHING] apply_to={apply_to} checking {len(placements)} placements")
            except Exception:
                pass
            for seg, _aud, st_ms, en_ms in placements:
                seg_type = str((seg.get('segment_type') or 'content')).lower()
                try:
                    log.append(f"[MUSIC_RULE_CHECK] seg_type='{seg_type}' vs apply_to={apply_to} match={seg_type in apply_to}")
                except Exception:
                    pass
                if seg_type not in apply_to:
                    continue
                label_to_intervals.setdefault(seg_type, []).append((st_ms, en_ms))
            
            try:
                if not label_to_intervals:
                    log.append(f"[MUSIC_RULE_NO_MATCH] apply_to={apply_to} but no matching segments found in {len(placements)} placements!")
                else:
                    log.append(f"[MUSIC_RULE_MATCHED] label_to_intervals={list(label_to_intervals.keys())} with {sum(len(v) for v in label_to_intervals.values())} total intervals")
            except Exception:
                pass

            for label, intervals in label_to_intervals.items():
                if not intervals:
                    continue
                intervals.sort(key=lambda x: x[0])
                merged: List[Tuple[int, int]] = []
                cur_s, cur_e = intervals[0]
                for s, e in intervals[1:]:
                    if s <= cur_e:
                        cur_e = max(cur_e, e)
                    else:
                        merged.append((cur_s, cur_e))
                        cur_s, cur_e = s, e
                merged.append((cur_s, cur_e))
                try:
                    log.append(f"[MUSIC_RULE_MERGED] label={label} groups={len(merged)} intervals={merged}")
                except Exception:
                    pass
                off_start = int(start_off_s * 1000)
                off_end = int(end_off_s * 1000)
                for s, e in merged:
                    s2 = s + off_start
                    e2 = e - off_end
                    if e2 <= s2:
                        continue
                    _apply(bg, s2, e2, vol_db=vol_db, fade_in_ms=fade_in_ms, fade_out_ms=fade_out_ms, label=label)
    except Exception as e:
        log.append(f"[MUSIC_RULES_WARN] {type(e).__name__}: {e}")

    final_mix = mix_buffer.to_segment()
    try:
        log.append(f"[FINAL_MIX] duration_ms={len(final_mix)}")
    except Exception:
        pass
    final_filename = f"{sanitize_filename(output_filename)}.mp3"
    final_path = OUTPUT_DIR / final_filename

    export_cfg: Dict[str, Any] = {}
    tmp_master_in = OUTPUT_DIR / f"._tmp_{sanitize_filename(output_filename)}_final.wav"
    try:
        tmp_master_in.parent.mkdir(parents=True, exist_ok=True)
        final_mix.export(tmp_master_in, format="wav")
        _norm = normalize_master(tmp_master_in, final_path, export_cfg, log)
        _mux = mux_tracks(final_path, None, final_path, export_cfg, log)
        outputs_cfg = {"mp3": final_path}
        _deriv = write_derivatives(final_path, outputs_cfg, export_cfg, log)
        cover_art_path = Path(cover_image_path) if cover_image_path else None
        for _fmt, _p in outputs_cfg.items():
            try:
                embed_metadata(_p, {}, cover_art_path, [], log)
            except Exception:
                pass
        log.append(f"Saved final content to {final_path.name}")
    except Exception as e:
        log.append(f"[FINAL_EXPORT_ERROR] {e}; falling back to cleaned content export")
        final_path = OUTPUT_DIR / cleaned_filename
        try:
            cleaned_audio.export(final_path, format="mp3")
        except Exception:
            final_path = cleaned_path
    finally:
        try:
            if tmp_master_in.exists():
                tmp_master_in.unlink()
        except Exception:
            pass

    return final_path, placements


def write_final_transcripts_and_cleanup(
    sanitized_output_filename: str,
    mutable_words: List[Dict[str, Any]],
    placements: List[Tuple[dict, AudioSegment, int, int]],
    template: Any,
    main_content_filename: str,
    log: List[str],
) -> None:
    """Write final and published transcripts and clean legacy transcript files."""
    # Update working JSON
    try:
        working_json = TRANSCRIPTS_DIR / f"{sanitized_output_filename}.json"
        with open(working_json, 'w', encoding='utf-8') as fh:
            json.dump(mutable_words, fh)
        log.append(f"[TRANSCRIPTS] updated working JSON {working_json.name} entries={len(mutable_words)}")
    except Exception as e:
        log.append(f"[TRANSCRIPTS_ERROR] update working JSON: {e}")

    # Final content-only transcript (phrases)
    try:
        final_txt = TRANSCRIPTS_DIR / f"{sanitized_output_filename}.final.txt"
        final_phrases = _build_phrases(mutable_words)
        _write_phrase_txt(final_txt, final_phrases)
        log.append(f"[TRANSCRIPTS] wrote final (content) {final_txt.name} phrases={len(final_phrases)}")
    except Exception as e:
        log.append(f"[TRANSCRIPTS_ERROR] write final content transcript: {e}")

    # Published transcript aligned to placements (with labels for non-content)
    try:
        published_txt = TRANSCRIPTS_DIR / f"{sanitized_output_filename}.txt"
        pub_phrases: List[Dict[str, Any]] = []
        if placements:
            content_phr = _build_phrases(mutable_words)
            content_added = False
            for seg, seg_audio, st_ms, en_ms in placements:
                seg_type = str((seg.get('segment_type') or 'content')).lower()
                if seg_type == 'content' and not content_added:
                    pub_phrases.extend(_offset_phrases(content_phr, st_ms / 1000.0))
                    content_added = True
                elif seg_type != 'content':
                    label = seg.get('name') or seg.get('title') or (seg.get('source') or {}).get('label') or (seg.get('source') or {}).get('filename') or seg_type.title()
                    pub_phrases.append({'speaker': 'Narrator', 'start': st_ms / 1000.0, 'end': en_ms / 1000.0, 'text': f"[{label}]"})
        else:
            pub_phrases = _build_phrases(mutable_words)
        _write_phrase_txt(published_txt, pub_phrases)
        log.append(f"[TRANSCRIPTS] wrote published transcript {published_txt.name} phrases={len(pub_phrases)}")
    except Exception as e:
        log.append(f"[TRANSCRIPTS_ERROR] write published transcript: {e}")

    # Cleanup legacy helpers and sidecars
    try:
        content_stem = Path(main_content_filename).stem
        cleaned_stem = f"cleaned_{content_stem}"
        precut_stem = f"precut_{content_stem}"
        keep_base = f"{sanitized_output_filename}.json"
        legacy_patterns = [
            f"*{content_stem}.words.json",
            f"*{content_stem}.original.words.json",
            f"{sanitized_output_filename}.words.json",
            f"{sanitized_output_filename}.original.words.json",
            f"{cleaned_stem}.words.json",
            f"{cleaned_stem}.original.words.json",
            f"{precut_stem}.words.json",
            f"{precut_stem}.original.words.json",
        ]
        for pat in legacy_patterns:
            for p in TRANSCRIPTS_DIR.glob(pat):
                if p.name == keep_base or p.suffix.lower() == ".txt":
                    continue
                try:
                    p.unlink()
                    log.append(f"[TRANSCRIPTS_CLEAN] removed {p.name}")
                except Exception as _e:
                    log.append(f"[TRANSCRIPTS_CLEAN_WARN] could not remove {p.name}: {type(_e).__name__}: {_e}")
        helper_targets = [
            TRANSCRIPTS_DIR / f"{sanitized_output_filename}.nopunct.json",
            TRANSCRIPTS_DIR / f"{sanitized_output_filename}.original.json",
            TRANSCRIPTS_DIR / f"{content_stem}.original.json",
            TRANSCRIPTS_DIR / f"{cleaned_stem}.original.json",
            TRANSCRIPTS_DIR / f"{precut_stem}.original.json",
        ]
        for p in helper_targets:
            try:
                if p.exists():
                    p.unlink()
                    log.append(f"[TRANSCRIPTS_CLEAN] removed {p.name}")
            except Exception as _e:
                log.append(f"[TRANSCRIPTS_CLEAN_WARN] could not remove {getattr(p,'name',p)}: {type(_e).__name__}: {_e}")
        # Do NOT remove canonical transcripts like <output_slug>.json or <content_stem>.json; keep permanent copies.
        # Only remove clearly legacy variants handled above. This preserves upload-time canonical JSON artifacts.
    except Exception as e:
        log.append(f"[TRANSCRIPTS_CLEAN_ERROR] {e}")


__all__ = [
    'load_content_and_init_transcripts',
    'detect_and_prepare_ai_commands',
    'primary_cleanup_and_rebuild',
    'execute_intern_commands_step',
    'compress_pauses_step',
    'export_cleaned_audio_step',
    'build_template_and_final_mix_step',
    'write_final_transcripts_and_cleanup',
]


# --- Thin wrappers matching ORC-1B expected names ---
def do_transcript_io(paths: Dict[str, Any], cfg: Dict[str, Any], log: List[str]) -> Dict[str, Any]:
    template = paths.get('template')
    main_content_filename = str(paths.get('audio_in') or '')
    output_filename = str(paths.get('output_name') or Path(main_content_filename).stem or 'episode')
    words_json_path = str(paths.get('words_json') or '') or None
    forbid_transcribe = bool(cfg.get('forbid_transcribe') or cfg.get('forbidTranscribe') or False)
    content_path, main_content_audio, words, sanitized_output_filename = load_content_and_init_transcripts(
        main_content_filename, words_json_path, output_filename, log, forbid_transcribe=forbid_transcribe
    )
    return {
        'template': template,
        'content_path': content_path,
        'main_content_audio': main_content_audio,
        'words': words,
        'sanitized_output_filename': sanitized_output_filename,
        'output_filename': output_filename,
        'cover_image_path': str(paths.get('cover_art') or '') or None,
        'main_content_filename': main_content_filename,
    }


def do_intern_sfx(paths: Dict[str, Any], cfg: Dict[str, Any], log: List[str], *, words: List[Dict[str, Any]]) -> Dict[str, Any]:
    cleanup_options = cfg.get('cleanup_options', {}) or {}
    mix_only = bool(cfg.get('mix_only') or cfg.get('mixOnly') or False)
    words_json_path = str(paths.get('words_json') or '') or None
    mutable_words, commands_cfg, ai_cmds, intern_count, flubber_count = detect_and_prepare_ai_commands(
        words, cleanup_options, words_json_path, mix_only, log
    )
    return {
        'mutable_words': mutable_words,
        'commands_cfg': commands_cfg,
        'ai_cmds': ai_cmds,
        'intern_count': intern_count,
        'flubber_count': flubber_count,
    }


def do_flubber(paths: Dict[str, Any], cfg: Dict[str, Any], log: List[str], *, mutable_words: List[Dict[str, Any]], commands_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Compatibility wrapper for a separate flubber phase.

    Flubber processing is already executed inside detect_and_prepare_ai_commands.
    This wrapper returns no changes to avoid double-application.
    """
    return {}


def do_fillers(paths: Dict[str, Any], cfg: Dict[str, Any], log: List[str], *, content_path: Path, mutable_words: List[Dict[str, Any]]) -> Dict[str, Any]:
    cleanup_options = cfg.get('cleanup_options', {}) or {}
    mix_only = bool(cfg.get('mix_only') or cfg.get('mixOnly') or False)
    cleaned_audio, mutable_words2, filler_freq_map, filler_removed_count = primary_cleanup_and_rebuild(
        content_path, mutable_words, cleanup_options, mix_only, log
    )
    return {
        'cleaned_audio': cleaned_audio,
        'mutable_words': mutable_words2,
        'filler_freq_map': filler_freq_map,
        'filler_removed_count': filler_removed_count,
    }


def do_silence(paths: Dict[str, Any], cfg: Dict[str, Any], log: List[str], *, cleaned_audio: AudioSegment, mutable_words: List[Dict[str, Any]]) -> Dict[str, Any]:
    cleanup_options = cfg.get('cleanup_options', {}) or {}
    mix_only = bool(cfg.get('mix_only') or cfg.get('mixOnly') or False)
    cleaned_audio2, mutable_words2 = compress_pauses_step(cleaned_audio, cleanup_options, mix_only, mutable_words, log)
    return {
        'cleaned_audio': cleaned_audio2,
        'mutable_words': mutable_words2,
    }


def do_tts(paths: Dict[str, Any], cfg: Dict[str, Any], log: List[str], *, ai_cmds: List[Dict[str, Any]], cleaned_audio: AudioSegment, content_path: Path, mutable_words: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Execute intern commands (may synthesize TTS audio when needed)
    tts_provider = str(cfg.get('tts_provider') or 'elevenlabs')
    elevenlabs_api_key = cfg.get('elevenlabs_api_key')
    mix_only = bool(cfg.get('mix_only') or cfg.get('mixOnly') or False)
    cleanup_options = cfg.get('cleanup_options', {}) or {}
    insane_verbose = bool(cleanup_options.get('insaneVerbose') or cleanup_options.get('debugCommands'))

    ai_note_additions: List[str] = []
    if ai_cmds:
        try:
            try:
                orig_audio = AudioSegment.from_file(content_path)
            except Exception as e:
                # Fallback to minimal silence if original audio isn't accessible
                try:
                    log.append(f"[INTERN_ORIG_WARN] {type(e).__name__}: {e}; using 1ms silence for orig audio")
                except Exception:
                    pass
                orig_audio = AudioSegment.silent(duration=1)
            cleaned_audio = execute_intern_commands(
                ai_cmds,
                cleaned_audio,
                orig_audio,
                tts_provider,
                elevenlabs_api_key,
                ai_enhancer,
                log,
                insane_verbose=insane_verbose,
                mutable_words=mutable_words,
                fast_mode=bool(mix_only),
            )
            ai_note_additions = [c.get('note', '') for c in ai_cmds if c.get('note')]
        except ai_enhancer.AIEnhancerError as e:
            try:
                log.append(f"[INTERN_ERROR] {e}; skipping intern audio insertion")
            except Exception:
                pass
        except Exception as e:
            try:
                log.append(f"[INTERN_ERROR] {type(e).__name__}: {e}; skipping intern audio insertion")
            except Exception:
                pass
    return {
        'cleaned_audio': cleaned_audio,
        'ai_note_additions': ai_note_additions,
    }


def do_export(paths: Dict[str, Any], cfg: Dict[str, Any], log: List[str], *, template: Any, cleaned_audio: AudioSegment, main_content_filename: str, output_filename: str, cover_image_path: Optional[str], mutable_words: List[Dict[str, Any]], sanitized_output_filename: str) -> Dict[str, Any]:
    # Export cleaned audio first
    cleaned_filename, cleaned_path = export_cleaned_audio_step(main_content_filename, cleaned_audio, log)

    # Build final mix with template and export; also write final/published transcripts and cleanup
    final_path, placements = build_template_and_final_mix_step(
        template,
        cleaned_audio,
        cleaned_filename,
        cleaned_path,
        main_content_filename,
        cfg.get('tts_overrides', {}) or {},
        str(cfg.get('tts_provider') or 'elevenlabs'),
        cfg.get('elevenlabs_api_key'),
        output_filename,
        str(paths.get('cover_art') or '') or None if cover_image_path is None else cover_image_path,
        log,
    )
    write_final_transcripts_and_cleanup(sanitized_output_filename, mutable_words, placements, template, main_content_filename, log)
    return {
        'final_path': final_path,
        'placements': placements,
        'cleaned_filename': cleaned_filename,
        'cleaned_path': cleaned_path,
    }
