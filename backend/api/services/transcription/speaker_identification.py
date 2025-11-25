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
from uuid import UUID
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


def map_speaker_labels(
    words: List[Dict],
    podcast_id: UUID,
    episode_id: UUID,
    speaker_intros: Optional[Dict[str, Any]] = None,
    guest_intros: Optional[List[Dict[str, Any]]] = None,
    intro_duration_s: Optional[float] = None,
) -> List[Dict]:
    """Map generic speaker labels to real names based on speaker order.
    
    If intro_duration_s is provided, it will first strip that many seconds
    from the beginning of the transcript (removing words within the intro)
    and shift all subsequent timestamps back by that amount.
    
    SIMPLIFIED APPROACH (Phase 1):
    - Maps "Speaker A" to first speaker in speaker_intros (usually host)
    - Maps "Speaker B" to second speaker (co-host or first guest)
    - Maps "Speaker C+" to remaining guests
    
    This assumes:
    - Host speaks first (reasonable assumption for most podcasts)
    - Speaker order in config matches speaking order
    
    PHASE 2 (Prepended Intros):
    - If intro_duration_s > 0, we assume intros were prepended to the audio
    - We strip the intros from the transcript results
    - We shift timestamps back to 0.0
    
    Args:
        words: List of word dicts with {word, start, end, speaker}
        podcast_id: UUID of podcast (for logging)
        episode_id: UUID of episode (for logging)
        speaker_intros: Dict with podcast-level host configuration
        guest_intros: List of episode-level guest configuration
        intro_duration_s: Duration of prepended intros in seconds (if any)
    
    Returns:
        Modified words list with speaker labels mapped to real names
    """
    if not words:
        return words

    # --- PHASE 2: Strip Intro Section (if applicable) ---
    if intro_duration_s and intro_duration_s > 0:
        logger.info(
            "[speaker_id] Stripping intro section (duration: %.2fs) from transcript (podcast=%s, episode=%s)",
            intro_duration_s,
            podcast_id,
            episode_id
        )
        
        filtered_words = []
        removed_count = 0
        
        for w in words:
            start = float(w.get("start") or 0.0)
            end = float(w.get("end") or 0.0)
            
            # Skip words in intro section
            if start < intro_duration_s:
                removed_count += 1
                continue
            
            # Adjust timestamps (subtract intro duration)
            w["start"] = max(0.0, start - intro_duration_s)
            w["end"] = max(0.0, end - intro_duration_s)
            
            filtered_words.append(w)
            
        logger.info(
            "[speaker_id] Removed %d intro words, kept %d content words",
            removed_count,
            len(filtered_words)
        )
        
        # Replace words list with filtered version
        words = filtered_words

    # Build ordered list of speaker names (hosts first, then guests)
    speaker_order = get_speaker_order(speaker_intros or {}, guest_intros or [])
    
    if not speaker_order:
        logger.info(
            "[speaker_id] No speaker configuration, keeping generic labels (podcast=%s, episode=%s)",
            podcast_id,
            episode_id
        )
        return words
    
    logger.info(
        "[speaker_id] Speaker order: %s (podcast=%s, episode=%s)",
        speaker_order,
        podcast_id,
        episode_id
    )
    
    # Map generic labels to real names
    # "Speaker A" → speaker_order[0]
    # "Speaker B" → speaker_order[1]
    # "Speaker C" → speaker_order[2], etc.
    label_map = {}
    for idx, name in enumerate(speaker_order):
        generic_label = f"Speaker {chr(65 + idx)}"  # A, B, C, ...
        label_map[generic_label] = name
    
    # Apply mapping to all words
    mapped_count = 0
    for word in words:
        if "speaker" in word and word["speaker"]:
            generic_label = word["speaker"]
            if generic_label in label_map:
                word["speaker"] = label_map[generic_label]
                mapped_count += 1
    
    logger.info(
        "[speaker_id] Mapped %d words to real names (podcast=%s, episode=%s)",
        mapped_count,
        podcast_id,
        episode_id
    )
    
    return words
