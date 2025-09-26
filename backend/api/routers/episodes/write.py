import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Body, status
from sqlalchemy.orm import Session
from sqlmodel import select

from api.core.database import get_session
from api.core.auth import get_current_user
from api.models.user import User
from api.models.podcast import Episode, Podcast
from api.services.episodes import repo as _svc_repo
from uuid import UUID as _UUID
from pathlib import Path
from api.core.paths import FINAL_DIR, MEDIA_DIR, APP_ROOT

logger = logging.getLogger("ppp.episodes.write")

# Nested router: parent episodes router provides the '/episodes' prefix.
router = APIRouter(tags=["episodes"])  # parent provides prefix '/episodes'

PROJECT_ROOT = APP_ROOT


from .common import _final_url_for, _cover_url_for, _status_value


@router.patch("/{episode_id}", status_code=200)
def update_episode_metadata(
	episode_id: str,
	payload: Dict[str, Any],
	session: Session = Depends(get_session),
	current_user: User = Depends(get_current_user),
):
	try:
		eid = _UUID(str(episode_id))
	except Exception:
		raise HTTPException(status_code=404, detail="Episode not found")
	ep = _svc_repo.get_episode_by_id(session, eid, user_id=current_user.id)
	if not ep:
		raise HTTPException(status_code=404, detail="Episode not found")

	changed = False
	title = payload.get("title")
	if title is not None and title.strip() and title != ep.title:
		ep.title = title.strip()
		changed = True
	description = payload.get("description")
	if description is not None and description != ep.show_notes:
		ep.show_notes = description
		changed = True
        if "cover_image_path" in payload:
                cover_image_path = payload.get("cover_image_path")
                if cover_image_path and cover_image_path != getattr(ep, 'cover_path', None):
                        ep.cover_path = cover_image_path
                        # When switching to a freshly uploaded cover, prefer the local path until publish sync updates remote.
                        if hasattr(ep, 'remote_cover_url'):
                                ep.remote_cover_url = None
                        changed = True
                elif cover_image_path is None and getattr(ep, 'cover_path', None):
                        ep.cover_path = None
                        if hasattr(ep, 'remote_cover_url'):
                                ep.remote_cover_url = None
                        changed = True
	publish_state = payload.get("publish_state")
	if publish_state is not None:
		changed = True
	if "tags" in payload:
		tags = payload.get("tags") or []
		try:
			existing_tags = ep.tags() if hasattr(ep, 'tags') else []
		except Exception:
			existing_tags = []
		norm = [str(t).strip() for t in tags if str(t).strip()]
		if norm != existing_tags:
			if hasattr(ep, 'set_tags'):
				ep.set_tags(norm)
			else:
				import json as _json
				ep.tags_json = _json.dumps(norm)
			changed = True
	if "is_explicit" in payload:
		val = bool(payload.get("is_explicit"))
		if val != bool(getattr(ep, 'is_explicit', False)):
			ep.is_explicit = val
			changed = True
	if "image_crop" in payload:
		val = payload.get("image_crop") or None
		if val != getattr(ep, 'image_crop', None):
			if val:
				parts = [p.strip() for p in str(val).split(',')]
				if len(parts) == 4:
					try:
						[float(p) for p in parts]
					except Exception:
						raise HTTPException(status_code=400, detail="image_crop must be 'x1,y1,x2,y2'")
				else:
					raise HTTPException(status_code=400, detail="image_crop must have four comma-separated numbers")
			ep.image_crop = val
			changed = True
	if "season_number" in payload:
		raw = payload.get("season_number")
		new_val = None
		if raw not in (None, ""):
			try:
				new_val = int(raw)
				if new_val < 0:
					raise ValueError
			except Exception:
				raise HTTPException(status_code=400, detail="season_number must be a non-negative integer")
		if new_val != getattr(ep, 'season_number', None):
			ep.season_number = new_val
			changed = True
	if "episode_number" in payload:
		raw = payload.get("episode_number")
		new_val = None
		if raw not in (None, ""):
			try:
				new_val = int(raw)
				if new_val < 0:
					raise ValueError
			except Exception:
				raise HTTPException(status_code=400, detail="episode_number must be a non-negative integer")
		if new_val != getattr(ep, 'episode_number', None):
			ep.episode_number = new_val
			changed = True
	if changed and ("season_number" in payload or "episode_number" in payload):
		try:
			if ep.podcast_id and ep.season_number is not None and ep.episode_number is not None:
				dup = session.exec(
					select(Episode)
					.where(Episode.podcast_id == ep.podcast_id, Episode.season_number == ep.season_number, Episode.episode_number == ep.episode_number)
					.where(Episode.id != ep.id)
				).first()
				if dup:
					raise HTTPException(status_code=409, detail="Episode numbering already in use for this podcast")
		except HTTPException:
			raise
		except Exception:
			logger.exception("uniqueness check on update failed; proceeding")

	def _serialize_single(ep_obj: Episode) -> Dict[str, Any]:
		final_exists = False
		cover_exists = False
		try:
			if ep_obj.final_audio_path:
				try:
					cand = (FINAL_DIR / os.path.basename(str(ep_obj.final_audio_path))).resolve()
				except Exception:
					cand = FINAL_DIR / os.path.basename(str(ep_obj.final_audio_path))
				final_exists = cand.is_file()
			if getattr(ep_obj, 'remote_cover_url', None):
				cover_exists = True
			else:
				if ep_obj.cover_path and not str(ep_obj.cover_path).lower().startswith(('http://','https://')):
					try:
						cand = (MEDIA_DIR / os.path.basename(str(ep_obj.cover_path))).resolve()
					except Exception:
						cand = MEDIA_DIR / os.path.basename(str(ep_obj.cover_path))
					cover_exists = cand.is_file()
				elif ep_obj.cover_path:
					cover_exists = True
		except Exception:
			pass
		preferred_cover = getattr(ep_obj, 'remote_cover_url', None) or ep_obj.cover_path
		stream_url = None
		try:
			spk_id = getattr(ep_obj, 'spreaker_episode_id', None)
			if spk_id:
				stream_url = f"https://api.spreaker.com/v2/episodes/{spk_id}/play"
		except Exception:
			stream_url = None
		final_audio_url = _final_url_for(ep_obj.final_audio_path)
		playback_url = stream_url or final_audio_url
		playback_type = 'stream' if stream_url else ('local' if final_audio_url else 'none')
		pub_at_iso = None
		try:
			pub_dt = getattr(ep_obj, 'publish_at', None)
			if pub_dt:
				if pub_dt.tzinfo is None or pub_dt.tzinfo.utcoffset(pub_dt) is None:
					pub_dt = pub_dt.replace(tzinfo=timezone.utc)
				pub_at_iso = pub_dt.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
		except Exception:
			pub_at_iso = None
		base_status = _status_value(ep_obj.status)
		is_scheduled = False
		derived_status = base_status
		if pub_at_iso and base_status != 'published':
			try:
				dt_obj = getattr(ep_obj, 'publish_at')
				if dt_obj and dt_obj > datetime.utcnow():
					is_scheduled = True
					derived_status = 'scheduled'
			except Exception:
				pass
		return {
			"id": str(ep_obj.id),
			"title": ep_obj.title,
			"status": derived_status,
			"processed_at": ep_obj.processed_at.isoformat() if getattr(ep_obj, 'processed_at', None) else None,
			"final_audio_url": final_audio_url,
			"cover_url": _cover_url_for(preferred_cover),
			"description": getattr(ep_obj, 'show_notes', None) or "",
			"tags": getattr(ep_obj, 'tags', lambda: [])(),
			"is_explicit": bool(getattr(ep_obj, 'is_explicit', False)),
			"image_crop": getattr(ep_obj, 'image_crop', None),
			"season_number": getattr(ep_obj, 'season_number', None),
			"episode_number": getattr(ep_obj, 'episode_number', None),
			"spreaker_episode_id": getattr(ep_obj, 'spreaker_episode_id', None),
			"is_published_to_spreaker": bool(getattr(ep_obj, 'is_published_to_spreaker', False)),
			"final_audio_exists": final_exists,
			"cover_exists": cover_exists,
			"cover_path": preferred_cover,
			"final_audio_basename": os.path.basename(ep_obj.final_audio_path) if ep_obj.final_audio_path else None,
			"publish_error": getattr(ep_obj, 'spreaker_publish_error', None),
			"publish_error_detail": getattr(ep_obj, 'spreaker_publish_error_detail', None),
			"needs_republish": bool(getattr(ep_obj, 'needs_republish', False)),
			"publish_at": pub_at_iso,
			"publish_at_local": getattr(ep_obj, 'publish_at_local', None),
			"is_scheduled": is_scheduled,
			"plays_total": None,
			"stream_url": stream_url,
			"playback_url": playback_url,
			"playback_type": playback_type,
		}

	if not changed:
		return {"message": "No changes applied", "episode_id": str(ep.id), "episode": _serialize_single(ep)}

	session.add(ep)
	session.commit()
	session.refresh(ep)

	spreaker_id = getattr(ep, 'spreaker_episode_id', None)
	if spreaker_id:
		spreaker_access_token = getattr(current_user, "spreaker_access_token", None)
		if not spreaker_access_token:
			return {"message": "Local update saved; user not connected to Spreaker so remote not updated", "episode_id": str(ep.id)}
		try:
			from api.services.publisher import SpreakerClient
			client = SpreakerClient(spreaker_access_token)
			img_path = None
			if ep.cover_path:
				cp = str(ep.cover_path)
				if not cp.lower().startswith(("http://","https://")):
					candidates = [
						cp,
						str((PROJECT_ROOT / cp)),
						str((MEDIA_DIR / os.path.basename(cp))),
					]
					for cand in candidates:
						if os.path.isfile(cand):
							img_path = cand
							break
			logger.info(
				"[spreaker-sync] attempt episode update id=%s title=%s desc_len=%s publish_state=%s cover=%s",
				spreaker_id,
				bool(ep.title),
				len(ep.show_notes or ""),
				publish_state,
				bool(img_path),
			)
			send_title = 'title' in payload and title is not None
			send_description = 'description' in payload and description is not None
			send_publish_state = publish_state is not None
			send_tags = ('tags' in payload)
			send_explicit = ('is_explicit' in payload)
			tags_arg = None
			if send_tags:
				try:
					tag_list = ep.tags() if hasattr(ep, 'tags') else []
				except Exception:
					tag_list = []
				if isinstance(tag_list, (list, tuple)):
					tags_arg = ",".join(t for t in [str(t).strip() for t in tag_list] if t)
				else:
					tags_arg = str(tag_list)
			explicit_arg = bool(getattr(ep, 'is_explicit', False)) if send_explicit else None

			ok, resp = client.update_episode(
				spreaker_id,
				title=ep.title if send_title else None,
				description=ep.show_notes if send_description else None,
				publish_state=publish_state if send_publish_state else None,
				tags=tags_arg,
				explicit=explicit_arg,
				image_file=img_path,
			)
			if not ok:
				try:
					ep.spreaker_publish_error = "update_failed"
					ep.spreaker_publish_error_detail = str(resp)[:4000]
					session.add(ep)
					session.commit()
				except Exception as _e:
					logger.warning("[spreaker-sync] failed to persist error detail: %s", _e)
			else:
				try:
					if getattr(ep, 'spreaker_publish_error', None):
						ep.spreaker_publish_error = None
						ep.spreaker_publish_error_detail = None
					if isinstance(resp, dict):
						ep_remote = resp.get('episode') if 'episode' in resp else resp
						if isinstance(ep_remote, dict):
							new_remote_cover = ep_remote.get('image_url') or ep_remote.get('image_original_url')
							if new_remote_cover and new_remote_cover != getattr(ep, 'remote_cover_url', None):
								ep.remote_cover_url = new_remote_cover
					session.add(ep)
					session.commit()
				except Exception:
					session.rollback()
			base_resp = {
				"message": "Episode updated (remote sync {} )".format('ok' if ok else 'failed'),
				"episode_id": str(ep.id),
				"spreaker_result": resp,
				"remote_attempt": {
					"used_cover": bool(img_path),
					"cover_path": img_path,
					"publish_state": publish_state,
					"payload_fields": [
						f for f, sent in [
							("title", send_title),
							("description", send_description),
							("publish_state", send_publish_state),
							("tags", send_tags),
							("explicit", send_explicit),
							("image_file", bool(img_path)),
						] if sent
					]
				}
			}
			if not ok and isinstance(resp, dict) and 'attempts' in resp:
				base_resp['spreaker_attempts'] = resp['attempts']
			base_resp["episode"] = _serialize_single(ep)
			return base_resp
		except Exception as ex:
			return {"message": "Episode updated locally; remote sync error", "episode_id": str(ep.id), "error": str(ex), "episode": _serialize_single(ep)}
	return {"message": "Episode updated locally (not yet published to Spreaker)", "episode_id": str(ep.id), "episode": _serialize_single(ep)}


@router.delete("/{episode_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_episode(
	episode_id: str,
	session: Session = Depends(get_session),
	current_user: User = Depends(get_current_user),
):
	try:
		eid = _UUID(str(episode_id))
	except Exception:
		# Idempotent delete: if invalid id format, treat as no-op success
		return
	# Support both ORM User object and dict-like with 'id' (tests may inject a simple dict)
	uid = getattr(current_user, 'id', None)
	if uid is None and isinstance(current_user, dict):  # type: ignore[arg-type]
		uid = current_user.get('id')  # type: ignore[assignment]
	ep = session.exec(select(Episode).where(Episode.id == eid, Episode.user_id == uid)).first()
	if not ep:
		# Idempotent delete: if already deleted or not found for user, return 204
		return
	_svc_repo.delete_episode(session, ep)
	return
