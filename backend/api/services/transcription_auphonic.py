"""Auphonic transcription service for Pro tier users.

Handles transcription + audio processing via Auphonic API:
- Uploads audio to Auphonic
- Processes with denoise, leveling, EQ, filler removal, silence removal
- Downloads cleaned audio + transcript
- Saves both original and cleaned audio to GCS
- Returns transcript in AssemblyAI-compatible format
"""

from __future__ import annotations

import json
import logging
import os  # Import os for getenv
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from api.core.config import settings
from api.core.paths import MEDIA_DIR  # Import MEDIA_DIR for local file resolution
from infrastructure import gcs  # Direct import (not through api.infrastructure alias)
from api.services.auphonic_client import AuphonicClient, AuphonicError

log = logging.getLogger(__name__)


class AuphonicTranscriptionError(Exception):
    """Exception raised when Auphonic transcription fails."""
    pass


def _download_from_gcs(gcs_url: str) -> Path:
    """Download file from GCS to temp location.
    
    Args:
        gcs_url: GCS URL (gs://bucket/path/to/file)
        
    Returns:
        Path to downloaded temp file
    """
    try:
        # Parse GCS URL
        if not gcs_url.startswith("gs://"):
            raise ValueError(f"Invalid GCS URL: {gcs_url}")
        
        parts = gcs_url[5:].split("/", 1)  # Remove 'gs://'
        bucket_name = parts[0]
        key = parts[1] if len(parts) > 1 else ""
        
        # Download to temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=Path(key).suffix)
        temp_path = Path(temp_file.name)
        temp_file.close()
        
        log.info("[auphonic_transcribe] downloading gcs_url=%s to temp=%s", gcs_url, temp_path)
        
        file_bytes = gcs.download_bytes(bucket_name, key)
        if file_bytes is None:
            raise AuphonicTranscriptionError(
                f"Failed to download from GCS: file not found or download returned None for gs://{bucket_name}/{key}"
            )
        temp_path.write_bytes(file_bytes)
        
        return temp_path
    
    except Exception as e:
        log.error("[auphonic_transcribe] gcs_download_failed url=%s error=%s", gcs_url, str(e))
        raise AuphonicTranscriptionError(f"Failed to download from GCS: {e}") from e


def _upload_to_gcs(local_path: Path, user_id: str, category: str, filename: str) -> str:
    """Upload file to GCS.
    
    Args:
        local_path: Local file path
        user_id: User UUID
        category: Media category (e.g., 'main_content')
        filename: Target filename
        
    Returns:
        GCS URL (gs://bucket/path)
    """
    try:
        bucket_name = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
        key = f"{user_id}/{category}/{filename}"
        
        log.info("[auphonic_transcribe] uploading local=%s to gcs=%s", local_path, key)
        
        with open(local_path, "rb") as f:
            file_bytes = f.read()
        
        gcs.upload_bytes(bucket_name, key, file_bytes)
        
        gcs_url = f"gs://{bucket_name}/{key}"
        log.info("[auphonic_transcribe] uploaded size=%d url=%s", len(file_bytes), gcs_url)
        
        return gcs_url
    
    except Exception as e:
        log.error("[auphonic_transcribe] gcs_upload_failed path=%s error=%s", local_path, str(e))
        raise AuphonicTranscriptionError(f"Failed to upload to GCS: {e}") from e


