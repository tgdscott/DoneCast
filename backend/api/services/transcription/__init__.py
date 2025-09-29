from __future__ import annotations

"""
Compatibility shim for transcription service.

This package name shadows the legacy module `api.services.transcription`.
Some code imports the package (e.g., `from api.services import transcription as trans`)
and expects `get_word_timestamps` to exist. Provide a thin wrapper that mirrors
the logic from the module so both import styles work.
"""

from typing import List, Dict, Any
import logging
from pathlib import Path
import os

from ...core.paths import MEDIA_DIR
from ..transcription_assemblyai import assemblyai_transcribe_with_speakers
from ..transcription_google import google_transcribe_with_words


def get_word_timestamps(filename: str) -> List[Dict[str, Any]]:
	"""Return per-word timestamps for an uploaded media file.

	Strategy:
	  1. AssemblyAI with speakers (preferred)
	  2. Google Speech word offsets (adds speaker=None)

	Raises on failure to keep callers' error handling consistent.
	"""
	# filename is expected to be a local name relative to MEDIA_DIR.
	audio_path = MEDIA_DIR / filename
	if not audio_path.exists():
		raise FileNotFoundError(f"Audio file not found: {filename}")

	# 1) AssemblyAI
	try:
		logging.info("[transcription/pkg] Using AssemblyAI with disfluencies=True")
		return assemblyai_transcribe_with_speakers(filename)
	except Exception:
		logging.warning("[transcription/pkg] AssemblyAI failed; falling back to Google", exc_info=True)

	# 2) Google fallback
	try:
		words = google_transcribe_with_words(filename)
		for w in words:
			if 'speaker' not in w:
				w['speaker'] = None
		return words
	except Exception:
		logging.warning("[transcription/pkg] Google fallback failed", exc_info=True)
		# Mirror behavior of module: only AssemblyAI and Google supported.
		raise NotImplementedError("Only AssemblyAI and Google transcription are supported.")


def transcribe_media_file(filename: str):
	"""Synchronous entrypoint for internal task: transcribe a media file.

	Accepts either a local filename (relative to MEDIA_DIR) or a gs:// URI.
	When a gs:// path is provided (prod uploads), this will download the
	object to MEDIA_DIR and transcribe that temporary local copy.

	Side-effect: writes a transcript JSON to TRANSCRIPTS_DIR using the stem
	of the input filename (e.g., my_audio.json) so that UI polling for
	/api/ai/transcript-ready and AI suggestion endpoints can discover it.
	"""

	def _is_gcs_path(p: str) -> bool:
		return isinstance(p, str) and p.startswith("gs://")

	def _download_gcs_to_media(gcs_uri: str) -> str:
		"""Download gs://bucket/key to MEDIA_DIR and return the local filename (basename)."""
		from google.cloud import storage  # lazy import, available in prod
		try:
			# Parse gs://bucket/key
			without_scheme = gcs_uri[len("gs://"):]
			bucket_name, key = without_scheme.split("/", 1)
			dst_name = os.path.basename(key) or "audio"
			dst_path = MEDIA_DIR / dst_name
			MEDIA_DIR.mkdir(parents=True, exist_ok=True)
			client = storage.Client()
			bucket = client.bucket(bucket_name)
			blob = bucket.blob(key)
			blob.download_to_filename(str(dst_path))
			return dst_name
		except Exception as e:
			logging.error("[transcription] GCS download failed for %s: %s", gcs_uri, e)
			raise

	local_name: str = filename
	delete_after: bool = False
	if _is_gcs_path(filename):
		local_name = _download_gcs_to_media(filename)
		delete_after = True

	try:
		words = get_word_timestamps(local_name)
		# Persist transcript JSON for discovery by the AI endpoints
		try:
			from ...core.paths import TRANSCRIPTS_DIR  # lazy import to avoid cycles
			TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
			stem = Path(local_name).stem
			out_path = TRANSCRIPTS_DIR / f"{stem}.json"
			if not out_path.exists():
				import json as _json
				payload = _json.dumps(words, ensure_ascii=False, indent=2)
				out_path.write_text(payload, encoding="utf-8")
				# Best-effort durable copy to GCS if configured
				try:
					bucket = (os.getenv("TRANSCRIPTS_BUCKET") or os.getenv("MEDIA_BUCKET") or "").strip()
					if bucket:
						from ...infrastructure.gcs import upload_bytes  # type: ignore
						key = f"transcripts/{stem}.json"
						upload_bytes(bucket, key, payload.encode("utf-8"), content_type="application/json; charset=utf-8")
				except Exception:
					pass
		except Exception:
			# Best-effort; do not fail transcription if persisting the JSON has issues
			pass
		return words
	except Exception:
		raise
	finally:
		# Best-effort cleanup of the temporary local copy for gs:// inputs
		if delete_after:
			try:
				(MEDIA_DIR / local_name).unlink(missing_ok=True)
			except Exception:
				pass

