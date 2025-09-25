from __future__ import annotations
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import json

from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

from .models import Word, UserSettings, SilenceSettings, InternSettings, CensorSettings
from .words import parse_words, remap_words_after_cuts, build_filler_cuts, merge_ranges
from .features import (
    ensure_ffmpeg,
    apply_flubber_cuts,
    insert_intern_responses,
    apply_censor_beep,
    replace_keywords_with_sfx,
)


def run_all(
    audio_path: Path,
    words_json_path: Path,
    work_dir: Path,
    user_settings: UserSettings,
    silence_cfg: SilenceSettings,
    intern_cfg: InternSettings,
    censor_cfg: Optional[CensorSettings] = None,
    sfx_map: Optional[Dict[str, Path]] = None,
    synth: Optional[Callable[[str], AudioSegment]] = None,
    flubber_cuts_ms: Optional[List[Tuple[int,int]]] = None,
    output_name: Optional[str] = None,
    disable_intern_insertion: bool = False,
) -> Dict[str, Any]:
    ensure_ffmpeg()
    work_dir = Path(work_dir)
    (work_dir / "cleaned_audio").mkdir(parents=True, exist_ok=True)
    words_raw = json.loads(Path(words_json_path).read_text())
    words = parse_words(words_raw)
    try:
        audio = AudioSegment.from_file(audio_path)
    except CouldntDecodeError as e:
        # Provide a clearer hint for tests that may have created an empty placeholder
        raise ValueError(
            f"Invalid or empty audio file at {audio_path}; tests should create a real WAV via make_tiny_wav"
        ) from e
    show_notes: List[str] = []
    if flubber_cuts_ms:
        audio = apply_flubber_cuts(audio, flubber_cuts_ms)
        words = remap_words_after_cuts(words, flubber_cuts_ms)
    if synth is None:
        synth = lambda text: AudioSegment.silent(duration=600)
    summary: Dict[str, Any] = {"edits": {}}
    def _add_note(txt: str):
        show_notes.append(txt)
    if not disable_intern_insertion and intern_cfg and getattr(intern_cfg, 'scan_window_s', 0.0) > 0 and synth is not None:
        audio = insert_intern_responses(audio, words, user_settings, intern_cfg, synth, _add_note)
        # Using keyword find similar to original
        count = sum(1 for w in words if w.word.strip().lower() == user_settings.intern_keyword)
        summary["edits"]["intern_insertions"] = count
    else:
        summary["edits"]["intern_insertions"] = 0
    # ---- Command terminators (CUT) would go here if available as spans
    prior_cut_spans: List[Tuple[int,int]] = []

    # ---- Fillers (CUT)
    # Settings with safe defaults
    remove_fillers_flag = bool(getattr(user_settings, 'removeFillers', getattr(user_settings, 'remove_fillers', True)))
    default_fillers = ["um","uh","er","ah"]
    user_fillers = getattr(user_settings, 'fillerWords', None) or getattr(user_settings, 'filler_words', None)
    if not user_fillers:
        user_fillers = default_fillers
    # also include any aggressive list if present on settings
    try:
        user_fillers = list(dict.fromkeys(list(user_fillers) + list(getattr(user_settings, 'aggressive_fillers', []))))
    except Exception:
        user_fillers = list(user_fillers) if isinstance(user_fillers, (list, tuple)) else default_fillers

    filler_cuts: List[Tuple[int,int]] = []
    filler_log_tokens: List[str] = []
    if remove_fillers_flag:
        # Build spans from current words
        fset = {str(f).strip().lower() for f in (user_fillers or []) if str(f).strip()}
        # capture tokens before edits for logging
        filler_log_tokens = [(w.word or '').strip().lower() for w in words if (w.word or '').strip().lower() in fset]
        filler_cuts = build_filler_cuts(words, fset)
    else:
        filler_cuts = []
    summary["edits"]["filler_cuts"] = list(merge_ranges(filler_cuts, gap_ms=0)) if filler_cuts else []

    # ---- Silences (CUT) - build cuts from word gaps
    def build_pause_cuts(_audio: AudioSegment, _words: List[Word], max_pause_ms: int, target_pause_ms: int) -> List[Tuple[int,int]]:
        cuts: List[Tuple[int,int]] = []
        if not _words or target_pause_ms < 0 or max_pause_ms <= 0:
            return cuts
        ws = sorted(_words, key=lambda w: (w.start, w.end))
        prev_end = int(round(ws[0].end * 1000)) if ws else 0
        for w in ws[1:]:
            start_ms = int(round(w.start * 1000))
            gap = start_ms - prev_end
            if gap > max_pause_ms and gap > target_pause_ms:
                cut_s = prev_end + target_pause_ms
                cut_e = start_ms
                if cut_e > cut_s:
                    cuts.append((cut_s, cut_e))
            prev_end = int(round(w.end * 1000))
        return cuts

    remove_pauses_flag = bool(getattr(user_settings, 'removePauses', True))
    max_pause_ms = int(round(1000 * float(getattr(user_settings, 'maxPauseSeconds', 1.5))))
    target_pause_ms = int(round(1000 * float(getattr(user_settings, 'targetPauseSeconds', 0.5))))
    silence_cuts: List[Tuple[int,int]] = []
    if remove_pauses_flag:
        silence_cuts = build_pause_cuts(audio, words, max_pause_ms, target_pause_ms)
    # Logging for silence
    total_sil_rm = sum(max(0, e - s) for s, e in silence_cuts) if silence_cuts else 0
    print(f"[silence] max={max_pause_ms}ms target={target_pause_ms}ms spans={len(silence_cuts)} removed_ms={total_sil_rm}")
    # Accumulate and apply all CUT spans at once
    all_cuts = merge_ranges((prior_cut_spans or []) + (filler_cuts or []) + (silence_cuts or []), gap_ms=0)
    if all_cuts:
        audio = apply_flubber_cuts(audio, all_cuts)
        words = remap_words_after_cuts(words, all_cuts)
    # Filler logging (filler-only stats)
    filler_spans_merged = merge_ranges(filler_cuts, gap_ms=0) if filler_cuts else []
    filler_removed_ms = sum(max(0, e - s) for s, e in filler_spans_merged)
    sample = ", ".join(filler_log_tokens[:3])
    print(f"[fillers] tokens={len(filler_log_tokens)} merged_spans={len(filler_spans_merged)} removed_ms={filler_removed_ms} sample=[{sample}]")
    if censor_cfg and getattr(censor_cfg, 'enabled', False):
        # Capture mode for diagnostics
        try:
            mode = {
                "uniform_ms": int(getattr(censor_cfg, 'beep_ms', 250)),
                "custom": bool(getattr(censor_cfg, 'beep_file', None)),
                "file": str(getattr(censor_cfg, 'beep_file', '')) if getattr(censor_cfg, 'beep_file', None) else None,
            }
            summary["edits"]["censor_mode"] = mode
        except Exception:
            summary["edits"]["censor_mode"] = {"uniform_ms": int(getattr(censor_cfg, 'beep_ms', 250))}
        audio, censor_spans = apply_censor_beep(audio, words, censor_cfg, mutate_words=False)
        summary["edits"]["censor_spans_ms"] = censor_spans
    else:
        summary["edits"]["censor_spans_ms"] = []
    if sfx_map:
        audio = replace_keywords_with_sfx(audio, words, sfx_map)
        summary["edits"]["sfx_applied"] = list(sfx_map.keys())
    else:
        summary["edits"]["sfx_applied"] = []
    out_name = output_name or f"{Path(audio_path).stem}_processed.mp3"
    out_path = work_dir / "cleaned_audio" / out_name
    audio.export(out_path, format="mp3")
    try:
        tr_dir = work_dir / 'transcripts'
        tr_dir.mkdir(parents=True, exist_ok=True)
        # vendor/original
        words_json_orig = tr_dir / f"{out_path.stem}.original.json"
        with open(words_json_orig, 'w', encoding='utf-8') as fh:
            fh.write(Path(words_json_path).read_text(encoding='utf-8'))
        # working/cleaned
        words_json_out = tr_dir / f"{out_path.stem}.json"
        with open(words_json_out, 'w', encoding='utf-8') as fh:
            import json as _json
            _json.dump([
                {"word": w.word, "start": w.start, "end": w.end} for w in words if getattr(w, 'word', None) is not None
            ], fh)
        summary["edits"]["words_json"] = str(words_json_out)
        summary["edits"]["words_json_original"] = str(words_json_orig)
    except Exception:
        pass
    summary["show_notes"] = show_notes
    summary["final_duration_ms"] = len(audio)
    return {"final_path": str(out_path), "summary": summary}

