"""
Episode Length Management Module

Provides functionality to automatically adjust episode length through:
1. Dynamic silence removal settings
2. Speed adjustments  
3. Filler word removal control

The system tries to achieve target length with minimal changes, progressively
applying more aggressive techniques as needed.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from pydub import AudioSegment

logger = logging.getLogger(__name__)


def calculate_episode_length(
    template,
    main_content_duration_ms: int,
    segment_overrides: Optional[Dict[str, Any]] = None
) -> int:
    """
    Calculate projected episode length including all template segments.
    
    Args:
        template: PodcastTemplate object with segments_json and timing_json
        main_content_duration_ms: Duration of main content in milliseconds
        segment_overrides: Dict of per-episode segment overrides (e.g., TTS values)
    
    Returns:
        Total projected episode duration in milliseconds
    """
    try:
        # Parse template segments
        segments_json = getattr(template, 'segments_json', '[]')
        segments = json.loads(segments_json) if isinstance(segments_json, str) else segments_json
        
        # Start with main content duration
        total_duration_ms = main_content_duration_ms
        
        # Add duration of each template segment
        for segment in segments:
            segment_type = segment.get('segment_type')
            source = segment.get('source', {})
            
            # Estimate segment duration based on type
            if segment_type == 'content':
                # Main content already counted
                continue
            elif source.get('source_type') == 'static':
                # Static files - we'd need to check actual file duration
                # For now, estimate average of 30 seconds for intro/outro
                if segment_type in ('intro', 'outro'):
                    total_duration_ms += 30000  # 30 seconds estimate
                elif segment_type == 'commercial':
                    total_duration_ms += 60000  # 60 seconds estimate
                else:
                    total_duration_ms += 5000   # 5 seconds for transitions/effects
            elif source.get('source_type') in ('tts', 'ai_generated'):
                # TTS segments - estimate based on word count or use override
                script = source.get('script', '') or source.get('prompt', '')
                # Rough estimate: 150 words per minute = 2.5 words per second = 400ms per word
                word_count = len(script.split())
                estimated_ms = word_count * 400
                total_duration_ms += max(estimated_ms, 5000)  # Minimum 5 seconds
        
        logger.info(
            "[length_mgmt] Projected episode length: %.2f minutes (main: %.2f min, segments: %.2f min)",
            total_duration_ms / 60000,
            main_content_duration_ms / 60000,
            (total_duration_ms - main_content_duration_ms) / 60000
        )
        return total_duration_ms
        
    except Exception as e:
        logger.warning("[length_mgmt] Failed to calculate episode length, using main content only: %s", e)
        return main_content_duration_ms


def analyze_silence_potential(
    words_json_path: Optional[Path],
    current_settings: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Analyze transcript to identify silence gaps and calculate potential time savings.
    
    Args:
        words_json_path: Path to transcript JSON file with word timestamps
        current_settings: Current cleanup settings dict
    
    Returns:
        Dict containing:
            - total_silences: Count of silence gaps
            - total_silence_duration_ms: Total duration of all silences
            - potential_savings_ms: Maximum time that could be saved
            - silence_distribution: List of (gap_duration_ms, count) tuples
    """
    if not words_json_path or not Path(words_json_path).exists():
        logger.warning("[length_mgmt] No transcript available for silence analysis")
        return {
            'total_silences': 0,
            'total_silence_duration_ms': 0,
            'potential_savings_ms': 0,
            'silence_distribution': []
        }
    
    try:
        with open(words_json_path, 'r', encoding='utf-8') as f:
            words = json.load(f)
        
        if not words or not isinstance(words, list):
            return {
                'total_silences': 0,
                'total_silence_duration_ms': 0,
                'potential_savings_ms': 0,
                'silence_distribution': []
            }
        
        # Calculate gaps between words
        gaps = []
        for i in range(len(words) - 1):
            current_word = words[i]
            next_word = words[i + 1]
            
            current_end = current_word.get('end', 0)
            next_start = next_word.get('start', 0)
            
            gap_ms = int((next_start - current_end) * 1000)
            if gap_ms > 0:
                gaps.append(gap_ms)
        
        # Analyze gap distribution
        if not gaps:
            return {
                'total_silences': 0,
                'total_silence_duration_ms': 0,
                'potential_savings_ms': 0,
                'silence_distribution': []
            }
        
        # Current settings for min_silence detection
        current_min_silence_ms = 1500
        if current_settings:
            max_pause_seconds = current_settings.get('maxPauseSeconds', 1.5)
            current_min_silence_ms = int(float(max_pause_seconds) * 1000)
        
        # Count silences that would be detected
        detectable_silences = [g for g in gaps if g >= current_min_silence_ms]
        total_silence_ms = sum(detectable_silences)
        
        # Calculate potential savings with different thresholds
        # We can compress silences down to target (e.g., 500ms)
        target_silence_ms = 500
        if current_settings:
            target_pause_seconds = current_settings.get('targetPauseSeconds', 0.5)
            target_silence_ms = int(float(target_pause_seconds) * 1000)
        
        potential_savings_ms = sum(max(0, g - target_silence_ms) for g in detectable_silences)
        
        # Create distribution buckets
        distribution = []
        buckets = [500, 1000, 1500, 2000, 3000, 5000, 10000, float('inf')]
        bucket_labels = ['0.5-1s', '1-1.5s', '1.5-2s', '2-3s', '3-5s', '5-10s', '10s+']
        
        for i, threshold in enumerate(buckets[:-1]):
            count = sum(1 for g in gaps if threshold <= g < buckets[i+1])
            if count > 0:
                avg_duration = sum(g for g in gaps if threshold <= g < buckets[i+1]) / count
                distribution.append({
                    'range': bucket_labels[i],
                    'count': count,
                    'avg_duration_ms': int(avg_duration)
                })
        
        result = {
            'total_silences': len(detectable_silences),
            'total_silence_duration_ms': total_silence_ms,
            'potential_savings_ms': potential_savings_ms,
            'silence_distribution': distribution,
            'current_min_threshold_ms': current_min_silence_ms,
            'current_target_ms': target_silence_ms
        }
        
        logger.info(
            "[length_mgmt] Silence analysis: %d gaps, %.2f sec total, %.2f sec potential savings",
            len(detectable_silences),
            total_silence_ms / 1000,
            potential_savings_ms / 1000
        )
        
        return result
        
    except Exception as e:
        logger.error("[length_mgmt] Failed to analyze silence potential: %s", e, exc_info=True)
        return {
            'total_silences': 0,
            'total_silence_duration_ms': 0,
            'potential_savings_ms': 0,
            'silence_distribution': []
        }


