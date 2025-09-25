from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from api.core.database import get_session
from api.core.auth import get_current_user
from api.models.user import User
from api.services.publisher import SpreakerClient
from api.core.config import settings
import requests
from sqlmodel import select
from api.models.podcast import Podcast, PodcastType, Episode
from uuid import UUID
import logging

log = logging.getLogger(__name__)

router = APIRouter(prefix="/spreaker", tags=["spreaker"])


@router.get("/shows")
def get_spreaker_shows(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Returns the authenticated user's shows from Spreaker.
    Shape: { "shows": [ { show_id, title, ... }, ... ] }
    """
    token = getattr(current_user, "spreaker_access_token", None)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Spreaker not connected")

    client = SpreakerClient(token)
    ok, result = client.get_shows()
    if not ok:
        raise HTTPException(status_code=500, detail=str(result))
    return {"shows": result}

@router.get("/analytics/plays/shows")
def get_plays_totals_for_user_shows(
    window: str = "last30d",
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Proxy to Spreaker totals endpoint for the authenticated user's shows.
    Returns shape: { window, totals: { show_id: { plays_total: int, title?: str }, ... }, raw?: ... }
    """
    token = getattr(current_user, "spreaker_access_token", None)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Spreaker not connected")
    client = SpreakerClient(token)
    user_id = client.get_user_id()
    if not user_id:
        raise HTTPException(status_code=502, detail="Failed to resolve Spreaker user id")
    # Map window to params if provider supports it; pass from/to as YYYY-MM-DD
    params = {}
    try:
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        if window.lower() in ("last30d", "last_30d", "30d"):
            since = now - timedelta(days=30)
            params = {"from": since.strftime("%Y-%m-%d"), "to": now.strftime("%Y-%m-%d")}
    except Exception:
        params = {}
    try:
        ok, data = client.get_user_shows_plays_totals(user_id, params=params)
        if not ok:
            raise HTTPException(status_code=502, detail=str(data))
        # Normalize common shapes
        # Expect either { items: [ { show_id, plays_total, ... } ] } or keyed totals
        items = []
        if isinstance(data, dict):
            items = data.get("items") or data.get("shows") or data.get("totals") or []
            if isinstance(items, dict):
                # Convert dict mapping to list
                items = [ {"show_id": k, **({"plays_total": v} if isinstance(v, (int, float)) else (v or {})) } for k, v in items.items() ]
        totals = {}
        for it in (items or []):
            sid = str(it.get("show_id")) if isinstance(it, dict) and it.get("show_id") is not None else None
            if not sid:
                continue
            pt = it.get("plays_total") or it.get("plays") or it.get("count") or it.get("play_count")
            try:
                pt = int(pt) if pt is not None else None
            except Exception:
                pt = None
            totals[sid] = {"plays_total": pt}
            title = it.get("title") or it.get("name")
            if title:
                totals[sid]["title"] = title
        return {"window": window, "totals": totals}
    except HTTPException:
        raise
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))

