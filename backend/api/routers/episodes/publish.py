import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlmodel import select

from api.core.database import get_session
from api.routers.auth import get_current_user
from api.models.user import User
from api.models.podcast import Episode, Podcast
from api.services.episodes import repo as _svc_repo
from api.services.episodes import publisher as _svc_publisher
from api.services.sms import sms_service
from uuid import UUID as _UUID

logger = logging.getLogger("ppp.episodes.publish")

router = APIRouter(tags=["episodes"])  # parent episodes router provides '/episodes' prefix


@router.post("/{episode_id}/publish", status_code=status.HTTP_200_OK)
def publish_episode_endpoint(
    episode_id: str,
    spreaker_show_id: Optional[str] = Body(None, embed=True, description="Optional explicit Spreaker show id (numeric). If omitted or invalid, will derive from the episode's podcast."),
    publish_state: str = Body(None, embed=True),  # e.g. 'unpublished' | 'public' (nullable to allow admin test-mode default)
    publish_at: Optional[str] = Body(None, embed=True, description="Optional ISO8601 datetime to schedule publication (UTC or with timezone)"),
    publish_at_local: Optional[str] = Body(None, embed=True, description="Raw local date/time string as originally chosen (no timezone conversion)."),
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

    # REQUIRE cloud storage audio path (GCS or R2)
    # Cloud storage is the sole source of truth for all media
    if not ep.gcs_audio_path:
        raise HTTPException(
            status_code=400, 
            detail="Episode has no cloud storage audio file. Episode must be properly assembled with audio uploaded to cloud storage before publishing."
        )
    
    # Accept both gs:// (GCS) and https:// (R2) URLs
    audio_path_str = str(ep.gcs_audio_path)
    if not (audio_path_str.startswith("gs://") or audio_path_str.startswith("https://")):
        raise HTTPException(
            status_code=400, 
            detail=f"Episode audio path has unexpected format: {audio_path_str[:50]}... (expected gs:// or https:// URL)"
        )

    # Spreaker integration is now OPTIONAL (legacy support only)
    spreaker_access_token = getattr(current_user, "spreaker_access_token", None)
    
    # Only attempt Spreaker validation if user has token
    derived_show_id = None
    if spreaker_access_token:
        # Derive / validate Spreaker show id
        if spreaker_show_id and spreaker_show_id.isdigit():
            derived_show_id = spreaker_show_id
        else:
            candidate_uuid = None
            if spreaker_show_id and '-' in spreaker_show_id:
                try:
                    candidate_uuid = _UUID(str(spreaker_show_id))
                except Exception:
                    candidate_uuid = None
            podcast_obj = None
            try:
                if getattr(ep, 'podcast_id', None):
                    podcast_obj = session.exec(select(Podcast).where(Podcast.id == ep.podcast_id)).first()
            except Exception:
                podcast_obj = None
            if not podcast_obj and candidate_uuid:
                podcast_obj = session.exec(select(Podcast).where(Podcast.id == candidate_uuid)).first()
            if podcast_obj and getattr(podcast_obj, 'spreaker_show_id', None):
                derived_show_id = str(podcast_obj.spreaker_show_id)
        
        # Log if Spreaker is attempted but show ID couldn't be determined
        if not derived_show_id or not derived_show_id.isdigit():
            logger.warning("publish_episode: User has Spreaker token but no valid show ID found episode_id=%s", episode_id)
    else:
        logger.info("publish_episode: Spreaker not connected, publishing RSS-only episode_id=%s", episode_id)

    # If publish_state omitted and admin test mode is on, default to draft (unpublished)
    if not publish_state:
        try:
            from api.models.settings import AppSetting as _AS
            rec = session.get(_AS, 'admin_settings')
            import json as _json
            adm = _json.loads(rec.value_json or '{}') if rec else {}
            if bool(adm.get('test_mode')):
                publish_state = 'unpublished'
        except Exception:
            pass

    description = ep.show_notes or ""

    auto_publish_iso = None
    if publish_at:
        raw_publish_at = str(publish_at).strip()
        import re as _re
        dt = None
        logger.debug("publish_episode: raw_publish_at=%s episode_id=%s", raw_publish_at, episode_id)
        if _re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$', raw_publish_at):
            try:
                from datetime import datetime as _dt, timezone as _tz
                y=int(raw_publish_at[0:4]); mo=int(raw_publish_at[5:7]); d=int(raw_publish_at[8:10]);
                h=int(raw_publish_at[11:13]); mi=int(raw_publish_at[14:16]); s=int(raw_publish_at[17:19]);
                dt=_dt(y,mo,d,h,mi,s,tzinfo=_tz.utc)
            except Exception as ex:
                try:
                    from datetime import datetime as _dt, timezone as _tz
                    dt = _dt.strptime(raw_publish_at, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=_tz.utc)
                except Exception:
                    dt = None
        if dt is None:
            norm = raw_publish_at
            try:
                if ' ' in norm and 'T' not in norm.split(' ')[0] and _re.match(r'^\d{4}-\d{2}-\d{2} ', norm):
                    norm = norm.replace(' ', 'T', 1)
                if _re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$', norm):
                    norm += ':00'
                if _re.match(r'.*[+-]\d{4}$', norm):
                    norm = norm[:-5] + norm[-5:-2] + ':' + norm[-2:]
                dt = datetime.fromisoformat(norm)
            except Exception:
                dt = None
        if dt is None and len(raw_publish_at) == 10 and raw_publish_at.count('-') == 2:
            try:
                from datetime import datetime as _dt
                dt = _dt.strptime(raw_publish_at, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            except Exception:
                dt = None
        if dt is None:
            logger.warning("publish_episode: invalid publish_at input=%s episode_id=%s", raw_publish_at, episode_id)
            raise HTTPException(status_code=400, detail=f"Invalid publish_at format; use ISO8601 (got: {raw_publish_at!r})")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if dt <= now:
            logger.warning("publish_episode: publish_at not future dt=%s now=%s episode_id=%s", dt.isoformat(), now.isoformat(), episode_id)
            raise HTTPException(status_code=400, detail="publish_at must be in the future (UTC)")
        ep.publish_at = dt.astimezone(timezone.utc)
        if publish_at_local:
            ep.publish_at_local = publish_at_local
        session.add(ep)
        session.commit()
        auto_publish_iso = dt.astimezone(timezone.utc).isoformat()

    async_result = _svc_publisher.publish(
        session=session,
        current_user=current_user,
        episode_id=eid,
        derived_show_id=str(derived_show_id) if derived_show_id else None,
        publish_state=publish_state,
        auto_publish_iso=auto_publish_iso,
    )
    if not auto_publish_iso and not getattr(ep, 'publish_at', None):
        try:
            ep.publish_at = datetime.now(timezone.utc)
            session.add(ep)
            session.commit()
        except Exception:
            session.rollback()
    
    # Refresh episode to get latest state
    session.refresh(ep)
    _pa = getattr(ep, 'publish_at', None)
    
    # Send SMS notification if user has opted in (for Spreaker path, RSS path handles it in service)
    # Only send if not already sent in RSS path
    if derived_show_id:  # Spreaker path
        try:
            user = session.get(User, current_user.id)
            # Use getattr() to safely access SMS fields (may not exist if migration hasn't run)
            sms_enabled = getattr(user, 'sms_notifications_enabled', False) if user else False
            sms_publish = getattr(user, 'sms_notify_publish', False) if user else False
            phone_number = getattr(user, 'phone_number', None) if user else None
            
            if user and sms_enabled and sms_publish and phone_number:
                episode_name = ep.title or "Untitled Episode"
                publish_date = _pa if _pa else datetime.now(timezone.utc)
                sms_service.send_publish_notification(
                    phone_number=phone_number,
                    episode_name=episode_name,
                    publish_date=publish_date,
                    user_id=str(user.id)
                )
                logger.info("[publish] SMS notification sent to user %s for episode %s (Spreaker)", user.id, episode_name)
        except Exception as sms_err:
            # Don't fail the publish if SMS fails (or if columns don't exist yet)
            logger.warning("[publish] SMS notification failed for user %s: %s", current_user.id, sms_err, exc_info=True)
    
    return {
        "message": "Publish scheduled with Spreaker" if auto_publish_iso else "Publish request submitted to Spreaker.",
        "job_id": async_result["job_id"],
        "scheduled_for": auto_publish_iso,
        "spreaker_show_id": derived_show_id,
        "publish_at": (_pa.astimezone(timezone.utc).isoformat().replace('+00:00','Z') if _pa else None),
    }


@router.post("/{episode_id}/unpublish", status_code=200)
def unpublish_episode(
    episode_id: str,
    force: bool = Body(False, embed=True, description="Force unpublish even if outside retention window"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    try:
        eid = _UUID(str(episode_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Episode not found")
    return _svc_publisher.unpublish(session=session, current_user=current_user, episode_id=eid, force=force)


@router.post("/{episode_id}/republish", status_code=status.HTTP_200_OK)
def republish_episode_endpoint(
    episode_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    try:
        eid = _UUID(str(episode_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Episode not found")
    resp = _svc_publisher.republish(session=session, current_user=current_user, episode_id=eid)
    return {"message": "Republish requested", **resp}


@router.post("/{episode_id}/publish/refresh", status_code=200)
def publish_refresh(
    episode_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    try:
        eid = _UUID(str(episode_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Episode not found")
    return _svc_publisher.refresh_remote(session=session, current_user=current_user, episode_id=eid)