def calculate_optimal_silence_settings(
    current_length_ms: int,
    target_min_ms: int,
    target_max_ms: int,
    silence_potential: Dict[str, Any]
) -> Optional[Dict[str, int]]:
    """
    Calculate optimal silence removal settings to reach target length.
    
    Args:
        current_length_ms: Current episode length
        target_min_ms: Minimum target length (soft range)
        target_max_ms: Maximum target length (soft range)
        silence_potential: Output from analyze_silence_potential()
    
    Returns:
        Dict with 'min_silence_ms' and 'target_silence_ms', or None if no adjustment needed
    """
    # Check if we're already in target range
    if target_min_ms <= current_length_ms <= target_max_ms:
        logger.info("[length_mgmt] Episode already in target range, no silence adjustment needed")
        return None
    
    # Calculate how much we need to shorten/lengthen
    if current_length_ms > target_max_ms:
        # Too long - need to compress more silence
        needed_reduction_ms = current_length_ms - target_max_ms
        available_savings_ms = silence_potential.get('potential_savings_ms', 0)
        
        if available_savings_ms == 0:
            logger.warning("[length_mgmt] Episode too long but no silence to compress")
            return None
        
        # Calculate how aggressive we need to be
        # More aggressive = lower min_silence_ms threshold, lower target_silence_ms
        
        # Map needed reduction to threshold adjustment
        # If we need to save 50% of available, make settings more aggressive
        reduction_ratio = min(1.0, needed_reduction_ms / available_savings_ms)
        
        # Min silence threshold: 500ms (most aggressive) to 3500ms (least aggressive)
        # Target silence: 250ms (most aggressive) to 1000ms (least aggressive)
        min_silence_ms = int(3500 - (reduction_ratio * 3000))  # 3500 -> 500
        target_silence_ms = int(1000 - (reduction_ratio * 750))  # 1000 -> 250
        
        logger.info(
            "[length_mgmt] Episode too long by %.2f sec, adjusting silence settings (ratio: %.2f)",
            needed_reduction_ms / 1000,
            reduction_ratio
        )
        
        return {
            'min_silence_ms': max(500, min(3500, min_silence_ms)),
            'target_silence_ms': max(250, min(1000, target_silence_ms)),
            'detect_threshold_dbfs': -50  # Keep consistent
        }
    
    else:
        # Too short - relax silence removal to preserve length
        logger.info("[length_mgmt] Episode too short, relaxing silence removal")
        
        # Use most conservative settings
        return {
            'min_silence_ms': 3500,  # Only remove very long pauses
            'target_silence_ms': 1000,  # Keep silences longer
            'detect_threshold_dbfs': -50
        }


