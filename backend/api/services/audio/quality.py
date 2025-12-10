from __future__ import annotations

import logging
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional, Any

from infrastructure import gcs, storage

log = logging.getLogger("audio.quality")


def _download_to_temp(gcs_path: str) -> Optional[Path]:
    """Download a gs://bucket/key or local path to a temp file and return Path."""
    try:
        if not gcs_path:
            return None
        p = str(gcs_path)
        if p.startswith("gs://"):
            without = p[len("gs://") :]
            parts = without.split("/", 1)
            if len(parts) != 2:
                log.warning("audio.quality: invalid gs:// path %s", p)
                return None
            bucket, key = parts
            data = gcs.download_bytes(bucket, key)
            if data is None:
                log.warning("audio.quality: gcs object not found %s", p)
                return None
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=Path(key).suffix)
            tf.write(data)
            tf.flush()
            tf.close()
            return Path(tf.name)
        else:
            # Local path - just return Path if exists
            path = Path(p)
            if path.exists():
                return path
            # Maybe it's a bare filename stored in configured storage
            # Try storage.download_bytes using configured bucket and key
            data = storage.download_bytes(os.getenv("GCS_BUCKET", ""), p)
            if data:
                tf = tempfile.NamedTemporaryFile(delete=False, suffix=path.suffix or ".wav")
                tf.write(data)
                tf.flush()
                tf.close()
                return Path(tf.name)
            log.warning("audio.quality: local file not found: %s", p)
            return None
    except Exception as e:
        log.warning("audio.quality: download_to_temp failed: %s", e, exc_info=True)
        return None


def _run_ffprobe_duration(path: Path) -> Optional[float]:
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        s = out.decode("utf-8").strip()
        return float(s)
    except Exception:
        return None


def _run_ffmpeg_ebur128(path: Path) -> Optional[float]:
    """Try to get integrated loudness (LUFS) from ffmpeg ebur128 filter."""
    try:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "ebur128=framelog=verbose",
            "-f",
            "null",
            "-",
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, stderr = proc.communicate(timeout=60)
        text = stderr.decode("utf-8", errors="ignore")
        # Look for lines like 'I: -21.0 LUFS'
        for line in reversed(text.splitlines()):
            if "I:" in line and "LUFS" in line:
                try:
                    parts = line.split()
                    # find token that looks like -21.0
                    for tok in parts:
                        if tok.replace("-", "").replace(".", "").isdigit():
                            return float(tok)
                except Exception:
                    continue
        return None
    except Exception:
        return None


def _run_ffmpeg_volumedetect(path: Path) -> Dict[str, Optional[float]]:
    """Return mean_volume and max_volume in dB from ffmpeg volumedetect filter."""
    try:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, stderr = proc.communicate(timeout=60)
        text = stderr.decode("utf-8", errors="ignore")
        mean = None
        maxv = None
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("mean_volume:"):
                try:
                    mean = float(line.split(":", 1)[1].strip().split()[0])
                except Exception:
                    pass
            if line.startswith("max_volume:"):
                try:
                    maxv = float(line.split(":", 1)[1].strip().split()[0])
                except Exception:
                    pass
        return {"mean_volume_db": mean, "max_volume_db": maxv}
    except Exception:
        return {"mean_volume_db": None, "max_volume_db": None}


def analyze_audio_file(main_content_filename: str) -> Dict[str, Any]:
    """Analyze audio and return quality metrics and a normalized label.

    Returns dict: {
        "integrated_lufs": float|None,
        "duration_seconds": float|None,
        "mean_volume_db": float|None,
        "max_volume_db": float|None,
        "signal_to_noise_ratio": float|None,
        "quality_label": str
    }
    """
    temp_path = None
    try:
        temp_path = _download_to_temp(main_content_filename)
        if temp_path is None:
            log.warning("audio.quality: could not obtain file for analysis: %s", main_content_filename)
            return {"integrated_lufs": None, "duration_seconds": None, "mean_volume_db": None, "max_volume_db": None, "signal_to_noise_ratio": None, "quality_label": "unknown"}

        # duration
        duration = _run_ffprobe_duration(temp_path)
        lufs = _run_ffmpeg_ebur128(temp_path)
        vol = _run_ffmpeg_volumedetect(temp_path)
        mean_db = vol.get("mean_volume_db")
        max_db = vol.get("max_volume_db")

        # crude SNR estimate: use max - mean as proxy (not true SNR)
        snr = None
        try:
            if mean_db is not None and max_db is not None:
                snr = max_db - mean_db
        except Exception:
            snr = None

        # Map to dnsmos-like surrogate (0-5) from snr/mean
        dnsmos = None
        try:
            if snr is not None:
                # heuristic mapping
                if snr < 0:
                    dnsmos = 1.5
                elif snr < 5:
                    dnsmos = 2.5
                elif snr < 10:
                    dnsmos = 3.2
                elif snr < 15:
                    dnsmos = 3.8
                else:
                    dnsmos = 4.2
        except Exception:
            dnsmos = None

        # Classify into labels used by decision matrix
        label = "good"
        try:
            # Add an "abysmal" tier for audio that is effectively unpublishable
            if (dnsmos is not None and dnsmos < 2.0) or (snr is not None and snr < -5):
                label = "abysmal"
            elif (dnsmos is not None and dnsmos < 2.5) or (snr is not None and snr < 0):
                label = "incredibly_bad"
            elif (dnsmos is not None and dnsmos < 3.0) or (snr is not None and snr < 5):
                label = "very_bad"
            elif (dnsmos is not None and dnsmos < 3.5) or (snr is not None and snr < 10):
                label = "fairly_bad"
            elif (dnsmos is not None and dnsmos <= 4.0) or (snr is not None and snr <= 15):
                label = "slightly_bad"
            else:
                label = "good"
        except Exception:
            label = "unknown"

        return {
            "integrated_lufs": lufs,
            "duration_seconds": duration,
            "mean_volume_db": mean_db,
            "max_volume_db": max_db,
            "signal_to_noise_ratio": snr,
            "dnsmos_score": dnsmos,
            "quality_label": label,
        }

    finally:
        try:
            if temp_path and temp_path.exists() and str(temp_path).startswith(tempfile.gettempdir()):
                temp_path.unlink(missing_ok=True)
        except Exception:
            pass
