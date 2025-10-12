"""GCS-first transcript storage.

This module provides transcript storage and retrieval using GCS as the source of truth,
eliminating dependency on ephemeral /tmp storage in Cloud Run containers.

Architecture:
- Transcripts are saved to GCS immediately after generation
- /tmp is only used for temporary processing (never as storage)
- GCS URLs are stored in Episode metadata or returned directly
- Multiple transcript types supported: original, working, final

Pattern:
1. Generate transcript (using transcription service)
2. Upload to GCS: gs://{bucket}/{user_id}/transcripts/{stem}.{type}.json
3. Store GCS URL in Episode.transcript_url or meta_json
4. Clean up any /tmp files
5. Return GCS URL for access

"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional
from uuid import UUID

from api.infrastructure.storage.gcs import GCSClient

logger = logging.getLogger(__name__)

# GCS bucket for media storage
GCS_BUCKET = "ppp-media-us-west1"

# Transcript types/suffixes
TRANSCRIPT_TYPES = ["original", "working", "final", "words"]


def save_transcript_to_gcs(
    user_id: UUID,
    stem: str,
    transcript_data: dict | list,
    transcript_type: str = "working",
    gcs_client: Optional[GCSClient] = None,
) -> str:
    """
    Save transcript to GCS and return the GCS URL.

    Args:
        user_id: User UUID who owns the transcript
        stem: Base filename stem (without extension)
        transcript_data: Transcript data (words array or dict)
        transcript_type: Type of transcript (original, working, final, words)
        gcs_client: Optional GCS client (creates one if not provided)

    Returns:
        GCS URL: gs://{bucket}/{user_id_hex}/transcripts/{stem}.{type}.json

    Example:
        >>> url = save_transcript_to_gcs(
        ...     user_id=UUID("..."),
        ...     stem="episode_193_raw",
        ...     transcript_data=[{"word": "hello", "start": 0.0, "end": 0.5}],
        ...     transcript_type="original"
        ... )
        >>> print(url)
        gs://ppp-media-us-west1/abc123.../transcripts/episode_193_raw.original.json
    """
    if gcs_client is None:
        gcs_client = GCSClient()

    # Generate GCS key with user_id prefix for isolation
    user_hex = user_id.hex
    gcs_key = f"{user_hex}/transcripts/{stem}.{transcript_type}.json"

    logger.info(
        f"[transcript_gcs] Saving transcript to GCS: {stem}.{transcript_type}.json"
    )

    try:
        # Serialize transcript data
        content = json.dumps(transcript_data, ensure_ascii=False, indent=2).encode(
            "utf-8"
        )

        # Upload to GCS
        gcs_client.upload_bytes(
            bucket_name=GCS_BUCKET,
            object_key=gcs_key,
            data=content,
            content_type="application/json",
        )

        # Generate GCS URL
        gcs_url = f"gs://{GCS_BUCKET}/{gcs_key}"

        logger.info(
            f"[transcript_gcs] Successfully saved transcript: {gcs_url} ({len(content)} bytes)"
        )

        return gcs_url

    except Exception as e:
        logger.error(
            f"[transcript_gcs] Failed to save transcript {stem}.{transcript_type}.json: {e}",
            exc_info=True,
        )
        raise


def load_transcript_from_gcs(
    user_id: UUID,
    stem: str,
    transcript_type: Optional[str] = None,
    gcs_client: Optional[GCSClient] = None,
) -> Optional[dict | list]:
    """
    Load transcript from GCS.

    Args:
        user_id: User UUID who owns the transcript
        stem: Base filename stem (without extension)
        transcript_type: Specific transcript type to load, or None to try all types
        gcs_client: Optional GCS client (creates one if not provided)

    Returns:
        Transcript data (words array or dict), or None if not found

    Example:
        >>> data = load_transcript_from_gcs(
        ...     user_id=UUID("..."),
        ...     stem="episode_193_raw",
        ...     transcript_type="original"
        ... )
        >>> if data:
        ...     print(f"Loaded {len(data)} words")
    """
    if gcs_client is None:
        gcs_client = GCSClient()

    user_hex = user_id.hex

    # If specific type requested, try only that
    types_to_try = [transcript_type] if transcript_type else TRANSCRIPT_TYPES

    for t_type in types_to_try:
        gcs_key = f"{user_hex}/transcripts/{stem}.{t_type}.json"

        try:
            logger.debug(
                f"[transcript_gcs] Attempting to load transcript: {stem}.{t_type}.json"
            )

            # Download from GCS
            data = gcs_client.download_bytes(
                bucket_name=GCS_BUCKET,
                object_key=gcs_key,
            )

            # Parse JSON
            transcript_data = json.loads(data.decode("utf-8"))

            logger.info(
                f"[transcript_gcs] Successfully loaded transcript: {stem}.{t_type}.json"
            )

            return transcript_data

        except Exception as e:
            logger.debug(
                f"[transcript_gcs] Transcript not found or failed to load: {stem}.{t_type}.json - {e}"
            )
            continue

    logger.warning(
        f"[transcript_gcs] No transcript found for stem: {stem} (tried types: {types_to_try})"
    )
    return None


def transcript_exists_in_gcs(
    user_id: UUID,
    stem: str,
    transcript_type: Optional[str] = None,
    gcs_client: Optional[GCSClient] = None,
) -> bool:
    """
    Check if transcript exists in GCS without downloading it.

    Args:
        user_id: User UUID who owns the transcript
        stem: Base filename stem (without extension)
        transcript_type: Specific transcript type to check, or None to check any type
        gcs_client: Optional GCS client (creates one if not provided)

    Returns:
        True if transcript exists, False otherwise

    Example:
        >>> if transcript_exists_in_gcs(user_id, "episode_193_raw", "original"):
        ...     print("Transcript exists!")
    """
    if gcs_client is None:
        gcs_client = GCSClient()

    user_hex = user_id.hex

    # If specific type requested, check only that
    types_to_try = [transcript_type] if transcript_type else TRANSCRIPT_TYPES

    for t_type in types_to_try:
        gcs_key = f"{user_hex}/transcripts/{stem}.{t_type}.json"

        try:
            # Check if object exists (lightweight operation)
            gcs_client.get_metadata(bucket_name=GCS_BUCKET, object_key=gcs_key)
            logger.debug(
                f"[transcript_gcs] Transcript exists: {stem}.{t_type}.json"
            )
            return True
        except Exception:
            continue

    return False


def delete_transcript_from_gcs(
    user_id: UUID,
    stem: str,
    transcript_type: Optional[str] = None,
    gcs_client: Optional[GCSClient] = None,
) -> int:
    """
    Delete transcript(s) from GCS.

    Args:
        user_id: User UUID who owns the transcript
        stem: Base filename stem (without extension)
        transcript_type: Specific transcript type to delete, or None to delete all types
        gcs_client: Optional GCS client (creates one if not provided)

    Returns:
        Number of transcripts deleted

    Example:
        >>> count = delete_transcript_from_gcs(user_id, "episode_193_raw", "original")
        >>> print(f"Deleted {count} transcript(s)")
    """
    if gcs_client is None:
        gcs_client = GCSClient()

    user_hex = user_id.hex

    # If specific type requested, delete only that
    types_to_delete = [transcript_type] if transcript_type else TRANSCRIPT_TYPES

    deleted_count = 0
    for t_type in types_to_delete:
        gcs_key = f"{user_hex}/transcripts/{stem}.{t_type}.json"

        try:
            gcs_client.delete_object(bucket_name=GCS_BUCKET, object_key=gcs_key)
            logger.info(
                f"[transcript_gcs] Deleted transcript: {stem}.{t_type}.json"
            )
            deleted_count += 1
        except Exception as e:
            logger.debug(
                f"[transcript_gcs] Failed to delete or doesn't exist: {stem}.{t_type}.json - {e}"
            )
            continue

    return deleted_count


def get_transcript_gcs_url(
    user_id: UUID,
    stem: str,
    transcript_type: str = "working",
) -> str:
    """
    Generate GCS URL for a transcript without checking if it exists.

    Args:
        user_id: User UUID who owns the transcript
        stem: Base filename stem (without extension)
        transcript_type: Type of transcript

    Returns:
        GCS URL string

    Example:
        >>> url = get_transcript_gcs_url(user_id, "episode_193_raw", "original")
        >>> print(url)
        gs://ppp-media-us-west1/abc123.../transcripts/episode_193_raw.original.json
    """
    user_hex = user_id.hex
    gcs_key = f"{user_hex}/transcripts/{stem}.{transcript_type}.json"
    return f"gs://{GCS_BUCKET}/{gcs_key}"
