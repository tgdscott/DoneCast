#!/usr/bin/env python3
"""CLI utility for manual audio normalization testing and QA.

Usage:
    python scripts/normalize_audio.py --in input.mp3 --out output.mp3 [--lufs -16] [--tp -1]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.services.audio.normalizer import run_loudnorm_two_pass

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Normalize audio loudness using ffmpeg loudnorm filter"
    )
    parser.add_argument(
        "--in",
        dest="input_path",
        required=True,
        type=Path,
        help="Input audio file path"
    )
    parser.add_argument(
        "--out",
        dest="output_path",
        required=True,
        type=Path,
        help="Output audio file path"
    )
    parser.add_argument(
        "--lufs",
        type=float,
        default=-16.0,
        help="Target loudness in LUFS (default: -16.0)"
    )
    parser.add_argument(
        "--tp",
        type=float,
        default=-1.0,
        help="True-peak ceiling in dBTP (default: -1.0)"
    )
    
    args = parser.parse_args()
    
    # Validate input file exists
    if not args.input_path.exists():
        log.error(f"Input file not found: {args.input_path}")
        sys.exit(1)
    
    # Ensure output directory exists
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    
    log.info(f"Normalizing audio: {args.input_path.name} -> {args.output_path.name}")
    log.info(f"Target: {args.lufs} LUFS, True-peak ceiling: {args.tp} dBTP")
    
    try:
        norm_log: list[str] = []
        run_loudnorm_two_pass(
            input_path=args.input_path,
            output_path=args.output_path,
            target_lufs=args.lufs,
            tp_ceil=args.tp,
            log_lines=norm_log,
        )
        
        # Print all log messages
        for log_line in norm_log:
            print(log_line)
        
        log.info(f"✅ Normalization complete: {args.output_path}")
        sys.exit(0)
        
    except Exception as e:
        log.error(f"❌ Normalization failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

