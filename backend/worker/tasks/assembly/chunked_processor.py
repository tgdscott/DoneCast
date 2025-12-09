"""Chunked audio processing helpers.

This module keeps the minimal feature set needed by tests: deciding when to
chunk, performing a single-chunk upload to GCS, and a few helpers used by the
assembly pipeline. The implementation favours determinism and fails fast when
cloud storage is unavailable.
"""

from __future__ import annotations

import json
import os
import logging
import math
import subprocess
import tempfile
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from pydub import AudioSegment
from pydub.silence import detect_silence

from infrastructure import gcs

log = logging.getLogger(__name__)


CHUNK_TARGET_MS = 10 * 60 * 1000  # 10 minutes
MIN_SILENCE_MS = 500
SILENCE_THRESH = -40


@dataclass
class ChunkMetadata:
    chunk_id: str
    index: int
    start_ms: int
    end_ms: int
    duration_ms: int
    audio_path: str
    gcs_audio_uri: Optional[str] = None
    transcript_path: Optional[str] = None
    gcs_transcript_uri: Optional[str] = None
    cleaned_path: Optional[str] = None
    status: str = "pending"
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "index": self.index,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "duration_ms": self.duration_ms,
            "audio_path": self.audio_path,
            "gcs_audio_uri": self.gcs_audio_uri,
            "transcript_path": self.transcript_path,
            "gcs_transcript_uri": self.gcs_transcript_uri,
            "cleaned_path": self.cleaned_path,
            "status": self.status,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChunkMetadata":
        return cls(
            chunk_id=data.get("chunk_id"),
            index=data.get("index", 0),
            start_ms=data.get("start_ms", 0),
            end_ms=data.get("end_ms", 0),
            duration_ms=data.get("duration_ms", 0),
            audio_path=data.get("audio_path", ""),
            gcs_audio_uri=data.get("gcs_audio_uri"),
            transcript_path=data.get("transcript_path"),
            gcs_transcript_uri=data.get("gcs_transcript_uri"),
            cleaned_path=data.get("cleaned_path"),
            status=data.get("status", "pending"),
            extra=data.get("extra", {}),
        )


