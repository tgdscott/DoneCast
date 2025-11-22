"""
Zoom Recording Detection Utility

Detects Zoom recordings in default save locations across different operating systems.
Zoom typically saves recordings with separate audio tracks per participant.
"""
from __future__ import annotations

import os
import platform
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class ZoomRecording:
    """Represents a detected Zoom recording session."""
    session_name: str  # Meeting name or folder name
    session_path: Path  # Path to the recording folder
    audio_files: List[Tuple[Path, str]]  # List of (file_path, participant_name) tuples
    video_file: Optional[Path] = None  # Optional video file
    timestamp: Optional[str] = None  # Recording timestamp if detectable


def get_default_zoom_paths() -> List[Path]:
    """
    Get default Zoom recording paths based on operating system.
    
    Returns:
        List of potential Zoom recording directories
    """
    system = platform.system()
    paths = []
    
    if system == "Windows":
        # Windows: %USERPROFILE%\Documents\Zoom
        user_profile = os.getenv("USERPROFILE") or os.getenv("HOME")
        if user_profile:
            paths.append(Path(user_profile) / "Documents" / "Zoom")
        # Also check OneDrive Documents
        onedrive = os.getenv("OneDrive")
        if onedrive:
            paths.append(Path(onedrive) / "Documents" / "Zoom")
    
    elif system == "Darwin":  # macOS
        home = Path.home()
        paths.append(home / "Documents" / "Zoom")
        # Also check Desktop
        paths.append(home / "Desktop" / "Zoom")
    
    elif system == "Linux":
        home = Path.home()
        paths.append(home / "Documents" / "Zoom")
        paths.append(home / "Zoom")
    
    # Filter out paths that don't exist
    return [p for p in paths if p.exists()]


