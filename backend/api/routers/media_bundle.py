import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Literal
from uuid import UUID, uuid4

import requests
from fastapi import APIRouter, Depends, HTTPException, status
from google.cloud import storage
from pydantic import BaseModel
from sqlmodel import Session

from api.core.database import get_session
from api.models.podcast import MediaCategory, MediaItem
from api.models.user import User
from api.routers.auth import get_current_user

router = APIRouter(prefix="/media", tags=["Media Library"])
log = logging.getLogger("media.bundle")


class SegmentBundlePart(BaseModel):
	media_item_id: UUID
	filename: Optional[str] = None
	processing_mode: Literal["advanced", "standard"] = "standard"


class SegmentBundleRequest(BaseModel):
	segments: List[SegmentBundlePart]
	friendly_name: Optional[str] = None


class SegmentBundleResponse(BaseModel):
	media_item: MediaItem
	duration_seconds: Optional[float] = None


_storage_client = None


def _get_storage_client():
	global _storage_client
	if _storage_client is not None:
		return _storage_client
	try:
		_storage_client = storage.Client()
		return _storage_client
	except Exception as exc:
		log.error("Failed to initialize GCS client: %s", exc, exc_info=True)
		raise HTTPException(
			status_code=500,
			detail="Google Cloud Storage credentials are not configured. "
			       "Set GOOGLE_APPLICATION_CREDENTIALS or run 'gcloud auth application-default login' on the API server.",
		)


def _parse_gs_url(url: str) -> tuple[str, str]:
	parts = url[5:].split("/", 1)
	if len(parts) != 2:
		raise ValueError("Invalid GCS URL")
	return parts[0], parts[1]


def _download_segment_to_path(source: str, dest: Path) -> Path:
	if source.startswith("gs://"):
		bucket_name, key = _parse_gs_url(source)
		client = _get_storage_client()
		dest.parent.mkdir(parents=True, exist_ok=True)
		try:
			bucket = client.bucket(bucket_name)
			blob = bucket.blob(key)
			blob.download_to_filename(str(dest))
			log.info("[bundle] Downloaded %s -> %s", source, dest)
			return dest
		except Exception as exc:
			log.error("[bundle] Failed to download %s: %s", source, exc, exc_info=True)
			raise HTTPException(status_code=500, detail=f"Failed to download audio from GCS: {exc}")

	if source.startswith("http://") or source.startswith("https://"):
		dest.parent.mkdir(parents=True, exist_ok=True)
		try:
			with requests.get(source, stream=True, timeout=120) as resp:
				resp.raise_for_status()
				with dest.open("wb") as fh:
					for chunk in resp.iter_content(chunk_size=1024 * 1024):
						if chunk:
							fh.write(chunk)
			log.info("[bundle] Downloaded %s -> %s", source, dest)
			return dest
		except Exception as exc:
			log.error("[bundle] Failed to download %s: %s", source, exc, exc_info=True)
			raise HTTPException(status_code=500, detail=f"Failed to download audio from URL: {exc}")

	src_path = Path(source)
	if not src_path.exists():
		raise HTTPException(status_code=404, detail=f"Audio file not found: {source}")
	dest.parent.mkdir(parents=True, exist_ok=True)
	shutil.copy2(src_path, dest)
	return dest


def _run_ffmpeg(cmd: List[str]) -> None:
	try:
		subprocess.run(
			cmd,
			check=True,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
		)
	except FileNotFoundError:
		raise HTTPException(
			status_code=500,
			detail="ffmpeg is not installed on the API server. Install ffmpeg to enable segment bundling.",
		)
	except subprocess.CalledProcessError as exc:
		stderr = exc.stderr.decode("utf-8", errors="ignore") if exc.stderr else ""
		log.error("[bundle] ffmpeg failed: %s", stderr)
		raise HTTPException(status_code=500, detail="Failed to process audio segments with ffmpeg.")


def _convert_to_wav(source: Path, dest: Path) -> Path:
	cmd = [
		"ffmpeg",
		"-y",
		"-i",
		str(source),
		"-ar",
		"48000",
		"-ac",
		"2",
		"-c:a",
		"pcm_s16le",
		str(dest),
	]
	_run_ffmpeg(cmd)
	return dest