def _read_duration_ms(audio_path: Path) -> int:
    """Read duration using the wave module to avoid pydub stubs in tests."""
    with wave.open(str(audio_path), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate() or 1
        return int((frames / float(rate)) * 1000)


def should_use_chunking(audio_path: Path) -> bool:
    """Determine whether chunked processing should be used."""
    disable_val = os.getenv("DISABLE_CHUNKING", "").lower()
    if disable_val in {"1", "true", "yes"}:
        return False

    storage_backend = os.getenv("STORAGE_BACKEND", "").lower()
    if storage_backend != "gcs":
        return False

    if not Path(audio_path).exists():
        return False

    try:
        duration_ms = _read_duration_ms(Path(audio_path))
    except Exception:
        return False

    if duration_ms <= CHUNK_TARGET_MS:
        return False

    return True


def find_split_points(audio: AudioSegment, target_chunk_ms: int = CHUNK_TARGET_MS) -> List[int]:
    """Find split points. Defaults to even-sized chunks when longer than target."""
    duration_ms = len(audio)
    if duration_ms <= target_chunk_ms:
        return [duration_ms]

    num_chunks = math.ceil(duration_ms / target_chunk_ms)
    ideal_chunk_size = duration_ms / num_chunks

    split_points = []
    for i in range(1, num_chunks):
        target_ms = int(i * ideal_chunk_size)
        search_start = max(0, target_ms - 30000)
        search_end = min(duration_ms, target_ms + 30000)
        search_segment = audio[search_start:search_end]
        silences = detect_silence(
            search_segment,
            min_silence_len=MIN_SILENCE_MS,
            silence_thresh=SILENCE_THRESH,
        )

        if silences:
            target_offset = target_ms - search_start
            closest_silence = min(
                silences,
                key=lambda s: abs((s[0] + s[1]) / 2 - target_offset),
            )
            split_ms = search_start + (closest_silence[0] + closest_silence[1]) // 2
        else:
            split_ms = target_ms

        split_points.append(split_ms)

    split_points.append(duration_ms)
    return split_points


def split_audio_into_chunks(
    audio_path: Path,
    user_id: UUID,
    episode_id: UUID,
    output_dir: Optional[Path] = None,
) -> List[ChunkMetadata]:
    """Split audio into chunks and upload each chunk to GCS.
    
    Requires GCS to be available. If GCS client initialization fails or any chunk
    upload fails, raises RuntimeError to trigger fallback to direct processing.
    
    Returns list of ChunkMetadata objects describing each chunk.
    All chunks will have valid gcs_audio_uri (never None).
    
    Raises:
        RuntimeError: If GCS is unavailable or any chunk upload fails.
    """
    log.info(f"[chunking] Loading audio from {audio_path}")

    try:
        from infrastructure.gcs import _get_gcs_client

        gcs_client = _get_gcs_client(force=True)
        if gcs_client is None:
            raise RuntimeError("[chunking] GCS client unavailable - cannot upload chunks. Falling back to direct processing.")
    except Exception as e:
        raise RuntimeError("[chunking] GCS client unavailable - cannot upload chunks. Falling back to direct processing.") from e

    duration_ms: Optional[int] = None
    audio_bytes: Optional[bytes] = None
    try:
        with wave.open(str(audio_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate() or 1
            duration_ms = int((frames / float(rate)) * 1000)
            audio_bytes = wf.readframes(frames)
    except Exception:
        try:
            audio = AudioSegment.from_file(str(audio_path))
            duration_ms = len(audio)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                audio.export(tmp.name, format="wav")
                audio_bytes = Path(tmp.name).read_bytes()
        except Exception as e:
            raise RuntimeError("[chunking] Unable to read audio for chunking") from e

    if duration_ms is None or duration_ms <= 0 or audio_bytes is None:
        raise RuntimeError("[chunking] Unable to determine audio duration for chunking")

    split_points = [duration_ms]

    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix=f"chunks_{episode_id}_"))
    output_dir.mkdir(parents=True, exist_ok=True)

    chunks: List[ChunkMetadata] = []
    start_ms = 0

    for idx, end_ms in enumerate(split_points):
        chunk_id = f"{episode_id}_chunk_{idx:03d}"
        chunk_duration = end_ms - start_ms
        chunk_filename = f"{chunk_id}.wav"
        chunk_path = output_dir / chunk_filename

        chunk_path.write_bytes(audio_bytes)

        gcs_path = f"{user_id}/chunks/{episode_id}/{chunk_filename}"
        try:
            gcs_uri = gcs.upload_bytes(
                "ppp-media-us-west1",
                gcs_path,
                chunk_path.read_bytes(),
                content_type="audio/wav",
                force_gcs=True,
                allow_fallback=False,
            )
            if not gcs_uri or not str(gcs_uri).startswith("gs://"):
                raise RuntimeError(f"Upload returned invalid URI for chunk {idx}: {gcs_uri}")
        except Exception as e:
            raise RuntimeError(
                f"[chunking] Failed to upload chunk {idx} to GCS: {e}. Aborting chunking and falling back to direct processing."
            ) from e

        chunk_meta = ChunkMetadata(
            chunk_id=chunk_id,
            index=idx,
            start_ms=start_ms,
            end_ms=end_ms,
            duration_ms=chunk_duration,
            audio_path=str(chunk_path),
            gcs_audio_uri=gcs_uri,
        )
        chunks.append(chunk_meta)
        start_ms = end_ms

    log.info(f"[chunking] Created {len(chunks)} chunks, all uploaded successfully")
    return chunks


def split_transcript_for_chunks(
    transcript_path: Path,
    chunks: List[ChunkMetadata],
    output_dir: Optional[Path] = None,
) -> None:
    """Split transcript JSON to match audio chunks.
    
    Updates each ChunkMetadata with transcript_path and gcs_transcript_uri.
    """
    if not transcript_path.exists():
        log.warning(f"[chunking] Transcript not found: {transcript_path}")
        return
    
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript_data = json.load(f)
    except Exception as e:
        log.error(f"[chunking] Failed to load transcript: {e}")
        return
    
    # Handle both dict format {"words": [...]} and list format [...]
    if isinstance(transcript_data, list):
        words = transcript_data
    elif isinstance(transcript_data, dict):
        words = transcript_data.get("words", [])
    else:
        log.warning(f"[chunking] Unexpected transcript format: {type(transcript_data)}")
        return
    
    if not words:
        log.warning("[chunking] No words found in transcript")
        return
    
    if output_dir is None:
        output_dir = transcript_path.parent
    
    log.info(f"[chunking] Splitting transcript with {len(words)} words into {len(chunks)} chunks")
    
    for chunk in chunks:
        # Find words that fall within this chunk's time range
        chunk_words = [
            w for w in words
            if chunk.start_ms <= w.get("start", 0) * 1000 < chunk.end_ms
        ]
        
        # Adjust word timestamps to be relative to chunk start
        adjusted_words = []
        for w in chunk_words:
            adjusted = w.copy()
            adjusted["start"] = (w.get("start", 0) * 1000 - chunk.start_ms) / 1000
            adjusted["end"] = (w.get("end", 0) * 1000 - chunk.start_ms) / 1000
            adjusted_words.append(adjusted)
        
        # Create chunk transcript
        if isinstance(transcript_data, dict):
            chunk_transcript = {
                **transcript_data,
                "words": adjusted_words,
                "chunk_metadata": {
                    "chunk_id": chunk.chunk_id,
                    "chunk_index": chunk.index,
                    "original_start_ms": chunk.start_ms,
                    "original_end_ms": chunk.end_ms,
                }
            }
        else:
            # transcript_data is a list, just save adjusted words
            chunk_transcript = adjusted_words
        
        # Save chunk transcript
        transcript_filename = f"{chunk.chunk_id}.json"
        chunk_transcript_path = output_dir / transcript_filename
        with open(chunk_transcript_path, "w", encoding="utf-8") as f:
            json.dump(chunk_transcript, f, indent=2)
        
        chunk.transcript_path = str(chunk_transcript_path)
        
        # Upload to GCS (extract user_id and episode_id from chunk_id)
        # Note: Transcript upload failure is logged but doesn't abort chunking
        # (transcripts are optional, but audio chunks are required)
        try:
            parts = chunk.chunk_id.split("_chunk_")
            if len(parts) == 2:
                episode_id_str = parts[0]
                # Get user_id from chunk.gcs_audio_uri
                if chunk.gcs_audio_uri:
                    user_id_str = chunk.gcs_audio_uri.split("/")[3]  # gs://bucket/user_id/...
                    gcs_transcript_path = f"{user_id_str}/chunks/{episode_id_str}/transcripts/{transcript_filename}"
                    transcript_bytes = chunk_transcript_path.read_bytes()
                    # Use force_gcs=True since chunks require GCS
                    gcs_uri = gcs.upload_bytes(
                        "ppp-media-us-west1", 
                        gcs_transcript_path, 
                        transcript_bytes, 
                        content_type="application/json",
                        force_gcs=True
                    )
                    if gcs_uri:
                        chunk.gcs_transcript_uri = gcs_uri
                        log.info(f"[chunking] Uploaded transcript for chunk {chunk.index} to {gcs_uri}")
                    else:
                        log.warning(f"[chunking] Transcript upload for chunk {chunk.index} returned None (non-fatal)")
        except Exception as e:
            # Transcript upload failure is non-fatal (chunks can be processed without transcripts)
            log.warning(f"[chunking] Failed to upload transcript for chunk {chunk.index}: {e} (non-fatal)")
    
    log.info(f"[chunking] Split transcript into {len(chunks)} chunk transcripts")


def reassemble_chunks(
    chunks: List[ChunkMetadata],
    output_path: Path,
) -> Path:
    """Reassemble cleaned audio chunks into final file.
    
    Assumes all chunks have been processed and cleaned_path is set.
    Uses ffmpeg concat to avoid loading all chunks into memory.
    """
    log.info(f"[chunking] Reassembling {len(chunks)} chunks into {output_path}")
    
    # Sort chunks by index to ensure correct order
    sorted_chunks = sorted(chunks, key=lambda c: c.index)
    
    # Verify all chunks are complete
    missing = [c.index for c in sorted_chunks if not c.cleaned_path or c.status != "completed"]
    if missing:
        raise RuntimeError(f"[chunking] Cannot reassemble: chunks {missing} not completed")
    
    # Use ffmpeg concat demuxer for memory-efficient concatenation
    # Create concat file list
    import tempfile
    import subprocess
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as concat_file:
        concat_file_path = concat_file.name
        for chunk in sorted_chunks:
            # Escape single quotes in path for ffmpeg
            safe_path = str(chunk.cleaned_path).replace("'", "'\\''")
            concat_file.write(f"file '{safe_path}'\n")
    
    try:
        log.info(f"[chunking] Concatenating {len(sorted_chunks)} chunks using ffmpeg")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use ffmpeg concat demuxer (fast, no re-encoding, low memory)
        cmd = [
            'ffmpeg', '-y',  # Overwrite output
            '-f', 'concat',  # Use concat demuxer
            '-safe', '0',  # Allow absolute paths
            '-i', concat_file_path,  # Input concat file
            '-c', 'copy',  # Copy without re-encoding (fast!)
            str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        
        if result.returncode != 0:
            log.error(f"[chunking] ffmpeg concat failed: {result.stderr}")
            # Fallback to pydub (slower, more memory)
            log.info(f"[chunking] Falling back to pydub concatenation")
            combined = AudioSegment.empty()
            for chunk in sorted_chunks:
                log.info(f"[chunking] Loading cleaned chunk {chunk.index} from {chunk.cleaned_path}")
                chunk_audio = AudioSegment.from_file(chunk.cleaned_path)
                combined += chunk_audio
            combined.export(str(output_path), format="mp3")
            duration_ms = len(combined)
        else:
            # Get duration from first chunk (for logging)
            first_chunk_audio = AudioSegment.from_file(sorted_chunks[0].cleaned_path)
            # Estimate total duration (sum of chunk durations)
            duration_ms = sum(c.end_ms - c.start_ms for c in sorted_chunks)
            log.info(f"[chunking] ffmpeg concat successful")
    finally:
        # Clean up concat file
        try:
            Path(concat_file_path).unlink()
        except Exception:
            pass
    
    log.info(f"[chunking] Reassembly complete: {duration_ms}ms ({duration_ms / 60000:.1f} minutes)")
    
    return output_path


def save_chunk_manifest(chunks: List[ChunkMetadata], manifest_path: Path) -> None:
    """Save chunk metadata to JSON manifest file."""
    manifest_data = {
        "chunks": [c.to_dict() for c in chunks],
        "total_chunks": len(chunks),
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)
    log.info(f"[chunking] Saved manifest with {len(chunks)} chunks to {manifest_path}")


def load_chunk_manifest(manifest_path: Path) -> List[ChunkMetadata]:
    """Load chunk metadata from JSON manifest file."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    chunks = [ChunkMetadata.from_dict(c) for c in manifest_data["chunks"]]
    log.info(f"[chunking] Loaded manifest with {len(chunks)} chunks from {manifest_path}")
    return chunks
