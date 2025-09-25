from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from pydub import AudioSegment


def normalize_master(audio_in: Path, audio_out: Path, cfg: Dict[str, Any], log: List[str]) -> Dict[str, Any]:
    """Parity-preserving master step.

    Current project does not apply a distinct final loudness/true-peak stage in processor.
    To preserve behavior, this function copies input audio to the requested output path
    using the suffix-derived format, without adding logs beyond what the caller already emits.
    """
    seg = AudioSegment.from_file(audio_in)
    fmt = audio_out.suffix.lstrip(".") or "mp3"
    audio_out.parent.mkdir(parents=True, exist_ok=True)
    seg.export(audio_out, format=fmt)
    # Return lightweight metrics without changing log order/text
    metrics: Dict[str, Any] = {
        "duration_ms": int(len(seg)),
        "sr": getattr(seg, "frame_rate", None),
    }
    return metrics


def mux_tracks(program_in: Path, bed_in: Optional[Path], out_path: Path, cfg: Dict[str, Any], log: List[str]) -> Dict[str, Any]:
    """Parity-preserving mux step.

    In the current flow, background music is applied earlier in the pipeline.
    Maintain behavior by copying the program track to out_path (no extra logs here).
    If a bed is provided and cfg requests it at export-time, overlay at 0ms.
    """
    prog = AudioSegment.from_file(program_in)
    if bed_in and cfg.get("apply_bed_at_export"):
        bed = AudioSegment.from_file(bed_in)
        try:
            bed_gain = float(cfg.get("bed_gain_db", 0.0))
            bed = bed.apply_gain(bed_gain)
        except Exception:
            pass
        out = prog.overlay(bed, position=0)
        applied = True
    else:
        out = prog
        applied = False
    fmt = out_path.suffix.lstrip(".") or "mp3"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.export(out_path, format=fmt)
    return {"bed_applied": applied, "duration_ms": int(len(out))}


def write_derivatives(master_in: Path, outputs: Dict[str, Path], cfg: Dict[str, Any], log: List[str]) -> Dict[str, Any]:
    """Write derivative formats from the master file paths.

    The current monolith emits a single mp3 via pydub. Preserve behavior by exporting
    to the provided targets without emitting additional logs.
    """
    seg = AudioSegment.from_file(master_in)
    metrics: Dict[str, Any] = {"written": []}
    for label, out_path in (outputs or {}).items():
        try:
            fmt = out_path.suffix.lstrip(".") or "mp3"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            seg.export(out_path, format=fmt)
            metrics["written"].append({"label": label, "path": str(out_path)})
        except Exception:
            # keep silent to preserve existing logging
            pass
    return metrics


def embed_metadata(final_path: Path, metadata: Dict[str, Any], cover_path: Optional[Path], chapters: Optional[List[Dict[str, Any]]], log: List[str]) -> None:
    """Embed tags/cover/chapters.

    Current code path does not embed tags in processor; keep a safe no-op to preserve logs.
    Implementations can be added later without changing existing log order.
    """
    # Intentionally no-op to preserve identical logging behavior
    return None


__all__ = [
    "normalize_master",
    "mux_tracks",
    "write_derivatives",
    "embed_metadata",
]