def detect_zoom_recordings(max_sessions: int = 10) -> List[ZoomRecording]:
    """
    Detect Zoom recording sessions in default locations.
    
    Args:
        max_sessions: Maximum number of sessions to return (most recent first)
    
    Returns:
        List of detected ZoomRecording objects
    """
    recordings = []
    zoom_paths = get_default_zoom_paths()
    
    if not zoom_paths:
        log.info("[zoom] No Zoom recording directories found")
        return recordings
    
    for zoom_path in zoom_paths:
        try:
            if not zoom_path.exists() or not zoom_path.is_dir():
                continue
            
            # Look for subdirectories (each meeting gets its own folder)
            for session_dir in sorted(zoom_path.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                if not session_dir.is_dir():
                    continue
                
                if len(recordings) >= max_sessions:
                    break
                
                recording = _parse_zoom_session(session_dir)
                if recording and recording.audio_files:
                    recordings.append(recording)
        
        except Exception as e:
            log.warning(f"[zoom] Error scanning {zoom_path}: {e}", exc_info=True)
    
    return recordings[:max_sessions]


def _parse_zoom_session(session_path: Path) -> Optional[ZoomRecording]:
    """
    Parse a Zoom session directory to extract audio files.
    
    Zoom typically saves:
    - audio_only.m4a (combined audio)
    - audio_only_1.m4a, audio_only_2.m4a (separate tracks per participant)
    - Or: participant_name_audio.m4a format
    
    Returns:
        ZoomRecording object if valid session found, None otherwise
    """
    if not session_path.is_dir():
        return None
    
    audio_files = []
    video_file = None
    
    # Common Zoom audio file patterns
    audio_patterns = [
        "audio_only.m4a",  # Combined audio
        "audio_only_*.m4a",  # Separate tracks (audio_only_1.m4a, etc.)
        "*_audio.m4a",  # Participant-specific (e.g., "John Doe_audio.m4a")
        "*.m4a",  # Any m4a file
        "*.mp3",  # MP3 format
        "*.wav",  # WAV format
    ]
    
    # Look for video file
    video_patterns = ["*.mp4", "*.mov", "*.mkv"]
    
    try:
        # Collect all audio files
        for pattern in audio_patterns:
            if "*" in pattern:
                # Use glob for patterns
                for audio_file in session_path.glob(pattern):
                    if audio_file.is_file():
                        # Try to extract participant name from filename
                        participant_name = _extract_participant_name(audio_file.name)
                        audio_files.append((audio_file, participant_name))
            else:
                # Direct filename match
                audio_file = session_path / pattern
                if audio_file.exists() and audio_file.is_file():
                    participant_name = _extract_participant_name(audio_file.name)
                    audio_files.append((audio_file, participant_name))
        
        # Look for video file
        for pattern in video_patterns:
            for vid_file in session_path.glob(pattern):
                if vid_file.is_file():
                    video_file = vid_file
                    break
            if video_file:
                break
        
        # Remove duplicates (same file path)
        seen_paths = set()
        unique_audio_files = []
        for file_path, participant_name in audio_files:
            if str(file_path) not in seen_paths:
                seen_paths.add(str(file_path))
                unique_audio_files.append((file_path, participant_name))
        
        if not unique_audio_files:
            return None
        
        # Sort audio files: prefer separate tracks over combined
        # audio_only_1.m4a, audio_only_2.m4a are better than audio_only.m4a
        def sort_key(item: Tuple[Path, str]) -> Tuple[bool, str]:
            file_path, _ = item
            name = file_path.name.lower()
            # Combined audio comes last
            is_combined = name == "audio_only.m4a"
            return (is_combined, name)
        
        unique_audio_files.sort(key=sort_key)
        
        return ZoomRecording(
            session_name=session_path.name,
            session_path=session_path,
            audio_files=unique_audio_files,
            video_file=video_file,
            timestamp=_extract_timestamp(session_path)
        )
    
    except Exception as e:
        log.warning(f"[zoom] Error parsing session {session_path}: {e}", exc_info=True)
        return None


def _extract_participant_name(filename: str) -> str:
    """
    Extract participant name from Zoom filename.
    
    Examples:
        "audio_only_1.m4a" -> "Participant 1"
        "John Doe_audio.m4a" -> "John Doe"
        "audio_only.m4a" -> "Combined Audio"
    """
    name_lower = filename.lower()
    
    # Check for numbered tracks
    if "audio_only_" in name_lower:
        # Extract number if present
        try:
            # audio_only_1.m4a -> "Participant 1"
            parts = name_lower.replace(".m4a", "").split("_")
            if len(parts) >= 3:
                num = parts[-1]
                if num.isdigit():
                    return f"Participant {num}"
        except Exception:
            pass
        return "Participant"
    
    # Check for participant-specific names
    if "_audio" in name_lower:
        # "John Doe_audio.m4a" -> "John Doe"
        participant = filename.split("_audio")[0]
        return participant.strip()
    
    # Default names
    if name_lower == "audio_only.m4a":
        return "Combined Audio"
    
    # Use filename stem as fallback
    return Path(filename).stem.replace("_", " ").title()


def _extract_timestamp(session_path: Path) -> Optional[str]:
    """Extract timestamp from session folder name or modification time."""
    try:
        # Try to parse from folder name (Zoom often uses timestamps)
        folder_name = session_path.name
        # Common formats: "Meeting Name 2024-01-15 14-30-00"
        # Or use modification time
        mtime = session_path.stat().st_mtime
        from datetime import datetime
        return datetime.fromtimestamp(mtime).isoformat()
    except Exception:
        return None


def get_zoom_recording_info(session_path: str) -> Optional[Dict]:
    """
    Get detailed info about a specific Zoom recording session.
    
    Args:
        session_path: Path to the Zoom session directory
    
    Returns:
        Dictionary with session information
    """
    path = Path(session_path)
    recording = _parse_zoom_session(path)
    
    if not recording:
        return None
    
    return {
        "session_name": recording.session_name,
        "session_path": str(recording.session_path),
        "audio_tracks": [
            {
                "path": str(audio_path),
                "participant_name": participant_name,
                "size_bytes": audio_path.stat().st_size if audio_path.exists() else 0,
            }
            for audio_path, participant_name in recording.audio_files
        ],
        "video_file": str(recording.video_file) if recording.video_file else None,
        "timestamp": recording.timestamp,
    }


