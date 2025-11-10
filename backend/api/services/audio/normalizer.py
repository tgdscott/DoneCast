"""Program-loudness normalization using ffmpeg loudnorm filter.

This module provides two-pass loudness normalization for non-Pro tier episodes.
Pro tier episodes use Auphonic for professional audio processing and skip this normalization.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


def _run_ffmpeg(cmd: List[str], log_lines: Optional[List[str]] = None) -> tuple[str, str, int]:
    """Run ffmpeg command and capture stdout/stderr.
    
    Args:
        cmd: ffmpeg command as list of strings
        log_lines: Optional list to append log messages to
        
    Returns:
        Tuple of (stdout, stderr, returncode)
        
    Raises:
        RuntimeError: If command fails (non-zero return code)
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        
        if log_lines is not None:
            if result.stdout:
                log_lines.append(f"[AUDIO_NORM] ffmpeg stdout: {result.stdout[:500]}")
            if result.stderr:
                log_lines.append(f"[AUDIO_NORM] ffmpeg stderr: {result.stderr[:500]}")
        
        if result.returncode != 0:
            error_msg = f"ffmpeg failed with return code {result.returncode}"
            if result.stderr:
                error_msg += f": {result.stderr[:500]}"
            raise RuntimeError(error_msg)
        
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"ffmpeg command timed out: {e}") from e
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found in PATH. Please install ffmpeg.") from None


def _parse_loudnorm_json(text: str) -> Dict[str, float]:
    """Parse loudnorm JSON output from ffmpeg.
    
    Args:
        text: ffmpeg stdout text containing JSON
        
    Returns:
        Dict with keys: input_i, input_lra, input_tp, input_thresh, target_offset
        
    Raises:
        ValueError: If JSON cannot be parsed or required keys are missing
    """
    # Find JSON block in output (usually between { and })
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    
    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        raise ValueError("No JSON found in ffmpeg output")
    
    json_str = text[start_idx:end_idx + 1]
    
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON: {e}") from e
    
    # Extract required keys
    required_keys = ["input_i", "input_lra", "input_tp", "input_thresh", "target_offset"]
    result = {}
    
    for key in required_keys:
        if key not in data:
            raise ValueError(f"Missing required key in loudnorm output: {key}")
        try:
            result[key] = float(data[key])
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid value for {key}: {data[key]}") from e
    
    return result