@router.get("/analytics/plays/shows/{show_id}/episodes")
def get_plays_totals_for_show_episodes(
    show_id: str,
    window: str = "last30d",
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Proxy to Spreaker totals endpoint for per-episode totals in a show.
    Returns shape: { window, items: [ { episode_id, plays_total, title? }, ... ] }
    """
    token = getattr(current_user, "spreaker_access_token", None)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Spreaker not connected")
    client = SpreakerClient(token)
    params = {}
    try:
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        if window.lower() in ("last30d", "last_30d", "30d"):
            since = now - timedelta(days=30)
            params = {"from": since.strftime("%Y-%m-%d"), "to": now.strftime("%Y-%m-%d")}
    except Exception:
        params = {}
    try:
        ok, data = client.get_show_episodes_plays_totals(show_id, params=params)
        if not ok:
            raise HTTPException(status_code=502, detail=str(data))
        items_in = []
        if isinstance(data, dict):
            items_in = data.get("items") or data.get("episodes") or []
        items = []
        for it in (items_in or []):
            eid = it.get("episode_id") if isinstance(it, dict) else None
            if not eid:
                continue
            pt = it.get("plays_total") or it.get("plays") or it.get("count") or it.get("play_count")
            try:
                pt = int(pt) if pt is not None else None
            except Exception:
                pt = None
            items.append({"episode_id": str(eid), "plays_total": pt, "title": it.get("title")})
        return {"window": window, "items": items}
    except HTTPException:
        raise
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))

@router.get("/analytics/plays/episodes")
def get_plays_totals_for_user_episodes(
    window: str = "last30d",
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Aggregate per-episode play totals across all of the user's Spreaker shows and map to local episode ids.
    Returns shape: { window, items: [ { episode_id, plays_total, spreaker_episode_id }, ... ] }
    """
    token = getattr(current_user, "spreaker_access_token", None)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Spreaker not connected")
    client = SpreakerClient(token)
    # Build mapping from spreaker_episode_id -> local episode_id for this user
    eps = session.exec(select(Episode).where(Episode.user_id == current_user.id).where(getattr(Episode, 'spreaker_episode_id') != None)).all()  # noqa: E711
    spk_to_local: dict[str, str] = {}
    for ep in eps:
        sid = getattr(ep, 'spreaker_episode_id', None)
        if sid:
            spk_to_local[str(sid)] = str(ep.id)
    # Find all shows for this user that have a linked spreaker_show_id
    shows = session.exec(select(Podcast).where(Podcast.user_id == current_user.id).where(getattr(Podcast, 'spreaker_show_id') != None)).all()  # noqa: E711
    items: list[dict] = []
    try:
        params = {}
        try:
            from datetime import datetime, timedelta, timezone
            now = datetime.now(timezone.utc)
            if window.lower() in ("last30d", "last_30d", "30d"):
                since = now - timedelta(days=30)
                params = {"from": since.strftime("%Y-%m-%d"), "to": now.strftime("%Y-%m-%d")}
        except Exception:
            params = {}
        for show in shows:
            sid = getattr(show, 'spreaker_show_id', None)
            if not sid:
                continue
            ok, data = client.get_show_episodes_plays_totals(str(sid), params=params)
            if not ok or not isinstance(data, dict):
                continue
            arr = data.get("items") or data.get("episodes") or []
            for it in arr:
                if not isinstance(it, dict):
                    continue
                spk_eid = str(it.get("episode_id")) if it.get("episode_id") is not None else None
                if not spk_eid:
                    continue
                pt = it.get("plays_total") or it.get("plays") or it.get("count") or it.get("play_count")
                try:
                    pt = int(pt) if pt is not None else None
                except Exception:
                    pt = None
                local_id = spk_to_local.get(spk_eid)
                if not local_id:
                    continue
                items.append({"episode_id": local_id, "plays_total": pt, "spreaker_episode_id": spk_eid})
        return {"window": window, "items": items}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/disconnect")
def spreaker_disconnect(session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    current_user.spreaker_access_token = None
    current_user.spreaker_refresh_token = None
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return {"message": "Spreaker account disconnected successfully."}

@router.get("/categories")
def get_spreaker_categories():
    """Public categories list (no auth required)."""
    try:
        r = requests.get("https://api.spreaker.com/v2/show-categories", timeout=30)
        if r.status_code // 100 != 2:
            raise HTTPException(status_code=502, detail=f"Spreaker categories error: {r.status_code}")
        data = r.json().get("response", r.json())
        return {"categories": data.get("items", data.get("categories", []))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed fetching categories: {e}")

@router.post("/refresh/{podcast_id}")
def refresh_spreaker_show(podcast_id: UUID,
                          session: Session = Depends(get_session),
                          current_user: User = Depends(get_current_user)):
    pid = podcast_id
    token = getattr(current_user, "spreaker_access_token", None)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Spreaker not connected")
    uid = current_user.id
    log.debug(f"[spreaker.refresh] pid={pid} ({type(pid)}) uid={uid} ({type(uid)})")
    pod = session.exec(select(Podcast).where(Podcast.id == pid, Podcast.user_id == uid)).first()
    if not pod or not pod.spreaker_show_id:
        raise HTTPException(status_code=404, detail="Podcast or linked Spreaker show not found")
    client = SpreakerClient(token)
    ok, resp = client.get_show(pod.spreaker_show_id)
    if not ok:
        raise HTTPException(status_code=502, detail=str(resp))
    show_obj = resp.get("show") or resp
    rss_candidate = (show_obj.get("rss_url") or show_obj.get("feed_url") or show_obj.get("xml_url"))
    # Fallback: construct canonical Spreaker feed URL if not present
    if not rss_candidate:
        sid_fallback = show_obj.get("show_id") or pod.spreaker_show_id
        if sid_fallback:
            rss_candidate = f"https://www.spreaker.com/show/{sid_fallback}/episodes/feed"
    changed = False
    if rss_candidate and not pod.rss_url_locked:
        pod.rss_url_locked = rss_candidate
        changed = True
    if rss_candidate and not pod.rss_url:
        pod.rss_url = rss_candidate
        changed = True
    if changed:
        session.add(pod)
        session.commit()
        session.refresh(pod)
    return {"podcast_id": str(pod.id), "rss_url": pod.rss_url, "rss_url_locked": pod.rss_url_locked}

@router.get("/show/{podcast_id}")
def get_remote_show(podcast_id: UUID, mapped: bool = False,
                    session: Session = Depends(get_session),
                    current_user: User = Depends(get_current_user)):
    pid = podcast_id
    token = getattr(current_user, "spreaker_access_token", None)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Spreaker not connected")
    uid = current_user.id
    log.debug(f"[spreaker.show] pid={pid} ({type(pid)}) uid={uid} ({type(uid)})")
    pod = session.exec(select(Podcast).where(Podcast.id == pid, Podcast.user_id == uid)).first()
    if not pod or not pod.spreaker_show_id:
        raise HTTPException(status_code=404, detail="Podcast or linked Spreaker show not found")
    client = SpreakerClient(token)
    ok, resp = client.get_show(pod.spreaker_show_id)
    if not ok:
        raise HTTPException(status_code=502, detail=str(resp))
    show_obj = resp.get("show") or resp
    # Provide a canonical RSS URL fallback for mapping if DB doesn't have one yet
    canonical_rss = (show_obj.get("rss_url") or show_obj.get("feed_url") or show_obj.get("xml_url"))
    if not canonical_rss:
        sid_fallback = show_obj.get("show_id") or pod.spreaker_show_id
        if sid_fallback:
            canonical_rss = f"https://www.spreaker.com/show/{sid_fallback}/episodes/feed"
    # Safe extraction of podcast_type regardless of whether stored as Enum or plain string
    pt_out = None
    if hasattr(pod, 'podcast_type'):
        raw_pt = getattr(pod, 'podcast_type')
        if isinstance(raw_pt, PodcastType):
            pt_out = raw_pt.value
        else:
            # Could already be a plain string or None
            pt_out = raw_pt or None
    try:
        mapped_obj = {
            "id": str(pod.id),
            "spreaker_show_id": pod.spreaker_show_id,
            "name": show_obj.get("title") or pod.name,
            "description": show_obj.get("description") or pod.description,
            "language": show_obj.get("language") or pod.language,
            "author_name": show_obj.get("author_name") or pod.author_name,
            "owner_name": show_obj.get("owner_name") or pod.owner_name,
            "copyright_line": show_obj.get("copyright") or pod.copyright_line,
            "category_id": show_obj.get("category_id") or pod.category_id,
            "category_2_id": show_obj.get("category_2_id") or pod.category_2_id,
            "category_3_id": show_obj.get("category_3_id") or pod.category_3_id,
            "contact_email": pod.contact_email,
            "podcast_type": pt_out,
            "rss_url_locked": pod.rss_url_locked or canonical_rss,
            "rss_url": pod.rss_url or canonical_rss,
            "cover_path": pod.cover_path,
        }
    except Exception as map_err:
        log.warning(f"[spreaker.show] mapping error pid={pod.id}: {map_err}")
        raise HTTPException(status_code=500, detail="Failed to map show metadata")
    if mapped:
        return {"mapped": mapped_obj}
    return {"show_raw": show_obj, "mapped": mapped_obj}
