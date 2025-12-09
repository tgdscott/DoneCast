"""Service layer public API.

Provides lightweight shims that can be imported directly from
``api.services``. Add shared helpers here to avoid circular imports.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from api.core.paths import MEDIA_DIR, FINAL_DIR
from api.models.podcast import PodcastTemplate
from types import SimpleNamespace

from api.services.audio import processor as audio_processor
from api.services.audio.processor import process_and_assemble_episode
from api.services.auphonic_client import process_episode_with_auphonic, AuphonicError
from api.services import transcription, transcripts, clean_engine
try:
	from infrastructure.tasks_client import enqueue_http_task as enqueue_task  # type: ignore
except Exception:
	def enqueue_task(*args, **kwargs):
		raise ImportError("tasks_client unavailable")
from . import notification  # re-export for legacy orchestrator imports


def _resolve_audio_path(main_content_filename: str) -> Path:
	"""Return an absolute path to the input audio file."""

	candidate = Path(main_content_filename)
	if candidate.is_absolute() and candidate.exists():
		return candidate
	from_media = MEDIA_DIR / main_content_filename
	if from_media.exists():
		return from_media
	raise FileNotFoundError(f"Input audio not found: {main_content_filename}")


def _load_template(session: Any, episode: Any) -> Any:
	"""Best-effort lookup of the episode template for downstream mixing."""
	try:
		template_id = getattr(episode, "template_id", None) or getattr(episode, "template", None)
		if template_id is None:
			return None
		# If template is already an object, return it directly
		if isinstance(template_id, PodcastTemplate):
			return template_id
		return session.get(PodcastTemplate, template_id)
	except Exception:
		logging.warning("[services] Failed to load template for episode %s", getattr(episode, "id", None), exc_info=True)
		return None


def audio_process_and_assemble_episode(
	*,
	session: Any,
	episode: Any,
	user: Any,
	podcast: Any,
	main_content_filename: str,
	output_filename: str,
	tts_values: dict | None = None,
	episode_details: dict | None = None,
	use_auphonic: bool | None = None,
	words_json_path: str | Path | None = None,
) -> Path:
	"""Final audio assembly pipeline (AQG-compliant).

	- Optionally process audio via Auphonic for Pro-tier quality.
	- Run the internal mixer to add template music/intro/outro and normalize to podcast LUFS.
	- Propagate errors to the orchestrator; do **not** swallow exceptions.
	"""

	log_prefix = "[services]"
	episode_id = getattr(episode, "id", "unknown")

	# Resolve raw input path
	input_path = _resolve_audio_path(main_content_filename)
	selected_path = input_path

	# Optional Auphonic pass
	if use_auphonic:
		try:
			auphonic_out = process_episode_with_auphonic(
				audio_path=input_path,
				episode_title=str(getattr(episode, "title", output_filename) or output_filename),
				output_dir=FINAL_DIR,
			)
			candidate = Path(auphonic_out.get("output_audio_path") or "")
			if candidate.exists():
				selected_path = candidate
				logging.info(
					"%s Auphonic processed audio ready: %s (episode=%s)",
					log_prefix,
					selected_path,
					episode_id,
				)
		except AuphonicError as err:
			logging.warning(
				"%s Auphonic failed (%s); falling back to raw audio %s",
				log_prefix,
				err,
				input_path,
			)
		except Exception:
			logging.warning(
				"%s Auphonic integration raised unexpected error; falling back to raw audio",
				log_prefix,
				exc_info=True,
			)

	# Final mixing & mastering
	try:
		template_obj = _load_template(session, episode)
		cleanup_opts = (episode_details or {}).get("cleanup_options") or {}
		final_path, _, _ = process_and_assemble_episode(
			template=template_obj,
			main_content_filename=str(selected_path),
			output_filename=output_filename,
			cleanup_options=cleanup_opts,
			tts_overrides=tts_values or {},
			cover_image_path=getattr(episode, "cover_image_path", None),
			elevenlabs_api_key=getattr(user, "elevenlabs_api_key", None),
			tts_provider=(episode_details or {}).get("tts_provider") or "elevenlabs",
			mix_only=False,
			words_json_path=str(words_json_path) if words_json_path else None,
		)
		logging.info("%s Final mix complete for episode=%s → %s", log_prefix, episode_id, final_path)
		return Path(final_path)
	except Exception:
		# Do not swallow errors; surface to orchestrator
		logging.error("%s Final assembly failed for episode=%s", log_prefix, episode_id, exc_info=True)
		raise


__all__ = [
	"audio_process_and_assemble_episode",
	"notification",
	"transcription",
	"transcripts",
	"clean_engine",
	"audio_processor",
	"enqueue_task",
]

# Legacy shim: expose a namespace for monkeypatching api.services.services.*
services = SimpleNamespace(
	transcription=transcription,
	transcripts=transcripts,
	clean_engine=clean_engine,
	audio_processor=audio_processor,
)
__all__.append("services")
