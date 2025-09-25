import logging
from datetime import datetime, timedelta

from worker.tasks import celery_app
from api.core.database import get_session
from api.core.paths import MEDIA_DIR
from api.models.podcast import MediaItem, MediaCategory, Episode
from sqlmodel import select

try:
	from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
	ZoneInfo = None  # type: ignore


@celery_app.task(name="maintenance.purge_expired_uploads")
def purge_expired_uploads() -> dict:
	"""Delete raw uploads that have expired (expires_at <= now) and are not used by any episode.

	Safety:
	- Only targets MediaCategory.main_content.
	- Skips items missing filename.
	- Idempotent: deleting missing files is tolerated.
	- Does not remove media referenced by Episode.working_audio_name or Episode.final_audio_path.
	"""
	session = next(get_session())
	now = datetime.utcnow()
	removed = 0
	skipped_in_use = 0
	checked = 0
	try:
		# Fetch candidates: expired main_content
		q = (
			select(MediaItem)
			.where(MediaItem.category == MediaCategory.main_content)  # type: ignore
			.where(MediaItem.expires_at != None)  # type: ignore
			.where(MediaItem.expires_at <= now)  # type: ignore
			.limit(10000)
		)
		items = session.exec(q).all()
		# Build a set of in-use basenames from episodes to avoid deleting source files that are still referenced
		q_eps = select(Episode)
		eps = session.exec(q_eps).all()
		in_use = set()
		for e in eps:
			for name in (getattr(e, 'working_audio_name', None), getattr(e, 'final_audio_path', None)):
				if name:
					try:
						from pathlib import Path
						in_use.add(Path(str(name)).name)
					except Exception:
						in_use.add(str(name))
		for m in items:
			checked += 1
			fn = getattr(m, 'filename', None)
			if not fn:
				continue
			if fn in in_use:
				skipped_in_use += 1
				continue
			try:
				path = MEDIA_DIR / fn
				if path.exists():
					try:
						path.unlink()
					except Exception:
						logging.warning("[purge] Failed to unlink %s", path, exc_info=True)
				session.delete(m)
				removed += 1
			except Exception:
				logging.warning("[purge] Failed to delete MediaItem %s", getattr(m, 'id', None), exc_info=True)
		if removed:
			session.commit()
	except Exception:
		session.rollback()
		logging.warning("[purge] purge_expired_uploads failed", exc_info=True)
	finally:
		session.close()
	logging.info("[purge] expired uploads: checked=%s removed=%s skipped_in_use=%s", checked, removed, skipped_in_use)
	return {"checked": checked, "removed": removed, "skipped_in_use": skipped_in_use}
