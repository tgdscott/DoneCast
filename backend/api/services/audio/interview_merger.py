"""
Interview Audio Merger

Merges multiple audio tracks (e.g., from Zoom separate recordings) into a single
podcast-ready audio file with per-track gain control and sync offset support.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from pydub import AudioSegment
from pydub.utils import make_chunks

log = logging.getLogger(__name__)


class InterviewMerger:
    """Merges multiple interview audio tracks into a single file."""
    
    def __init__(
        self,
        target_sample_rate: int = 44100,
        target_channels: int = 1,  # Mono for podcast
        target_format: str = "mp3",
    ):
        """
        Initialize merger with target audio settings.
        
        Args:
            target_sample_rate: Output sample rate (Hz)
            target_channels: Output channels (1=mono, 2=stereo)
            target_format: Output format (mp3, wav, etc.)
        """
        self.target_sample_rate = target_sample_rate
        self.target_channels = target_channels
        self.target_format = target_format
    
    def merge_tracks(
        self,
        tracks: List[Dict[str, any]],
        output_path: Path,
        default_gain_db: float = 0.0,
        sync_offsets_ms: Optional[List[int]] = None,
    ) -> Dict[str, any]:
        """
        Merge multiple audio tracks into a single file.
        
        Args:
            tracks: List of track dictionaries with:
                - "path": Path to audio file
                - "gain_db": Optional gain adjustment in dB (default: 0.0)
                - "pan": Optional panning (-1.0 to 1.0, 0=center)
            output_path: Path to save merged output
            default_gain_db: Default gain if not specified per track
            sync_offsets_ms: Optional list of sync offsets in milliseconds for each track
        
        Returns:
            Dictionary with merge results:
                - "duration_ms": Final duration
                - "tracks_merged": Number of tracks
                - "output_path": Path to output file
        """
        if not tracks:
            raise ValueError("At least one track is required")
        
        log.info(f"[interview_merger] Merging {len(tracks)} tracks")
        
        # Load all tracks
        audio_segments = []
        for i, track_info in enumerate(tracks):
            track_path = Path(track_info["path"])
            if not track_path.exists():
                raise FileNotFoundError(f"Track file not found: {track_path}")
            
            log.info(f"[interview_merger] Loading track {i+1}: {track_path.name}")
            
            # Load audio
            try:
                audio = AudioSegment.from_file(str(track_path))
            except Exception as e:
                log.error(f"[interview_merger] Failed to load {track_path}: {e}", exc_info=True)
                raise
            
            # Normalize sample rate and channels
            if audio.frame_rate != self.target_sample_rate:
                audio = audio.set_frame_rate(self.target_sample_rate)
            
            if audio.channels != self.target_channels:
                audio = audio.set_channels(self.target_channels)
            
            # Apply sync offset if provided
            if sync_offsets_ms and i < len(sync_offsets_ms):
                offset_ms = sync_offsets_ms[i]
                if offset_ms > 0:
                    # Add silence at the beginning
                    audio = AudioSegment.silent(duration=offset_ms) + audio
                elif offset_ms < 0:
                    # Trim from the beginning
                    audio = audio[abs(offset_ms):]
            
            # Apply gain adjustment
            gain_db = track_info.get("gain_db", default_gain_db)
            if gain_db != 0.0:
                audio = audio.apply_gain(gain_db)
                log.info(f"[interview_merger] Applied {gain_db}dB gain to track {i+1}")
            
            audio_segments.append(audio)
        
        # Find the longest track (will be our base duration)
        max_duration = max(len(seg) for seg in audio_segments)
        log.info(f"[interview_merger] Longest track: {max_duration}ms")
        
        # Pad shorter tracks with silence to match longest
        for i, seg in enumerate(audio_segments):
            if len(seg) < max_duration:
                padding = AudioSegment.silent(duration=max_duration - len(seg))
                audio_segments[i] = seg + padding
                log.info(f"[interview_merger] Padded track {i+1} with {len(padding)}ms silence")
        
        # Mix all tracks together
        log.info("[interview_merger] Mixing tracks...")
        merged = audio_segments[0]
        for i, seg in enumerate(audio_segments[1:], start=1):
            # Overlay tracks (mix them together)
            merged = merged.overlay(seg)
            log.info(f"[interview_merger] Mixed track {i+1} into merged audio")
        
        # Normalize the final mix to prevent clipping
        # Use headroom to avoid distortion
        headroom_db = -3.0  # Leave 3dB headroom
        max_possible_gain = headroom_db - merged.max_possible_amplitude
        if max_possible_gain > 0:
            merged = merged.apply_gain(max_possible_gain)
            log.info(f"[interview_merger] Applied normalization gain: {max_possible_gain}dB")
        
        # Export merged audio
        output_path.parent.mkdir(parents=True, exist_ok=True)
        merged.export(
            str(output_path),
            format=self.target_format,
            bitrate="192k" if self.target_format == "mp3" else None,
        )
        
        log.info(f"[interview_merger] Merged audio saved to {output_path}")
        
        return {
            "duration_ms": len(merged),
            "tracks_merged": len(tracks),
            "output_path": str(output_path),
            "sample_rate": self.target_sample_rate,
            "channels": self.target_channels,
            "format": self.target_format,
        }


def merge_interview_tracks(
    track_paths: List[str],
    output_path: str,
    gains_db: Optional[List[float]] = None,
    sync_offsets_ms: Optional[List[int]] = None,
) -> Dict[str, any]:
    """
    Convenience function to merge interview tracks.
    
    Args:
        track_paths: List of paths to audio files
        output_path: Path to save merged output
        gains_db: Optional list of gain adjustments per track (dB)
        sync_offsets_ms: Optional list of sync offsets per track (ms)
    
    Returns:
        Merge results dictionary
    """
    tracks = []
    for i, path in enumerate(track_paths):
        track_info = {"path": path}
        if gains_db and i < len(gains_db):
            track_info["gain_db"] = gains_db[i]
        tracks.append(track_info)
    
    merger = InterviewMerger()
    return merger.merge_tracks(
        tracks=tracks,
        output_path=Path(output_path),
        sync_offsets_ms=sync_offsets_ms,
    )