def _concat_wav(parts: List[Path], dest: Path) -> Path:
	if len(parts) == 1:
		shutil.copy2(parts[0], dest)
		return dest
	manifest = dest.parent / "concat.txt"
	with manifest.open("w", encoding="utf-8") as fh:
		for part in parts:
			line = part.as_posix().replace("'", r"'\''")
			fh.write(f"file '{line}'\n")
	cmd = [
		"ffmpeg",
		"-y",
		"-f",
		"concat",
		"-safe",
		"0",
		"-i",
		str(manifest),
		"-c",
		"copy",
		str(dest),
	]
	_run_ffmpeg(cmd)
	try:
		manifest.unlink(missing_ok=True)  # type: ignore[arg-type]
	except Exception:
		pass
	return dest


def _probe_audio_seconds(path: Path) -> Optional[float]:
	cmd = [
		"ffprobe",
		"-v",
		"error",
		"-show_entries",
		"format=duration",
		"-of",
		"default=noprint_wrappers=1:nokey=1",
		str(path),
	]
	try:
		result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		raw = (result.stdout or b"").decode("utf-8", errors="ignore").strip()
		if raw:
			seconds = float(raw)
			return seconds if seconds > 0 else None
	except Exception:
		return None
	return None


def _kickoff_transcription(media_item: MediaItem, user_id: UUID) -> None:
	try:
		from worker.tasks import transcribe_media_file  # type: ignore
		transcribe_media_file.delay(media_item.filename, str(user_id))
	except Exception:
		pass


@router.post("/main-content/bundle", response_model=SegmentBundleResponse, status_code=status.HTTP_201_CREATED)
async def bundle_main_content_segments(
	payload: SegmentBundleRequest,
	session: Session = Depends(get_session),
	current_user: User = Depends(get_current_user),
):
	if not payload.segments:
		raise HTTPException(status_code=400, detail="At least one segment is required.")

	temp_dir = Path(tempfile.mkdtemp(prefix="segment-bundle-"))
	log.info("[bundle] Starting bundle for user=%s segments=%d", current_user.id, len(payload.segments))

	try:
		converted_parts: List[Path] = []
		for index, segment in enumerate(payload.segments):
			media_item = session.get(MediaItem, segment.media_item_id)
			if not media_item or media_item.user_id != current_user.id:
				raise HTTPException(status_code=404, detail="One of the selected segments was not found.")

			source = segment.filename or media_item.filename
			if not source:
				raise HTTPException(status_code=400, detail="Segment is missing a filename reference.")

			download_path = temp_dir / f"segment_{index}.src"
			local_source = _download_segment_to_path(source, download_path)
			wav_path = temp_dir / f"segment_{index}.wav"
			converted = _convert_to_wav(local_source, wav_path)
			converted_parts.append(converted)

		combined_path = temp_dir / "bundle.wav"
		_concat_wav(converted_parts, combined_path)
		duration_seconds = _probe_audio_seconds(combined_path)

		from infrastructure import gcs as gcs_module  # type: ignore

		gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
		storage_key = f"{current_user.id.hex}/media_uploads/bundles/{uuid4().hex}.wav"
		with combined_path.open("rb") as fh:
			gcs_url = gcs_module.upload_fileobj(
				gcs_bucket,
				storage_key,
				fh,
				content_type="audio/wav",
				force_gcs=True,
			)

		friendly = payload.friendly_name or f"Segment bundle · {datetime.utcnow():%b %d %Y %H:%M}"
		bundle_item = MediaItem(
			filename=gcs_url,
			friendly_name=friendly,
			content_type="audio/wav",
			filesize=combined_path.stat().st_size,
			user_id=current_user.id,
			category=MediaCategory.main_content,
		)
		session.add(bundle_item)
		session.commit()
		session.refresh(bundle_item)

		_kickoff_transcription(bundle_item, current_user.id)
		log.info("[bundle] Created bundle media item %s for user %s", bundle_item.id, current_user.id)

		return SegmentBundleResponse(media_item=bundle_item, duration_seconds=duration_seconds)
	finally:
		shutil.rmtree(temp_dir, ignore_errors=True)

