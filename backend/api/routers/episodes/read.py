import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Body, status, Query
from sqlalchemy.orm import Session
from sqlmodel import select
from sqlalchemy import func

from api.core.database import get_session
from api.routers.auth import get_current_user
from api.models.user import User
from api.models.podcast import Episode, Podcast, EpisodeStatus

from api.services.episodes import jobs as _svc_jobs
from .common import _final_url_for, _cover_url_for, _status_value
from api.services.episodes import repo as _svc_repo
from api.services.episodes.transcripts import transcript_endpoints_for_episode
from uuid import UUID as _UUID
from pathlib import Path
from api.core.paths import FINAL_DIR, MEDIA_DIR, APP_ROOT

logger = logging.getLogger("ppp.episodes.read")

# Note: this router is nested under the parent episodes router to avoid double '/episodes' prefix.
router = APIRouter(tags=["episodes"])  # parent provides prefix '/episodes'

# Avoid importing app main (would cause circular import). Derive project root relative to this file.
PROJECT_ROOT = APP_ROOT


def _set_status(ep: Episode, status_str: str) -> None:
	try:
		from api.models.podcast import EpisodeStatus as _EpisodeStatus  # optional enum
		try:
			enum_val = getattr(_EpisodeStatus, status_str)
		except Exception:
			try:
				enum_val = _EpisodeStatus[status_str]
			except Exception:
				enum_val = _EpisodeStatus(status_str)
		ep.status = enum_val  # type: ignore[assignment]
	except Exception:
		try:
			setattr(ep, 'status', status_str)
		except Exception:
			pass


# --- read endpoints ---------------------------------------------------------

## moved: GET /episodes/status/{job_id} is now defined in episodes_jobs.py


@router.get("/last/numbering", status_code=200)
def get_last_numbering(
	podcast_id: Optional[str] = Query(None, description="Optional podcast UUID to scope numbering"),
	session: Session = Depends(get_session),
	current_user: User = Depends(get_current_user),
):
	try:
		from sqlalchemy import text as _sa_text
		import re

		def _parse_numbers_from_title(title: str) -> tuple[int | None, int | None]:
			if not title:
				return (None, None)
			t = str(title)
			# Combined S/E patterns first (S2E187, S2 E187, Season 2 Episode 187)
			patterns = [
				r"\bS(?:eason)?\s*(\d+)\s*(?:,|-|\s)*\s*E(?:p(?:isode)?)?\.?\s*(\d+)\b",
				r"\bSeason\s*(\d+)\s*(?:,|-|\s)*\s*Episode\s*(\d+)\b",
			]
			for pat in patterns:
				m = re.search(pat, t, flags=re.IGNORECASE)
				if m:
					try:
						return (int(m.group(1)), int(m.group(2)))
					except Exception:
						pass
			# Separate captures (Episode N), (Season N)
			se_m = re.search(r"\bSeason\s*(\d+)\b", t, flags=re.IGNORECASE)
			ep_m = re.search(r"\b(?:Ep|Episode)\.?\s*(\d+)\b", t, flags=re.IGNORECASE)
			s_val = int(se_m.group(1)) if se_m else None
			e_val = int(ep_m.group(1)) if ep_m else None
			return (s_val, e_val)

		# Base query for this user (and optional podcast scope)
		q = select(Episode).where(Episode.user_id == current_user.id)
		if podcast_id:
			try:
				from uuid import UUID as _UUID
				pid = _UUID(str(podcast_id))
				q = q.where(Episode.podcast_id == pid)
			except Exception:
				pass

		# Pass 1: prefer rows with explicit season/episode set; choose highest season then episode
		eps = session.execute(
			q.order_by(
				_sa_text("season_number DESC"),
				_sa_text("episode_number DESC"),
				_sa_text("created_at DESC"),
			).limit(200)
		).scalars().all()
		latest_season = None
		latest_episode = None
		for e in eps:
			if e.season_number is None or e.episode_number is None:
				continue
			if latest_season is None:
				latest_season = e.season_number
				latest_episode = e.episode_number
			elif e.season_number > latest_season:
				latest_season = e.season_number
				latest_episode = e.episode_number
			elif e.season_number == latest_season and latest_episode is not None and e.episode_number > latest_episode:
				latest_episode = e.episode_number
		if latest_season is not None and latest_episode is not None:
			return {"season_number": latest_season, "episode_number": latest_episode}

		# Pass 2: fallback - parse from recent titles (covers imported episodes)
		eps_recent = session.execute(
			q.order_by(
				_sa_text("COALESCE(source_published_at, created_at) DESC"),
			).limit(300)
		).scalars().all()
		cand_s = None
		cand_e = None
		for e in eps_recent:
			s_val, e_val = _parse_numbers_from_title(getattr(e, 'title', '') or '')
			if s_val is not None and e_val is not None:
				cand_s, cand_e = s_val, e_val
				break
			# If only episode parsed, keep as candidate while searching for season in others
			if e_val is not None and cand_e is None:
				cand_e = e_val
		if cand_s is None and cand_e is not None:
			# Derive season from any explicit season on episodes, else default 1
			for e in eps:
				if e.season_number is not None:
					cand_s = int(e.season_number)
					break
			if cand_s is None:
				cand_s = 1
		if cand_s is not None and cand_e is not None:
			return {"season_number": cand_s, "episode_number": cand_e}

		# Nothing found
		return {"season_number": None, "episode_number": None}
	except Exception:
		return {"season_number": None, "episode_number": None}


