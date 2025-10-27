"""
Speaker Identification Audio Preprocessing

Prepends host and guest voice intros before main content audio to enable
AssemblyAI's speaker diarization to learn and consistently label speakers.

User flow:
1. Hosts record "Hi, my name is Scott" intros (one-time setup)
2. Guests record similar intros (per-episode if applicable)
3. System combines: [host1_intro] [host2_intro] [guest1_intro] [main_content]
4. AssemblyAI transcription learns voices from intros
5. Post-processing maps generic "Speaker A/B/C" to actual names
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, cast
from pydub import AudioSegment

logger = logging.getLogger(__name__)


def prepend_speaker_intros(
    main_audio_path: Path,
    podcast_speaker_intros: Optional[Dict[str, Any]],
    episode_guest_intros: Optional[List[Dict[str, Any]]],
    output_path: Optional[Path] = None
) -> Tuple[Path, float]:
    """
    Prepend host and guest voice intros before main content audio.
    
    Args:
        main_audio_path: Path to the main episode content audio file
        podcast_speaker_intros: Podcast-level speaker config from podcast.speaker_intros
            Format: {"hosts": [{"name": "Scott", "gcs_path": "gs://...", "duration_ms": 2000}]}
        episode_guest_intros: Episode-level guest config from episode.guest_intros
            Format: [{"name": "Sarah", "gcs_path": "gs://...", "duration_ms": 2000}]
        output_path: Optional custom output path (defaults to main_audio_path_with_intros.wav)
    
    Returns:
        Tuple of (output_file_path, total_intro_duration_seconds)
        
    Raises:
        FileNotFoundError: If main audio file doesn't exist
        Exception: If GCS download or audio processing fails
    """
    if not main_audio_path.exists():
        raise FileNotFoundError(f"Main audio file not found: {main_audio_path}")
    
    # Check if we have any intros to prepend
    has_host_intros = bool(podcast_speaker_intros and podcast_speaker_intros.get("hosts"))
    has_guest_intros = bool(episode_guest_intros)
    
    if not has_host_intros and not has_guest_intros:
        logger.info("[speaker_id] No speaker intros configured, skipping prepend")
        return main_audio_path, 0.0
    
    logger.info(
        "[speaker_id] Prepending speaker intros: hosts=%s, guests=%s",
        len(cast(Dict[str, Any], podcast_speaker_intros).get("hosts", [])) if has_host_intros else 0,
        len(episode_guest_intros) if has_guest_intros else 0
    )
    
    segments: List[AudioSegment] = []
    total_intro_duration_ms = 0
    gap_duration_ms = 500  # 0.5 second gap between intros
    
    # Add host intros (in order)
    if has_host_intros:
        hosts = cast(Dict[str, Any], podcast_speaker_intros)["hosts"]
        for idx, host in enumerate(hosts):
            host_name = host.get("name", f"Host {idx + 1}")
            gcs_path = host.get("gcs_path")
            
            if not gcs_path:
                logger.warning("[speaker_id] Host '%s' missing gcs_path, skipping", host_name)
                continue
            
            try:
                # Download from GCS to temp file
                local_path = _download_speaker_intro(gcs_path, f"host_{idx}_{host_name}")
                intro_audio = AudioSegment.from_file(local_path)
                
                segments.append(intro_audio)
                total_intro_duration_ms += len(intro_audio)
                
                # Add gap after intro (except after last segment)
                segments.append(AudioSegment.silent(duration=gap_duration_ms))
                total_intro_duration_ms += gap_duration_ms
                
                logger.info(
                    "[speaker_id] Added host intro: %s (%.2fs)",
                    host_name,
                    len(intro_audio) / 1000.0
                )
            except Exception as e:
                logger.error("[speaker_id] Failed to load host intro for '%s': %s", host_name, e)
                raise
    
    # Add guest intros (in order)
    if has_guest_intros:
        for idx, guest in enumerate(episode_guest_intros):
            guest_name = guest.get("name", f"Guest {idx + 1}")
            gcs_path = guest.get("gcs_path")
            
            if not gcs_path:
                logger.warning("[speaker_id] Guest '%s' missing gcs_path, skipping", guest_name)
                continue
            
            try:
                # Download from GCS to temp file
                local_path = _download_speaker_intro(gcs_path, f"guest_{idx}_{guest_name}")
                intro_audio = AudioSegment.from_file(local_path)
                
                segments.append(intro_audio)
                total_intro_duration_ms += len(intro_audio)
                
                # Add gap after intro
                segments.append(AudioSegment.silent(duration=gap_duration_ms))
                total_intro_duration_ms += gap_duration_ms
                
                logger.info(
                    "[speaker_id] Added guest intro: %s (%.2fs)",
                    guest_name,
                    len(intro_audio) / 1000.0
                )
            except Exception as e:
                logger.error("[speaker_id] Failed to load guest intro for '%s': %s", guest_name, e)
                raise
    
    # Add main content
    main_audio = AudioSegment.from_file(main_audio_path)
    segments.append(main_audio)
    
    logger.info("[speaker_id] Main content duration: %.2fs", len(main_audio) / 1000.0)
    
    # Combine all segments
    if not segments:
        raise ValueError("No audio segments to combine")
    
    combined: AudioSegment = segments[0]
    for seg in segments[1:]:
        combined = combined + seg
    
    # Determine output path
    if output_path is None:
        output_path = main_audio_path.parent / f"{main_audio_path.stem}_with_speaker_intros.wav"
    
    # Export combined audio
    combined.export(output_path, format="wav")
    
    total_intro_duration_s = total_intro_duration_ms / 1000.0
    logger.info(
        "[speaker_id] Created audio with speaker intros: %s (total intro duration: %.2fs)",
        output_path.name,
        total_intro_duration_s
    )
    
    return output_path, total_intro_duration_s


def _download_speaker_intro(gcs_path: str, label: str) -> Path:
    """
    Download a speaker intro file from GCS to a temp location.
    
    Args:
        gcs_path: GCS path (gs://bucket/path/to/file.wav)
        label: Label for temp filename (e.g., "host_0_Scott")
    
    Returns:
        Path to downloaded local file
    """
    from api.core.paths import LOCAL_TMP_DIR
    
    try:
        from google.cloud import storage  # type: ignore
    except ImportError as e:
        raise RuntimeError("google-cloud-storage not installed") from e
    
    # Extract filename from GCS path
    filename = Path(gcs_path).name
    local_path = LOCAL_TMP_DIR / f"speaker_intro_{label}_{filename}"
    
    logger.debug("[speaker_id] Downloading %s to %s", gcs_path, local_path)
    
    # Download from GCS
    if not gcs_path.startswith("gs://"):
        raise ValueError(f"Invalid GCS path (must start with gs://): {gcs_path}")
    
    without_scheme = gcs_path[len("gs://"):]
    bucket_name, key = without_scheme.split("/", 1)
    
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(key)
    blob.download_to_filename(str(local_path))
    
    if not local_path.exists():
        raise FileNotFoundError(f"Failed to download speaker intro from {gcs_path}")
    
    return local_path


def get_speaker_order(
    podcast_speaker_intros: Optional[Dict[str, Any]],
    episode_guest_intros: Optional[List[Dict[str, Any]]]
) -> List[str]:
    """
    Get ordered list of speaker names based on intro order.
    
    This matches the order speakers will be assigned by AssemblyAI diarization
    (Speaker A, Speaker B, Speaker C, etc.)
    
    Args:
        podcast_speaker_intros: Podcast-level host configuration
        episode_guest_intros: Episode-level guest configuration
    
    Returns:
        Ordered list of speaker names (e.g., ["Scott", "Amber", "Sarah", "Mike"])
    """
    speaker_names = []
    
    # Add hosts in order
    if podcast_speaker_intros and podcast_speaker_intros.get("hosts"):
        for host in podcast_speaker_intros["hosts"]:
            name = host.get("name")
            if name:
                speaker_names.append(name)
    
    # Add guests in order
    if episode_guest_intros:
        for guest in episode_guest_intros:
            name = guest.get("name")
            if name:
                speaker_names.append(name)
    
    return speaker_names