def _get_audio_duration(input_path: Path) -> float:
    """Get audio duration in seconds using ffprobe.
    
    Args:
        input_path: Path to audio file
        
    Returns:
        Duration in seconds
        
    Raises:
        RuntimeError: If ffprobe fails or duration cannot be determined
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(input_path),
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        duration = float(result.stdout.strip())
        return duration
    except (subprocess.CalledProcessError, ValueError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"Failed to get audio duration: {e}") from e


def run_loudnorm_two_pass(
    input_path: Path,
    output_path: Path,
    target_lufs: float = -16.0,
    tp_ceil: float = -1.0,
    log_lines: Optional[List[str]] = None,
) -> None:
    """Run two-pass loudness normalization using ffmpeg loudnorm filter.
    
    Pass 1: Analyze audio to get measured values
    Pass 2: Apply normalization with measured values for accurate targeting
    
    Args:
        input_path: Path to input audio file
        output_path: Path to write normalized output
        target_lufs: Target integrated loudness in LUFS (default -16.0)
        tp_ceil: True-peak ceiling in dBTP (default -1.0)
        log_lines: Optional list to append log messages to
        
    Raises:
        RuntimeError: If normalization fails
        ValueError: If output duration differs significantly from input
    """
    if log_lines is None:
        log_lines = []
    
    log_lines.append(f"[AUDIO_NORM] Starting two-pass normalization: target={target_lufs} LUFS, TP={tp_ceil} dBTP")
    
    # Get input duration for validation
    try:
        input_duration = _get_audio_duration(input_path)
        log_lines.append(f"[AUDIO_NORM] Input duration: {input_duration:.2f}s")
    except Exception as e:
        log_lines.append(f"[AUDIO_NORM] WARNING: Could not get input duration: {e}")
        input_duration = None
    
    # Pass 1: Analyze
    log_lines.append("[AUDIO_NORM] Pass 1: Analyzing audio...")
    pass1_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-y",
        "-i", str(input_path),
        "-af", f"loudnorm=I={target_lufs}:TP={tp_ceil}:LRA=11:print_format=json",
        "-f", "null",
        "-",
    ]
    
    try:
        stdout, stderr, _ = _run_ffmpeg(pass1_cmd, log_lines)
        
        # Parse JSON from stdout
        try:
            measured = _parse_loudnorm_json(stdout)
            log_lines.append(
                f"[AUDIO_NORM] Measured: I={measured['input_i']:.2f} LUFS, "
                f"LRA={measured['input_lra']:.2f} LU, TP={measured['input_tp']:.2f} dBTP, "
                f"thresh={measured['input_thresh']:.2f} dBFS, offset={measured['target_offset']:.2f} dB"
            )
        except ValueError as e:
            log_lines.append(f"[AUDIO_NORM] WARNING: Failed to parse pass 1 JSON: {e}, falling back to single-pass")
            # Fall back to single-pass
            _run_loudnorm_single_pass(input_path, output_path, target_lufs, tp_ceil, log_lines)
            return
        
    except RuntimeError as e:
        log_lines.append(f"[AUDIO_NORM] WARNING: Pass 1 failed: {e}, falling back to single-pass")
        _run_loudnorm_single_pass(input_path, output_path, target_lufs, tp_ceil, log_lines)
        return
    
    # Pass 2: Apply normalization
    log_lines.append("[AUDIO_NORM] Pass 2: Applying normalization...")
    pass2_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-y",
        "-i", str(input_path),
        "-af", (
            f"loudnorm=I={target_lufs}:TP={tp_ceil}:LRA=11:"
            f"measured_I={measured['input_i']}:measured_LRA={measured['input_lra']}:"
            f"measured_TP={measured['input_tp']}:measured_thresh={measured['input_thresh']}:"
            f"offset={measured['target_offset']}:linear=true:print_format=summary,"
            f"alimiter=limit={tp_ceil}"
        ),
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(output_path),
    ]
    
    try:
        stdout, stderr, _ = _run_ffmpeg(pass2_cmd, log_lines)
        
        # Extract final loudness from summary (if present)
        if "Input Integrated" in stdout or "Output Integrated" in stdout:
            log_lines.append(f"[AUDIO_NORM] Pass 2 summary: {stdout[:200]}")
        
        # Validate output duration
        if input_duration is not None:
            try:
                output_duration = _get_audio_duration(output_path)
                duration_diff_pct = abs(output_duration - input_duration) / input_duration * 100
                
                if duration_diff_pct > 0.5:
                    raise ValueError(
                        f"Output duration differs by {duration_diff_pct:.2f}% "
                        f"(input: {input_duration:.2f}s, output: {output_duration:.2f}s). "
                        "This may indicate processing failure."
                    )
                
                log_lines.append(
                    f"[AUDIO_NORM] Duration validation: input={input_duration:.2f}s, "
                    f"output={output_duration:.2f}s, diff={duration_diff_pct:.2f}%"
                )
            except Exception as e:
                log_lines.append(f"[AUDIO_NORM] WARNING: Could not validate output duration: {e}")
        
        log_lines.append(f"[AUDIO_NORM] ✅ Normalization completed successfully: {output_path.name}")
        
    except RuntimeError as e:
        log_lines.append(f"[AUDIO_NORM] ERROR: Pass 2 failed: {e}")
        raise


def _run_loudnorm_single_pass(
    input_path: Path,
    output_path: Path,
    target_lufs: float,
    tp_ceil: float,
    log_lines: Optional[List[str]] = None,
) -> None:
    """Run single-pass loudness normalization (fallback when two-pass fails).
    
    Args:
        input_path: Path to input audio file
        output_path: Path to write normalized output
        target_lufs: Target integrated loudness in LUFS
        tp_ceil: True-peak ceiling in dBTP
        log_lines: Optional list to append log messages to
    """
    if log_lines is None:
        log_lines = []
    
    log_lines.append("[AUDIO_NORM] Using single-pass normalization (fallback mode)")
    
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-y",
        "-i", str(input_path),
        "-af", f"loudnorm=I={target_lufs}:TP={tp_ceil}:LRA=11:linear=true,alimiter=limit={tp_ceil}",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(output_path),
    ]
    
    _run_ffmpeg(cmd, log_lines)
    log_lines.append(f"[AUDIO_NORM] ✅ Single-pass normalization completed: {output_path.name}")


__all__ = ["run_loudnorm_two_pass"]

