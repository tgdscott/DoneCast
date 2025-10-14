from __future__ import annotations

from typing import List, Tuple
from pydub import AudioSegment

from ..models import SilenceSettings
from .utils import detect_silences_dbfs


def compress_dead_air_middle(
    audio: AudioSegment,
    silence_cfg: SilenceSettings
) -> Tuple[AudioSegment, List[Tuple[int, int, int]]]:
    silences = detect_silences_dbfs(
        audio,
        threshold_dbfs=silence_cfg.detect_threshold_dbfs,
        min_len_ms=silence_cfg.min_silence_ms,
    )
    if not silences:
        return audio, []

    edits: List[Tuple[int, int, int]] = []
    out = AudioSegment.silent(duration=0)
    cursor = 0
    crossfade_ms = 15  # 15ms crossfade for smooth transitions

    for s, e in silences:
        pause_len = e - s
        if pause_len < silence_cfg.min_silence_ms or silence_cfg.target_silence_ms >= pause_len:
            continue

        target = silence_cfg.target_silence_ms
        allowed_removed = int(round(pause_len * max(0.0, min(1.0, silence_cfg.max_removal_pct))))
        actual_removed = pause_len - target
        if actual_removed > allowed_removed:
            target = pause_len - allowed_removed

        left_keep = int(round((target * silence_cfg.edge_keep_ratio) / 2.0))
        right_keep = target - left_keep

        cut_start = s + left_keep
        cut_end = e - right_keep
        if cut_end > cut_start:
            # Get segment before the cut
            segment = audio[cursor:cut_start]
            
            # Apply crossfade at cut boundaries to smooth the transition
            if len(out) > crossfade_ms and len(segment) > crossfade_ms:
                fade_len = min(crossfade_ms, len(out), len(segment))
                before_fade = out[:-fade_len]
                fade_out_portion = out[-fade_len:].fade_out(fade_len)
                fade_in_portion = segment[:fade_len].fade_in(fade_len)
                crossfaded = fade_out_portion.overlay(fade_in_portion)
                out = before_fade + crossfaded + segment[fade_len:]
            else:
                out += segment
            
            cursor = cut_end
            edits.append((cut_start, cut_end, cut_end - cut_start))

    # Handle final segment with crossfade
    if cursor < len(audio):
        final_segment = audio[cursor:]
        if len(out) > crossfade_ms and len(final_segment) > crossfade_ms:
            fade_len = min(crossfade_ms, len(out), len(final_segment))
            before_fade = out[:-fade_len]
            fade_out_portion = out[-fade_len:].fade_out(fade_len)
            fade_in_portion = final_segment[:fade_len].fade_in(fade_len)
            crossfaded = fade_out_portion.overlay(fade_in_portion)
            out = before_fade + crossfaded + final_segment[fade_len:]
        else:
            out += final_segment
    
    return out, edits
