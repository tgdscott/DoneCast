"""
worker.tasks package bootstrap.

Exports celery_app and re-exports legacy task functions from the monolith
worker/tasks.py so existing imports like `from worker.tasks import create_podcast_episode`
continue to work until tasks are migrated in WT-2.
"""

from .app import celery_app  # backwards-compatible import path

# Prefer re-exporting from new domain modules
try:
	from .transcription import transcribe_media_file  # type: ignore F401
except Exception:
	transcribe_media_file = None  # type: ignore
try:
	from .audio import create_podcast_episode  # type: ignore F401
except Exception:
	create_podcast_episode = None  # type: ignore
try:
	from .publish import publish_episode_to_spreaker_task  # type: ignore F401
except Exception:
	publish_episode_to_spreaker_task = None  # type: ignore

# Fallback: attempt to load legacy monolith if any symbol missing
if not (transcribe_media_file and create_podcast_episode and publish_episode_to_spreaker_task):
	import sys
	import importlib.util
	from pathlib import Path

	_pkg_dir = Path(__file__).resolve().parent
	_legacy_mod_path = _pkg_dir.parent / "tasks.py"
	if _legacy_mod_path.is_file():
		try:
			spec = importlib.util.spec_from_file_location("worker.tasks_legacy", str(_legacy_mod_path))
			if spec and spec.loader:
				legacy = importlib.util.module_from_spec(spec)
				sys.modules["worker.tasks_legacy"] = legacy
				spec.loader.exec_module(legacy)
				for _name in (
					"transcribe_media_file",
					"create_podcast_episode",
					"publish_episode_to_spreaker_task",
				):
					if globals().get(_name) is None and hasattr(legacy, _name):
						globals()[_name] = getattr(legacy, _name)
		except Exception:
			pass