def apply_speed_adjustment(
    audio_path: Path,
    speed_factor: float,
    output_path: Path
) -> Path:
    """
    Apply speed adjustment to audio file while preserving pitch.
    
    Args:
        audio_path: Path to input audio file
        speed_factor: Speed multiplier (e.g., 1.05 for 5% faster, 0.95 for 5% slower)
        output_path: Path for output audio file
    
    Returns:
        Path to speed-adjusted audio file
    """
    try:
        import subprocess
        
        # Use ffmpeg atempo filter to change speed without changing pitch
        # atempo can only do 0.5-2.0x, so for larger changes we need to chain
        atempo_filters = []
        remaining_factor = speed_factor
        
        while remaining_factor > 2.0:
            atempo_filters.append("atempo=2.0")
            remaining_factor /= 2.0
        
        while remaining_factor < 0.5:
            atempo_filters.append("atempo=0.5")
            remaining_factor /= 0.5
        
        if remaining_factor != 1.0:
            atempo_filters.append(f"atempo={remaining_factor}")
        
        if not atempo_filters:
            # No change needed
            logger.info("[length_mgmt] No speed adjustment needed (factor=1.0)")
            return audio_path
        
        filter_chain = ",".join(atempo_filters)
        
        cmd = [
            "ffmpeg",
            "-i", str(audio_path),
            "-filter:a", filter_chain,
            "-y",  # Overwrite output
            str(output_path)
        ]
        
        logger.info("[length_mgmt] Applying speed adjustment: factor=%.3f, filter=%s", speed_factor, filter_chain)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg speed adjustment failed: {result.stderr}")
        
        if not output_path.exists():
            raise RuntimeError("FFmpeg did not create output file")
        
        logger.info("[length_mgmt] Speed adjustment complete: %s", output_path)
        return output_path
        
    except Exception as e:
        logger.error("[length_mgmt] Failed to apply speed adjustment: %s", e, exc_info=True)
        raise


def determine_strategy(
    template_settings,
    projected_length_ms: int,
    silence_potential: Dict[str, Any],
    soft_min: int,
    soft_max: int,
    hard_min: int,
    hard_max: int
) -> Dict[str, Any]:
    """
    Determine the optimal strategy for adjusting episode length.
    
    Decision flow:
    1. If within soft range: no action
    2. If outside soft but inside hard: adjust silence settings
    3. If outside hard after max silence adjustment: apply speed adjustment
    4. If still too short after all adjustments: skip filler removal
    
    Args:
        template_settings: Template object with settings
        projected_length_ms: Projected episode length
        silence_potential: Silence analysis results
        soft_min, soft_max: Soft range boundaries (ms)
        hard_min, hard_max: Hard range boundaries (ms)
    
    Returns:
        Dict with 'action' and 'params' keys
    """
    logger.info(
        "[length_mgmt] Determining strategy: length=%.2f min, soft=[%.2f-%.2f], hard=[%.2f-%.2f]",
        projected_length_ms / 60000,
        soft_min / 60000,
        soft_max / 60000,
        hard_min / 60000,
        hard_max / 60000
    )
    
    # Step 1: Check if already in soft range
    if soft_min <= projected_length_ms <= soft_max:
        logger.info("[length_mgmt] Episode within soft range, no action needed")
        return {"action": "no_change", "params": {}}
    
    # Step 2: Outside soft range but inside hard range
    if hard_min <= projected_length_ms <= hard_max:
        # Try to adjust with silence removal settings
        if projected_length_ms > soft_max:
            # Too long - compress silences
            target_length_ms = soft_max
        else:
            # Too short - relax silence compression
            target_length_ms = soft_min
        
        silence_settings = calculate_optimal_silence_settings(
            current_length_ms=projected_length_ms,
            target_min_ms=soft_min,
            target_max_ms=soft_max,
            silence_potential=silence_potential
        )
        
        if silence_settings:
            logger.info("[length_mgmt] Strategy: adjust silence removal")
            return {
                "action": "adjust_silence",
                "params": silence_settings
            }
        else:
            logger.info("[length_mgmt] Silence adjustment not effective, no action")
            return {"action": "no_change", "params": {}}
    
    # Step 3: Outside hard range - need speed adjustment
    if projected_length_ms < hard_min:
        # Too short even after relaxing silence removal
        logger.info("[length_mgmt] Episode too short, will apply slowdown after assembly")
        return {
            "action": "apply_speed",
            "params": {
                "speed_factor": 0.95,  # Slow down (user setting will be used)
                "target": "lengthen"
            }
        }
    
    elif projected_length_ms > hard_max:
        # Too long even after aggressive silence compression
        logger.info("[length_mgmt] Episode too long, will apply speedup after assembly")
        return {
            "action": "apply_speed",
            "params": {
                "speed_factor": 1.05,  # Speed up (user setting will be used)
                "target": "shorten"
            }
        }
    
    # Fallback
    return {"action": "no_change", "params": {}}
