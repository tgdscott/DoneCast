import os
import logging
from pathlib import Path
from typing import Optional

from worker.tasks import celery_app
from api.core.paths import WS_ROOT as PROJECT_ROOT
from api.core.database import get_session
from api.core import crud
from api.services.image_utils import ensure_cover_image_constraints
from api.services.publisher import SpreakerClient
from uuid import UUID


@celery_app.task(name="publish_episode_to_spreaker_task")
def publish_episode_to_spreaker_task(
	episode_id: str,
	spreaker_show_id: str,
	title: str,
	description: Optional[str],
	auto_published_at: Optional[str],
	spreaker_access_token: str,
	publish_state: str,
):
	"""
	Pushes the episode to Spreaker with description and optional cover.
	Sets status accordingly; enforces immediate private visibility if requested.
	"""
	logging.info(f"[publish] CWD = {os.getcwd()}")
	session = next(get_session())

	try:
		episode = crud.get_episode_by_id(session, UUID(episode_id))
		if not episode:
			logging.warning("[publish] stale job: episode %s not found; dropping task", episode_id)
			return {"dropped": True, "reason": "episode not found", "episode_id": episode_id}
		if not episode.final_audio_path:
			logging.warning("[publish] stale job: episode %s has no final audio; dropping task", episode_id)
			return {"dropped": True, "reason": "no final audio", "episode_id": episode_id}

		cover_candidate = getattr(episode, "cover_path", None)
		if not cover_candidate and getattr(episode, "podcast_id", None):
			pod = crud.get_podcast_by_id(session, episode.podcast_id)
			if pod and pod.cover_path:
				cover_candidate = pod.cover_path

		image_file_path = None
		if cover_candidate and isinstance(cover_candidate, str):
			p = Path(cover_candidate)
			if not p.is_file():
				p2 = (PROJECT_ROOT / "media_uploads" / cover_candidate).resolve()
				if p2.is_file():
					p = p2
			if p.is_file():
				image_file_path = ensure_cover_image_constraints(str(p))

		desc = description or getattr(episode, "description", None) or getattr(episode, "show_notes", None) or ""

		audio_path = str(episode.final_audio_path)
		if audio_path and not os.path.isabs(audio_path):
			candidate = (PROJECT_ROOT / 'final_episodes' / os.path.basename(audio_path)).resolve()
			if candidate.is_file():
				audio_path = str(candidate)
		if not os.path.isfile(audio_path):
			raise RuntimeError(f"Final audio file not found for publishing: {audio_path}")

		client = SpreakerClient(spreaker_access_token)

		parsed_auto_str = None
		if auto_published_at:
			try:
				from datetime import datetime, timezone
				dt = datetime.fromisoformat(auto_published_at.replace('Z', '+00:00'))
				if dt.tzinfo is None:
					dt = dt.replace(tzinfo=timezone.utc)
				parsed_auto_str = dt.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
			except Exception as e:
				logging.warning(f"Invalid auto_published_at '{auto_published_at}': {e}; sending without scheduling.")
				parsed_auto_str = None

		original_auto = parsed_auto_str
		logging.info(f"[publish] Uploading episode {episode_id} to show {spreaker_show_id} auto_published_at={parsed_auto_str}")
		if not str(spreaker_show_id).isdigit():
			raise RuntimeError(f"Spreaker show id must be numeric; got {spreaker_show_id}")

		tags_arg = None
		try:
			if hasattr(episode, 'tags'):
				tag_list = episode.tags()
				if isinstance(tag_list, (list, tuple)):
					tags_arg = ",".join(t for t in [str(t).strip() for t in tag_list] if t)
		except Exception:
			pass
		explicit_arg = bool(getattr(episode, 'is_explicit', False))

		ok, result = client.upload_episode(
			show_id=str(spreaker_show_id),
			title=title,
			file_path=audio_path,
			description=desc,
			publish_state=publish_state,
			auto_published_at=parsed_auto_str,
			image_file=image_file_path,
			tags=tags_arg,
			explicit=explicit_arg,
		)

		if ok:
			if original_auto:
				if str(getattr(episode, 'status', '')) != 'published':
					try:
						from api.models.podcast import EpisodeStatus as _EpStatus
						episode.status = _EpStatus.processed  # type: ignore[attr-defined]
					except Exception:
						episode.status = 'processed'  # type: ignore[assignment]
				try:
					from datetime import datetime, timezone
					dt = datetime.strptime(original_auto, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
					episode.publish_at = dt
				except Exception:
					pass
				episode.is_published_to_spreaker = False
			else:
				try:
					from api.models.podcast import EpisodeStatus as _EpStatus
					episode.status = _EpStatus.published  # type: ignore[attr-defined]
				except Exception:
					episode.status = 'published'  # type: ignore[assignment]
				episode.is_published_to_spreaker = True

				try:
					desired_private = str(publish_state).lower() in {'unpublished', 'private'}
				except Exception:
					desired_private = False
				try:
					if desired_private and isinstance(result, dict) and result.get('episode_id'):
						ep_id = str(result['episode_id'])
						ok_upd, upd_resp = client.update_episode(ep_id, publish_state='unpublished')
						logging.info(f"[publish] enforced private via update ok={ok_upd}")
						if not ok_upd:
							logging.warning(f"[publish] private enforce failed: {upd_resp}")
				except Exception:
					logging.warning('[publish] failed to enforce private via update', exc_info=True)

			try:
				if isinstance(result, dict) and result.get('episode_id'):
					ep_id = str(result['episode_id'])
					ok_ep, ep_resp = client.get_episode(ep_id)
					if ok_ep:
						ep_obj = ep_resp.get('episode') or ep_resp
						remote_url = (
							ep_obj.get('image_url')
							or ep_obj.get('image_original_url')
							or ep_obj.get('image_large_url')
						)
						if remote_url:
							if remote_url != getattr(episode, 'remote_cover_url', None):
								setattr(episode, 'remote_cover_url', remote_url)
							if episode.cover_path and not str(episode.cover_path).lower().startswith(('http://','https://')):
								local_path = (PROJECT_ROOT / 'media_uploads' / Path(episode.cover_path).name)
								if local_path.is_file():
									try:
										local_path.unlink()
										episode.cover_path = remote_url
									except Exception:
										logging.warning(f"[publish] Failed to delete local cover {local_path}")
					else:
						logging.info(f"[publish] Remote episode fetch failed ok_ep={ok_ep}")
				else:
					logging.debug('[publish] No episode_id in upload result; skip cover sync')
			except Exception:
				logging.warning('[publish] cover sync error', exc_info=True)

			if isinstance(result, dict) and result.get('episode_id'):
				episode.spreaker_episode_id = str(result['episode_id'])

			episode.spreaker_publish_error = None
			episode.spreaker_publish_error_detail = None
			episode.needs_republish = False
			session.add(episode)
			session.commit()

			logging.info(f"Published to Spreaker: {episode.title} (id={episode.spreaker_episode_id})")
			try:
				from api.models.notification import Notification
				note = Notification(user_id=episode.user_id, type='publish', title='Episode published', body=f"{episode.title}")
				session.add(note)
				session.commit()
			except Exception:
				logging.warning("[publish] Failed to create notification", exc_info=True)

			return {"ok": True, "episode_id": episode.id, "result": result}
		else:
			episode.spreaker_publish_error = str(result)
			try:
				import json as _json
				episode.spreaker_publish_error_detail = _json.dumps(result)
			except Exception:
				episode.spreaker_publish_error_detail = None
			session.add(episode)
			session.commit()
			return {"ok": False, "error": str(result)}
	except Exception as e:
		logging.exception(f"[publish] error for episode {episode_id}: {e}")
		raise
	finally:
		try:
			session.close()
		except Exception:
			pass