def _parse_auphonic_transcript(transcript_data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Parse Auphonic transcript JSON to extract words, summary, tags, and chapters.
    
    Auphonic Whisper ASR Full Response (dict format with metadata):
    {
        "segments": [...],  # Word-level timestamps
        "summary": "Brief 1-2 paragraph summary",
        "summary_long": "Detailed multi-paragraph summary",
        "tags": ["keyword1", "keyword2"],
        "chapters": [{"title": "Chapter 1", "start": 0.0, "end": 120.5}, ...]
    }
    
    Or simplified segments-only format (list):
    [{"start": 0.0, "end": 5.0, "text": "...", "timestamps": [...], "speaker": "Speaker0"}, ...]
    
    Output format:
    {
        "words": [
            {"word": "Hello", "start": 0.0, "end": 0.5, "speaker": "A", "confidence": 0.95}
        ],
        "metadata": {
            "brief_summary": "...",
            "long_summary": "...",
            "tags": [...],
            "chapters": [...]
        }
    }
    
    Args:
        transcript_data: Auphonic transcript JSON (dict or list)
        
    Returns:
        Dict with "words" (AssemblyAI-compatible list) and "metadata" (summary/tags/chapters)
    """
    words = []
    
    try:
        # DEBUG: Log the transcript structure
        if isinstance(transcript_data, list):
            log.info("[auphonic_transcribe] 🔍 transcript_data is LIST with %d items", len(transcript_data))
            if len(transcript_data) > 0:
                log.info("[auphonic_transcribe] 🔍 First item type=%s keys=%s", 
                         type(transcript_data[0]).__name__, 
                         list(transcript_data[0].keys()) if isinstance(transcript_data[0], dict) else "N/A")
        elif isinstance(transcript_data, dict):
            log.info("[auphonic_transcribe] 🔍 transcript_data is DICT with keys=%s", list(transcript_data.keys()))
        else:
            log.warning("[auphonic_transcribe] 🔍 transcript_data is unexpected type=%s", type(transcript_data).__name__)
        
        # Initialize metadata dictionary for summary, tags, chapters
        metadata = {
            "brief_summary": None,
            "long_summary": None,
            "tags": [],
            "chapters": [],
        }
        
        # Handle different possible Auphonic transcript structures
        # (May need adjustment based on actual Auphonic API response)
        
        # If transcript_data is a dict with segments/summary/tags/chapters (full Auphonic Whisper ASR response)
        if isinstance(transcript_data, dict):
            # Extract metadata from root level (Auphonic provides these in full JSON response)
            metadata["brief_summary"] = transcript_data.get("summary")
            metadata["long_summary"] = transcript_data.get("summary_long")
            metadata["tags"] = transcript_data.get("tags", [])
            metadata["chapters"] = transcript_data.get("chapters", [])
            
            # Process segments array (same logic as list format below)
            segments = transcript_data.get("segments", transcript_data.get("data", []))
            for segment in segments:
                speaker = segment.get("speaker", "Speaker0")
                speaker_num = 0
                if speaker.startswith("Speaker"):
                    try:
                        speaker_num = int(speaker[7:])
                    except (ValueError, IndexError):
                        pass
                speaker_letter = chr(65 + speaker_num)
                
                for word_tuple in segment.get("timestamps", []):
                    if len(word_tuple) >= 4:
                        word_text, start, end, confidence = word_tuple[:4]
                        words.append({
                            "word": word_text,
                            "start": float(start),
                            "end": float(end),
                            "speaker": speaker_letter,
                            "confidence": float(confidence),
                        })
        
        # If transcript_data is a list (Auphonic Whisper ASR format - segments only)
        elif isinstance(transcript_data, list):
            for segment in transcript_data:
                # Extract speaker label (e.g., "Speaker0", "Speaker1", "Speaker2")
                speaker = segment.get("speaker", "Speaker0")
                
                # Convert Auphonic speaker format to letter format
                # "Speaker0" → "A", "Speaker1" → "B", "Speaker2" → "C", etc.
                speaker_num = 0
                if speaker.startswith("Speaker"):
                    try:
                        speaker_num = int(speaker[7:])  # Extract number after "Speaker"
                    except (ValueError, IndexError):
                        pass
                speaker_letter = chr(65 + speaker_num)  # 65 is ASCII for 'A', so 0→A, 1→B, 2→C
                
                # Extract words from timestamps array
                # Auphonic Whisper ASR format: [["word_text", start_time, end_time, confidence], ...]
                for word_tuple in segment.get("timestamps", []):
                    if len(word_tuple) >= 4:
                        word_text, start, end, confidence = word_tuple[:4]
                        words.append({
                            "word": word_text,
                            "start": float(start),
                            "end": float(end),
                            "speaker": speaker_letter,
                            "confidence": float(confidence),
                        })
        
        # Legacy format handling (keep for backward compatibility)
        if not words and isinstance(transcript_data, dict) and "segments" in transcript_data:
            # Segmented format with speakers
            for segment in transcript_data.get("segments", []):
                speaker = segment.get("speaker", "SPEAKER_00")
                # Convert speaker ID to single letter (A, B, C, etc.)
                speaker_letter = chr(65 + int(speaker.split("_")[-1]) % 26)
                
                for word_obj in segment.get("words", []):
                    words.append({
                        "word": word_obj.get("word", ""),
                        "start": float(word_obj.get("start", 0.0)),
                        "end": float(word_obj.get("end", 0.0)),
                        "speaker": speaker_letter,
                        "confidence": float(word_obj.get("confidence", 1.0)),
                    })
        
        elif "words" in transcript_data:
            # Flat word list
            for word_obj in transcript_data.get("words", []):
                words.append({
                    "word": word_obj.get("word", ""),
                    "start": float(word_obj.get("start", 0.0)),
                    "end": float(word_obj.get("end", 0.0)),
                    "speaker": word_obj.get("speaker", "A"),
                    "confidence": float(word_obj.get("confidence", 1.0)),
                })
        
        elif "results" in transcript_data:
            # Alternative format with results array
            for result in transcript_data.get("results", []):
                for word_obj in result.get("words", []):
                    words.append({
                        "word": word_obj.get("word", ""),
                        "start": float(word_obj.get("start", 0.0)),
                        "end": float(word_obj.get("end", 0.0)),
                        "speaker": word_obj.get("speaker", "A"),
                        "confidence": float(word_obj.get("confidence", 1.0)),
                    })
        
        else:
            # Unknown format
            if isinstance(transcript_data, dict):
                log.warning("[auphonic_transcribe] unknown transcript format, keys=%s", list(transcript_data.keys()))
            else:
                log.warning("[auphonic_transcribe] unknown transcript format, type=%s", type(transcript_data).__name__)
        
        log.info(
            "[auphonic_transcribe] ✅ parsed transcript: words=%d, brief_summary=%s, long_summary=%s, tags=%d, chapters=%d",
            len(words),
            "yes" if metadata.get("brief_summary") else "no",
            "yes" if metadata.get("long_summary") else "no",
            len(metadata.get("tags", [])),
            len(metadata.get("chapters", [])),
        )
        
        return {
            "words": words,
            "metadata": metadata,
        }
    
    except Exception as e:
        log.error("[auphonic_transcribe] transcript_parse_failed error=%s", str(e))
        raise AuphonicTranscriptionError(f"Failed to parse transcript: {e}") from e


def auphonic_transcribe_and_process(
    audio_path: str,
    user_id: str,
) -> Dict[str, Any]:
    """Upload audio to Auphonic, process, download results.
    
    This is the main entry point for Pro tier transcription. It:
    1. Downloads audio from GCS (if needed)
    2. Uploads to Auphonic
    3. Creates production with all processing enabled:
       - Denoise (noise reduction)
       - Leveler (speaker balancing)
       - AutoEQ (frequency optimization)
       - Crossgate (filler word removal)
       - Silence removal
       - Transcription with word-level timestamps
       - Show notes generation (if available)
    4. Polls until complete
    5. Downloads cleaned audio + transcript
    6. Uploads cleaned audio to GCS (keeps original for failure diagnosis)
    7. Returns transcript in AssemblyAI-compatible format
    
    Args:
        audio_path: GCS URL or local path to audio file
        user_id: User UUID string
        
    Returns:
        {
            "transcript": [...],  # List of word dicts with start/end/word/speaker
            "cleaned_audio_url": "gs://bucket/path/to/cleaned.mp3",
            "original_audio_url": "gs://bucket/path/to/original.mp3",
            "show_notes": "...",  # AI-generated show notes (or None)
            "chapters": [...],    # Chapter markers (or None)
            "auphonic_output_file": "gs://bucket/path/to/outputs.txt"  # If single file
        }
    
    Raises:
        AuphonicTranscriptionError: If processing fails
    """
    temp_files: List[Path] = []
    
    try:
        # Step 1: Get local file
        if audio_path.startswith("gs://"):
            log.info("[auphonic_transcribe] downloading from GCS user_id=%s", user_id)
            local_audio_path = _download_from_gcs(audio_path)
            temp_files.append(local_audio_path)
            original_gcs_url = audio_path
        else:
            # Resolve filename to full path in MEDIA_DIR
            local_audio_path = Path(audio_path)
            if not local_audio_path.is_absolute():
                local_audio_path = MEDIA_DIR / audio_path
            
            log.info("[auphonic_transcribe] checking local file=%s", local_audio_path)
            if not local_audio_path.exists():
                raise AuphonicTranscriptionError(f"Audio file not found: {audio_path} (resolved to {local_audio_path})")
            
            # Upload original to GCS for backup
            original_filename = f"{local_audio_path.stem}_original{local_audio_path.suffix}"
            original_gcs_url = _upload_to_gcs(local_audio_path, user_id, "main_content", original_filename)
        
        # Step 2: Initialize Auphonic client
        client = AuphonicClient()
        
        # Step 2.5: Check account info to see what features are available
        try:
            account_info = client.get_info()
            log.info("[auphonic_transcribe] 🔍 Auphonic account info:")
            log.info("[auphonic_transcribe] 🔍   credits_remaining: %s", account_info.get("credits_remaining"))
            log.info("[auphonic_transcribe] 🔍   credits_recurring: %s", account_info.get("credits_recurring"))
            log.info("[auphonic_transcribe] 🔍   algorithms_available: %s", list(account_info.get("algorithms", {}).keys()))
            log.info("[auphonic_transcribe] 🔍   speech_recognition available: %s", "speech_recognition" in account_info.get("algorithms", {}))
        except Exception as e:
            log.warning("[auphonic_transcribe] Could not fetch account info: %s", e)
        
        # Step 3: Create production using the PlusPlus preset
        # Preset UUID can be overridden with AUPHONIC_PRESET_UUID env var
        # Default: TMpreMMux5mgjzRGq9shq3 (configured with Whisper ASR + all audio processing)
        # Preset includes:
        # - Audio: MP3 @ 112kbps, Subtitle (VTT), Transcript (HTML), Speech Data (JSON)
        # - Auphonic Whisper ASR with auto language detection & speaker diarization
        # - Automatic Shownotes and Chapters
        # - Audio processing: Leveler, Voice AutoEQ, Loudness -16 LUFS, Noise/Reverb/Breathing reduction, Auto-cutting (silence/fillers/coughs)
        
        preset_uuid = os.getenv("AUPHONIC_PRESET_UUID", "TMpreMMux5mgjzRGq9shq3")
        
        log.info("[auphonic_transcribe] creating_production user_id=%s preset=%s", user_id, preset_uuid)
        production = client.create_production(
            preset=preset_uuid,
            title=f"Episode for user {user_id}",
        )
        
        production_uuid = production.get("uuid")
        if not production_uuid:
            raise AuphonicTranscriptionError("No production UUID returned from Auphonic")
        
        log.info("[auphonic_transcribe] production_created uuid=%s user_id=%s", production_uuid, user_id)
        
        # Step 4: Upload file to the production
        log.info("[auphonic_transcribe] uploading to Auphonic uuid=%s file=%s", production_uuid, local_audio_path.name)
        client.upload_file(production_uuid, local_audio_path)
        
        # Step 5: Start processing
        client.start_production(production_uuid)
        
        # Step 6: Poll until done (30 min timeout)
        log.info("[auphonic_transcribe] polling_start uuid=%s", production_uuid)
        production = client.poll_until_done(production_uuid, max_wait_seconds=1800)
        
        # Debug: Log the FULL production response to understand what Auphonic returned
        log.info("[auphonic_transcribe] 🔍 FULL PRODUCTION RESPONSE:")
        log.info("[auphonic_transcribe] 🔍   status: %s", production.get("status"))
        log.info("[auphonic_transcribe] 🔍   error_status: %s", production.get("error_status"))
        log.info("[auphonic_transcribe] 🔍   error_message: %s", production.get("error_message"))
        log.info("[auphonic_transcribe] 🔍   algorithms applied: %s", production.get("algorithms", {}))
        
        output_files = production.get("output_files", [])
        log.info("[auphonic_transcribe] 🔍 DEBUG: got %d output_files (requested 2: mp3 + speech/json)", len(output_files))
        for i, of in enumerate(output_files):
            log.info("[auphonic_transcribe] 🔍 DEBUG: output_file[%d] FULL: %r", i, of)
        
        # Log what we REQUESTED vs what we GOT
        log.info("[auphonic_transcribe] 🔍 REQUESTED output_files: [{'format': 'mp3', 'bitrate': '192'}, {'format': 'speech', 'ending': 'json'}]")
        log.info("[auphonic_transcribe] 🔍 GOT %d files. Missing transcript = Speech recognition NOT ENABLED or NOT AVAILABLE in Auphonic account", len(output_files))
        
        # Step 7: Download outputs
        output_audio_path = None
        transcript_path = None
        
        temp_output_dir = Path(tempfile.mkdtemp())
        temp_files.append(temp_output_dir)
        
        for output_file in output_files:
            file_ending = output_file.get("ending", "")
            file_type = output_file.get("type", "")
            
            if file_ending == "mp3":
                output_audio_path = temp_output_dir / f"{local_audio_path.stem}_auphonic_cleaned.mp3"
                client.download_output(output_file, output_audio_path)
                temp_files.append(output_audio_path)
            
            elif file_ending == "json":
                # Auphonic may return type=None or type="transcript" - accept either
                transcript_path = temp_output_dir / f"{local_audio_path.stem}_auphonic_transcript.json"
                client.download_output(output_file, transcript_path)
                temp_files.append(transcript_path)
        
        if not output_audio_path:
            raise AuphonicTranscriptionError("No audio output file found in Auphonic response")
        
        if not transcript_path:
            # CRITICAL: We requested transcript but didn't get it - need to understand why
            raise AuphonicTranscriptionError(
                f"No transcript file found in Auphonic response. Got {len(output_files)} output files. "
                f"Speech recognition may not be enabled/available in Auphonic account. "
                f"Check production logs above for full response details. "
                f"If speech recognition costs extra, we need to decide if Auphonic is worth it without transcription."
            )
        
        # Step 8: Upload cleaned audio to GCS
        cleaned_filename = f"{local_audio_path.stem}_auphonic_cleaned.mp3"
        cleaned_gcs_url = _upload_to_gcs(output_audio_path, user_id, "main_content", cleaned_filename)
        
        # Step 9: Parse transcript and extract metadata
        transcript_data = json.loads(transcript_path.read_text())
        parsed_result = _parse_auphonic_transcript(transcript_data)
        
        # Extract words and metadata from parsed result
        transcript_words = parsed_result.get("words", [])
        transcript_metadata = parsed_result.get("metadata", {})
        
        # Step 10: Save transcript to GCS (for episode assembly)
        transcript_filename = f"{local_audio_path.stem}.json"
        transcript_gcs_key = f"transcripts/{user_id}/{transcript_filename}"
        gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
        transcript_gcs_url = f"gs://{gcs_bucket}/{transcript_gcs_key}"
        
        transcript_json = json.dumps(transcript_words, indent=2)
        gcs.upload_bytes(gcs_bucket, transcript_gcs_key, transcript_json.encode())
        
        log.info(
            "[auphonic_transcribe] ✅ complete: user_id=%s uuid=%s words=%d brief_summary=%s tags=%d chapters=%d cleaned=%s",
            user_id,
            production_uuid,
            len(transcript_words),
            "yes" if transcript_metadata.get("brief_summary") else "no",
            len(transcript_metadata.get("tags", [])),
            len(transcript_metadata.get("chapters", [])),
            cleaned_gcs_url,
        )
        
        return {
            "transcript": transcript_words,
            "cleaned_audio_url": cleaned_gcs_url,
            "original_audio_url": original_gcs_url,
            "brief_summary": transcript_metadata.get("brief_summary"),
            "long_summary": transcript_metadata.get("long_summary"),
            "tags": transcript_metadata.get("tags", []),
            "chapters": transcript_metadata.get("chapters", []),
            "auphonic_output_file": None,  # Single file output not used in this implementation
            "production_uuid": production_uuid,
            "duration_ms": production.get("length_timestring_ms"),
        }
    
    except AuphonicError as e:
        log.error("[auphonic_transcribe] auphonic_error user_id=%s error=%s", user_id, str(e))
        raise AuphonicTranscriptionError(f"Auphonic API error: {e}") from e
    
    except Exception as e:
        log.error("[auphonic_transcribe] unexpected_error user_id=%s error=%s", user_id, str(e))
        raise AuphonicTranscriptionError(f"Unexpected error: {e}") from e
    
    finally:
        # Cleanup temp files
        for temp_path in temp_files:
            try:
                if temp_path.is_file():
                    temp_path.unlink()
                elif temp_path.is_dir():
                    import shutil
                    shutil.rmtree(temp_path)
            except Exception:
                pass


__all__ = [
    "auphonic_transcribe_and_process",
    "AuphonicTranscriptionError",
]