@router.get("/{episode_id}/spreaker/raw", status_code=200)
def get_spreaker_episode_raw(
	episode_id: str,
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
	spreaker_id = getattr(ep, 'spreaker_episode_id', None)
	if not spreaker_id:
		raise HTTPException(status_code=400, detail="Episode not linked to Spreaker")
	token = getattr(current_user, 'spreaker_access_token', None)
	if not token:
		raise HTTPException(status_code=401, detail="User not connected to Spreaker")
	try:
		from api.services.publisher import SpreakerClient
		client = SpreakerClient(token)
		ok, resp = client.get_episode(spreaker_id)
		if not ok:
			raise HTTPException(status_code=502, detail=f"Spreaker fetch failed: {resp}")
		return {"spreaker_episode_id": spreaker_id, "spreaker_raw": resp}
	except HTTPException:
		raise
	except Exception as ex:
		raise HTTPException(status_code=500, detail=str(ex))


@router.get("/{episode_id}/spreaker/diff", status_code=200)
def diff_spreaker_episode(
	episode_id: str,
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
	spreaker_id = getattr(ep, 'spreaker_episode_id', None)
	if not spreaker_id:
		raise HTTPException(status_code=400, detail="Episode not linked to Spreaker")
	token = getattr(current_user, 'spreaker_access_token', None)
	if not token:
		raise HTTPException(status_code=401, detail="User not connected to Spreaker")
	try:
		from api.services.publisher import SpreakerClient
		client = SpreakerClient(token)
		ok, resp = client.get_episode(spreaker_id)
		if not ok:
			raise HTTPException(status_code=502, detail=f"Spreaker fetch failed: {resp}")
		remote = resp.get('episode') if isinstance(resp, dict) and 'episode' in resp else resp
		if not isinstance(remote, dict):
			raise HTTPException(status_code=502, detail="Unexpected remote response shape")
		diffs = {}
		checks = [
			('title', ep.title, remote.get('title')),
			('description', getattr(ep, 'show_notes', None), remote.get('description')),
			('visibility', None, remote.get('visibility')),
			('image_url', getattr(ep, 'remote_cover_url', None), remote.get('image_url')),
		]
		for field, local_val, remote_val in checks:
			if (local_val or '') != (remote_val or ''):
				diffs[field] = {'local': local_val, 'remote': remote_val}
		return {
			'episode_id': str(ep.id),
			'spreaker_episode_id': spreaker_id,
			'diffs': diffs,
			'remote_visibility': remote.get('visibility'),
			'remote_updated_at': remote.get('updated_at'),
		}
	except HTTPException:
		raise
	except Exception as ex:
		raise HTTPException(status_code=500, detail=str(ex))


@router.get("/{episode_id}/publish/status", status_code=200)
def publish_status(
	episode_id: str,
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
	final_audio_exists = False
	if getattr(ep, 'final_audio_path', None):
		base = os.path.basename(str(ep.final_audio_path))
		candidates = []
		try:
			candidates.append((FINAL_DIR / base).resolve())
		except Exception:
			candidates.append(FINAL_DIR / base)
		candidates.append(MEDIA_DIR / base)
		final_audio_exists = any(c.is_file() for c in candidates)
	_pa = getattr(ep, 'publish_at', None)
	return {
		'episode_id': str(ep.id),
		'status': _status_value(ep.status),
		'spreaker_episode_id': getattr(ep, 'spreaker_episode_id', None),
		'final_audio': {'path': getattr(ep, 'final_audio_path', None), 'exists': final_audio_exists},
		'publish_at': (_pa.astimezone(timezone.utc).isoformat().replace('+00:00','Z') if _pa else None),
		'last_error': getattr(ep, 'spreaker_publish_error', None),
		'last_error_detail': getattr(ep, 'spreaker_publish_error_detail', None),
		'needs_republish': getattr(ep, 'needs_republish', False),
		'remote_cover_url': getattr(ep, 'remote_cover_url', None),
	}


@router.get("/", status_code=status.HTTP_200_OK)
def list_episodes(
	session: Session = Depends(get_session),
	current_user: User = Depends(get_current_user),
	limit: int = Query(100, ge=1, le=1000, description="Max episodes to return"),
	offset: int = Query(0, ge=0, description="Offset for pagination"),
):
	# total count (avoid direct Episode.id reference for analyzer compatibility)
	try:
		# Ensure we get a plain integer, not a Row object
		total = session.execute(
			select(func.count()).select_from(Episode).where(Episode.user_id == current_user.id)
		).scalar_one()
	except Exception:
		total = 0
	try:
		from sqlalchemy import text as _sa_text
		eps = session.execute(
			select(Episode)
			.where(Episode.user_id == current_user.id)
			.order_by(_sa_text("publish_at DESC"), _sa_text("processed_at DESC"), _sa_text("created_at DESC"), _sa_text("id DESC"))
			.offset(offset)
			.limit(limit)
		).scalars().all()
	except Exception:
		from sqlalchemy import text as _sa_text
		eps = session.execute(
			select(Episode)
			.where(Episode.user_id == current_user.id)
			.order_by(_sa_text("processed_at DESC"))
			.offset(offset)
			.limit(limit)
		).scalars().all()
	items = []
	now_utc = datetime.utcnow()
	for e in eps:
		final_exists = False
		cover_exists = False
		try:
			if e.final_audio_path:
				base = os.path.basename(str(e.final_audio_path))
				cands = []
				try:
					cands.append((FINAL_DIR / base).resolve())
				except Exception:
					cands.append(FINAL_DIR / base)
				cands.append(MEDIA_DIR / base)
				final_exists = any(c.is_file() for c in cands)
			if getattr(e, 'remote_cover_url', None):
				cover_exists = True
			else:
				if e.cover_path and not str(e.cover_path).lower().startswith(('http://', 'https://')):
					try:
						candidate = (MEDIA_DIR / os.path.basename(str(e.cover_path))).resolve()
					except Exception:
						candidate = MEDIA_DIR / os.path.basename(str(e.cover_path))
					cover_exists = candidate.is_file()
				elif e.cover_path:
					cover_exists = True
		except Exception:
			pass

		base_status = _status_value(e.status)
		is_scheduled = False
		if e.publish_at and base_status != "published":
			if e.publish_at > now_utc:
				is_scheduled = True
				derived_status = "scheduled"
			else:
				derived_status = "published"
				try:
					_set_status(e, "published")
					e.is_published_to_spreaker = True
					session.add(e)
				except Exception:
					pass
		else:
			derived_status = base_status

		# Prefer local cover_path first so newly uploaded covers display immediately;
		# remote_cover_url will override later once publish sync updates it.
		preferred_cover = e.cover_path or getattr(e, 'remote_cover_url', None)
		stream_url = None
		try:
			spk_id = getattr(e, 'spreaker_episode_id', None)
			if spk_id:
				stream_url = f"https://api.spreaker.com/v2/episodes/{spk_id}/play"
		except Exception:
			stream_url = None
		final_audio_url = _final_url_for(e.final_audio_path)
		if not final_exists:
			final_audio_url = None
		playback_url = stream_url or final_audio_url
		playback_type = 'stream' if stream_url else ('local' if final_audio_url else 'none')
		if playback_type == 'stream':
			final_exists = True

		pub_at_iso = None
		pub_local_raw = getattr(e, 'publish_at_local', None)
		try:
			pub_dt = getattr(e, 'publish_at', None)
			if pub_dt:
				if pub_dt.tzinfo is None or pub_dt.tzinfo.utcoffset(pub_dt) is None:
					pub_dt = pub_dt.replace(tzinfo=timezone.utc)
				pub_at_iso = pub_dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
		except Exception:
			pub_at_iso = None

		try:
			transcript_info = transcript_endpoints_for_episode(e)
		except Exception:
			transcript_info = {
				"available": False,
				"json": None,
				"text": None,
				"absolute_json": None,
				"absolute_text": None,
			}
		items.append({
			"id": str(e.id),
			"podcast_id": getattr(e, 'podcast_id', None),
			"title": e.title,
			"status": derived_status,
			"processed_at": e.processed_at.isoformat() if getattr(e, "processed_at", None) else None,
			"duration_ms": getattr(e, 'duration_ms', None),
			"final_audio_url": final_audio_url,
			"cover_url": _cover_url_for(preferred_cover),
			"description": getattr(e, "show_notes", None) or "",
			"tags": getattr(e, 'tags', lambda: [])(),
			"is_explicit": bool(getattr(e, 'is_explicit', False)),
			"image_crop": getattr(e, 'image_crop', None),
			"season_number": getattr(e, 'season_number', None),
			"episode_number": getattr(e, 'episode_number', None),
			"spreaker_episode_id": getattr(e, "spreaker_episode_id", None),
			"is_published_to_spreaker": bool(getattr(e, "is_published_to_spreaker", False)),
			"final_audio_exists": final_exists,
			"cover_exists": cover_exists,
			"cover_path": preferred_cover,
			"final_audio_basename": os.path.basename(e.final_audio_path) if e.final_audio_path else None,
			"publish_error": getattr(e, 'spreaker_publish_error', None),
			"publish_error_detail": getattr(e, 'spreaker_publish_error_detail', None),
			"needs_republish": bool(getattr(e, 'needs_republish', False)),
			"publish_at": pub_at_iso,
			"publish_at_local": pub_local_raw,
			"is_scheduled": is_scheduled,
			"plays_total": None,
			"stream_url": stream_url,
			"playback_url": playback_url,
			"playback_type": playback_type,
			"has_transcript": bool(transcript_info.get("available", False)),
			"transcript_url": transcript_info.get("text"),
			"transcript_json_url": transcript_info.get("json"),
		})

	try:
		session.commit()
	except Exception:
		session.rollback()
	return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/summary", status_code=200)
def episodes_summary(
	podcast_id: Optional[str] = Query(None, description="Filter by podcast id (UUID)"),
	session: Session = Depends(get_session),
	current_user: User = Depends(get_current_user),
):
	"""Return small counters for episodes owned by the user (optionally for a podcast).

	Response: { total, unpublished_or_unscheduled }
	- unpublished_or_unscheduled counts episodes that are not published yet OR have a future publish_at.
	"""
	from uuid import UUID as _UUID
	try:
		q = select(Episode).where(Episode.user_id == current_user.id)
		if podcast_id:
			pid = _UUID(str(podcast_id))
			q = q.where(Episode.podcast_id == pid)
		eps = session.execute(q).scalars().all()
	except Exception:
		eps = []
	total = len(eps)
	from datetime import datetime, timezone
	now = datetime.now(timezone.utc)
	def _status_val(s):
		try:
			return s.value if hasattr(s, 'value') else str(s)
		except Exception:
			return str(s)
	unpub = 0
	for e in eps:
		st = _status_val(getattr(e, 'status', None))
		pub_at = getattr(e, 'publish_at', None)
		is_future = False
		try:
			if pub_at and (pub_at.tzinfo is None or pub_at.tzinfo.utcoffset(pub_at) is None):
				pub_at = pub_at.replace(tzinfo=timezone.utc)
			is_future = bool(pub_at and pub_at > now)
		except Exception:
			is_future = False
		if st != 'published' or is_future:
			unpub += 1
	return {"total": total, "unpublished_or_unscheduled": unpub}


@router.get("/{episode_id}/diagnostics", status_code=200)
def episode_diagnostics(
	episode_id: str,
	session: Session = Depends(get_session),
	current_user: User = Depends(get_current_user),
):
	import uuid as _uuid
	try:
		eid = _uuid.UUID(str(episode_id))
	except Exception:
		raise HTTPException(status_code=404, detail="Episode not found")
	ep = session.execute(select(Episode).where(Episode.id == eid, Episode.user_id == current_user.id)).scalars().first()
	if not ep:
		raise HTTPException(status_code=404, detail="Episode not found")
	final_path = ep.final_audio_path
	cover_path = ep.cover_path
	final_exists = False
	try:
		if final_path:
			# Accept absolute, relative, or basename under FINAL_DIR
			p = Path(final_path)
			final_exists = p.is_file() or (FINAL_DIR / p.name).is_file()
	except Exception:
		final_exists = False
	cover_candidates = []
	if cover_path:
		try:
			base = os.path.basename(cover_path)
		except Exception:
			base = str(cover_path)
		cover_candidates = [
			cover_path,
			str((MEDIA_DIR / base).resolve()),
		]
	cover_exists = any(os.path.isfile(c) for c in cover_candidates)
	return {
		"id": str(ep.id),
		"final_audio_path": final_path,
		"final_audio_url": _final_url_for(final_path),
		"final_audio_exists": final_exists,
		"cover_path": cover_path,
		"cover_url": _cover_url_for(cover_path),
		"cover_exists": cover_exists,
		"cover_candidates": cover_candidates,
	"cwd": str(APP_ROOT.parent),
	}


@router.get("/{episode_id}/assembly-log", status_code=200)
def get_assembly_log(
	episode_id: str,
	session: Session = Depends(get_session),
	current_user: User = Depends(get_current_user),
):
	try:
		eid = _UUID(str(episode_id))
	except Exception:
		raise HTTPException(status_code=404, detail="Episode not found")
	ep = session.execute(select(Episode).where(Episode.id == eid, Episode.user_id == current_user.id)).scalars().first()
	if not ep:
		raise HTTPException(status_code=404, detail="Episode not found")
	log_path = PROJECT_ROOT / "assembly_logs" / f"{ep.id}.log"
	if not log_path.is_file():
		raise HTTPException(status_code=404, detail="Assembly log not found")
	try:
		with open(log_path, "r", encoding="utf-8") as fh:
			lines = fh.readlines()[:500]
		return {"episode_id": str(ep.id), "log": [l.rstrip("\n") for l in lines]}
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Failed to read log: {e}")


@router.get("/lookup/by-spreaker/{spreaker_episode_id}", status_code=200)
def lookup_episode_by_spreaker(
	spreaker_episode_id: str,
	session: Session = Depends(get_session),
	current_user: User = Depends(get_current_user),
):
	ep = session.execute(
		select(Episode)
		.where(Episode.user_id == current_user.id)
		.where(getattr(Episode, 'spreaker_episode_id') == spreaker_episode_id)
	).scalars().first()
	if not ep:
		raise HTTPException(status_code=404, detail="Episode with that Spreaker ID not found for user")
	_pa = getattr(ep, 'publish_at', None)
	return {
		"id": str(ep.id),
		"title": ep.title,
		"status": _status_value(ep.status),
		"spreaker_episode_id": getattr(ep, 'spreaker_episode_id', None),
		"publish_at": (_pa.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z') if _pa else None),
		"processed_at": ep.processed_at.isoformat() if getattr(ep, 'processed_at', None) else None,
		"created_at": ep.created_at.isoformat() if getattr(ep, 'created_at', None) else None,
	}


@router.get("/admin/missing-spreaker-ids", status_code=200)
def list_missing_spreaker_ids(
	session: Session = Depends(get_session),
	current_user: User = Depends(get_current_user),
):
	from sqlalchemy import or_, desc as _desc
	q = (
		select(Episode)
		.where(Episode.user_id == current_user.id)
		.where(or_(getattr(Episode, 'spreaker_episode_id') == None, getattr(Episode, 'spreaker_episode_id') == ""))  # noqa: E711
		.order_by(_desc(getattr(Episode, 'processed_at')))
	)
	rows = session.execute(q).scalars().all()
	items = []
	for e in rows:
		_pa = getattr(e, 'publish_at', None)
		items.append({
			"id": str(e.id),
			"title": e.title,
			"processed_at": e.processed_at.isoformat() if getattr(e, 'processed_at', None) else None,
			"publish_at": (_pa.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z') if _pa else None),
		})
	return {"count": len(items), "items": items}

