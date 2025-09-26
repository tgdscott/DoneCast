from fastapi import APIRouter, Depends, HTTPException, status, Form, File, UploadFile, Request, Body
from typing import Optional
from uuid import UUID, uuid4
from pathlib import Path
import shutil
import logging
from typing import List, Optional
from uuid import UUID, uuid4
from sqlmodel import Session, select, SQLModel
import shutil
from pathlib import Path
import logging

from ..core.database import get_session
from ..models.user import User
from ..models.podcast import Podcast, PodcastBase, PodcastType, Episode, EpisodeStatus
from ..services.publisher import SpreakerClient
from ..services.image_utils import ensure_cover_image_constraints
from api.core.auth import get_current_user
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
from sqlmodel import Session, select

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/podcasts",
    tags=["Podcasts (Shows)"],
)

from api.core.paths import MEDIA_DIR
UPLOAD_DIRECTORY = MEDIA_DIR
UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)


class PodcastUpdate(SQLModel):
    # All fields optional for partial updates
    name: Optional[str] = None
    description: Optional[str] = None
    cover_path: Optional[str] = None
    podcast_type: Optional[PodcastType] = None
    language: Optional[str] = None
    copyright_line: Optional[str] = None
    owner_name: Optional[str] = None
    author_name: Optional[str] = None
    spreaker_show_id: Optional[str] = None
    contact_email: Optional[str] = None
    category_id: Optional[int] = None
    category_2_id: Optional[int] = None
    category_3_id: Optional[int] = None


@router.post("/{podcast_id}/link-spreaker-episodes", status_code=200)
async def link_imported_to_spreaker(
    podcast_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Link existing local episodes (e.g., imported via RSS) to Spreaker episodes for playback.
    - Requires the podcast to have a spreaker_show_id and user to be connected to Spreaker.
    - Heuristic match by normalized title and publish date (day).
    - Updates spreaker_episode_id and prefers remote stream_url for playback when available.
    Returns: { mapped: int, total_candidates: int }
    """
    # Validate podcast and auth
    pod = session.exec(select(Podcast).where(Podcast.id == podcast_id, Podcast.user_id == current_user.id)).first()
    if not pod:
        raise HTTPException(status_code=404, detail="Podcast not found.")
    if not pod.spreaker_show_id or not getattr(current_user, 'spreaker_access_token', None):
        raise HTTPException(status_code=400, detail="Podcast not linked to Spreaker or user not connected.")

    token_str: str = str(current_user.spreaker_access_token)
    client = SpreakerClient(api_token=token_str)
    ok, spk_data = client.get_all_episodes_for_show(str(pod.spreaker_show_id))
    if not ok or not isinstance(spk_data, dict):
        raise HTTPException(status_code=502, detail="Failed to fetch episodes from Spreaker.")
    spk_items = spk_data.get("items", []) or []

    # Load local episodes lacking spreaker_episode_id
    local_eps = session.exec(
        select(Episode).where(Episode.podcast_id == pod.id, Episode.user_id == current_user.id)
    ).all()
    # Build index by (normalized_title, date_key)
    from datetime import datetime, timezone
    def norm_title(t: str | None) -> str:
        try:
            return (t or '').strip().lower()
        except Exception:
            return ''
    def date_key(dt: datetime | None) -> str:
        try:
            return dt.date().isoformat() if dt else ''
        except Exception:
            return ''
    local_index: dict[tuple[str, str], Episode] = {}
    for le in local_eps:
        if getattr(le, 'spreaker_episode_id', None):
            continue
        local_index[(norm_title(le.title), date_key(getattr(le, 'publish_at', None)))] = le

    mapped = 0
    total_candidates = len(local_index)
    for it in spk_items:
        if not isinstance(it, dict):
            continue
        spk_title = it.get('title') or ''
        spk_id = str(it.get('episode_id')) if it.get('episode_id') is not None else None
        pub_dt = None
        pub_str = it.get('published_at')
        if pub_str:
            try:
                pub_dt = datetime.strptime(pub_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                pub_dt = None
        key = (norm_title(spk_title), date_key(pub_dt))
        cand = local_index.get(key)
        if cand and not getattr(cand, 'spreaker_episode_id', None) and spk_id:
            cand.spreaker_episode_id = spk_id
            # Prefer remote stream URL if local final path missing
            if not getattr(cand, 'final_audio_path', None):
                cand.final_audio_path = it.get('stream_url') or it.get('download_url')
            # If we recovered a publish date, persist and potentially set status
            if pub_dt:
                try:
                    cand.publish_at = cand.publish_at or pub_dt
                    if pub_dt <= datetime.now(timezone.utc):
                        cand.status = EpisodeStatus.published
                except Exception:
                    pass
            session.add(cand)
            mapped += 1

    if mapped:
        session.commit()
    return {"mapped": mapped, "total_candidates": total_candidates}


@router.post("/{podcast_id}/publish-all", status_code=200)
async def publish_all_to_spreaker(
    podcast_id: UUID,
    publish_state: Optional[str] = Body("public", embed=True),
    include_already_linked: bool = Body(False, embed=True, description="If true, will also republish episodes that already have a spreaker_episode_id"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Batch-publish all episodes for this podcast to Spreaker using existing mirrored audio.
    Requires the podcast to have a numeric spreaker_show_id and the user to be connected to Spreaker.
    Returns counters and job ids are not tracked here (jobs are enqueued per-episode).
    """
    pod = session.exec(select(Podcast).where(Podcast.id == podcast_id, Podcast.user_id == current_user.id)).first()
    if not pod:
        raise HTTPException(status_code=404, detail="Podcast not found.")
    if not getattr(current_user, 'spreaker_access_token', None):
        raise HTTPException(status_code=401, detail="User is not connected to Spreaker.")
    sid = getattr(pod, 'spreaker_show_id', None)
    if not sid or not str(sid).isdigit():
        raise HTTPException(status_code=400, detail="Podcast must have a numeric spreaker_show_id.")

    # Select candidates
    eps = session.exec(select(Episode).where(Episode.podcast_id == pod.id, Episode.user_id == current_user.id)).all()
    started = 0
    skipped_no_audio = 0
    skipped_already_linked = 0
    errors = 0
    from api.services.episodes import publisher as _ep_pub
    for ep in eps:
        if not getattr(ep, 'final_audio_path', None):
            skipped_no_audio += 1
            continue
        if getattr(ep, 'spreaker_episode_id', None) and not include_already_linked:
            skipped_already_linked += 1
            continue
        try:
            _ = _ep_pub.publish(
                session=session,
                current_user=current_user,
                episode_id=ep.id,
                derived_show_id=str(sid),
                publish_state=publish_state,
                auto_publish_iso=None,
            )
            started += 1
        except Exception:
            errors += 1
    return {
        "message": "Batch publish enqueued",
        "show_id": str(sid),
        "started": started,
        "skipped_no_audio": skipped_no_audio,
        "skipped_already_linked": skipped_already_linked,
        "errors": errors,
        "total": len(eps),
    }


@router.post("/", response_model=Podcast, status_code=status.HTTP_201_CREATED)
async def create_podcast(
    name: str = Form(...),
    description: str = Form(...),
    cover_image: Optional[UploadFile] = File(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    log.info("--- Starting a new podcast creation process ---")
    log.info(f"Received request to create podcast with name: '{name}'")

    spreaker_show_id = None
    if current_user.spreaker_access_token:
        log.info("User has a Spreaker access token. Proceeding to create show on Spreaker.")
        client = SpreakerClient(api_token=current_user.spreaker_access_token)
        
        log.info(f"Calling SpreakerClient.create_show with title: '{name}'")
        success, result = client.create_show(title=name, description=description, language="en")
        
        if not success:
            log.error(f"Spreaker API call failed. Result: {result}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create show on Spreaker: {result}"
            )
        
        log.info(f"Spreaker API call successful. Result: {result}")
        spreaker_show_id = result.get("show_id")
        
        if not spreaker_show_id:
            log.error("Spreaker created the show but did not return a valid show_id.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Spreaker created the show but did not return a valid ID."
            )
        log.info(f"Successfully obtained Spreaker Show ID: {spreaker_show_id}")
    else:
        log.warning("User does not have a Spreaker access token. Skipping Spreaker show creation.")

    log.info("Creating podcast in local database.")
    db_podcast = Podcast(
        name=name,
        description=description,
        spreaker_show_id=spreaker_show_id,
        user_id=current_user.id
    )

    # If we created a Spreaker show, attempt to fetch its RSS URL immediately.
    if spreaker_show_id and current_user.spreaker_access_token:
        try:
            ok_show, resp_show = client.get_show(spreaker_show_id)
            if ok_show:
                show_obj = resp_show.get("show") or resp_show
                rss_candidate = (
                    show_obj.get("rss_url")
                    or show_obj.get("feed_url")
                    or show_obj.get("xml_url")
                )
                if rss_candidate:
                    db_podcast.rss_url = db_podcast.rss_url or rss_candidate
                    if not getattr(db_podcast, 'rss_url_locked', None):
                        db_podcast.rss_url_locked = rss_candidate
        except Exception as e:
            log.warning(f"Failed to fetch show RSS after creation: {e}")

    if cover_image and cover_image.filename:
        log.info(f"Cover image provided: '{cover_image.filename}'. Processing file.")
        # Validate content type and extension
        ct = (getattr(cover_image, 'content_type', '') or '').lower()
        if not ct.startswith('image/'):
            raise HTTPException(status_code=400, detail=f"Invalid cover content type '{ct or 'unknown'}'. Expected image.")
        ext = Path(cover_image.filename).suffix.lower()
        if ext not in {'.png', '.jpg', '.jpeg'}:
            raise HTTPException(status_code=400, detail="Unsupported cover image extension. Allowed: .png, .jpg, .jpeg")

        # Sanitize original name
        import re
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(cover_image.filename).name).strip("._") or "cover"
        file_extension = Path(safe_name).suffix
        unique_filename = f"{current_user.id}_{uuid4()}{file_extension}"
        save_path = UPLOAD_DIRECTORY / unique_filename

        # Stream copy with 10MB cap
        MB = 1024 * 1024
        max_bytes = 10 * MB
        total = 0
        try:
            with save_path.open("wb") as buffer:
                while True:
                    chunk = cover_image.file.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        try:
                            save_path.unlink(missing_ok=True)  # type: ignore[arg-type]
                        except Exception:
                            pass
                        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Cover image exceeds 10 MB limit.")
                    buffer.write(chunk)
            # Store only basename for consistency (URL construction handled elsewhere)
            db_podcast.cover_path = unique_filename  # legacy field; prefer remote_cover_url after upload
            log.info(f"Successfully saved cover image to: {save_path}")

            if spreaker_show_id:
                log.info(f"Uploading cover art to Spreaker for show ID: {spreaker_show_id}")
                ok_img, resp_img = client.update_show_image(show_id=spreaker_show_id, image_file_path=str(save_path))
                if ok_img and isinstance(resp_img, dict):
                    show_obj = resp_img.get('show') or resp_img
                    # Try to capture remote cover URL if returned
                    for k in ('image_url','cover_url','cover_art_url','image'):  # heuristic keys
                        if isinstance(show_obj, dict) and show_obj.get(k):
                            db_podcast.remote_cover_url = show_obj.get(k)
                            break
                elif not ok_img:
                    log.warning(f"Spreaker cover upload failed: {resp_img}")

        except HTTPException:
            raise
        except Exception as e:
            log.error(f"Failed to save or upload cover image: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save or upload cover image: {e}")
    else:
        log.info("No cover image was provided.")

    session.add(db_podcast)
    session.commit()
    session.refresh(db_podcast)
    log.info(f"Successfully saved podcast to local database with ID: {db_podcast.id}")
    log.info("--- Podcast creation process finished ---")
    return db_podcast

@router.post("/{podcast_id}/recover-from-spreaker", status_code=200)
async def recover_spreaker_episodes(
    podcast_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Scans a podcast's Spreaker show for episodes that are not in the local database
    and creates local records for them. This is useful for recovering episodes
    uploaded outside the app.
    """
    log.info(f"Starting Spreaker recovery for podcast {podcast_id} for user {current_user.id}")

    podcast = session.get(Podcast, podcast_id)
    if not podcast or podcast.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Podcast not found.")

    if not podcast.spreaker_show_id or not current_user.spreaker_access_token:
        raise HTTPException(status_code=400, detail="Podcast is not linked to Spreaker or user is not connected.")

    client = SpreakerClient(api_token=current_user.spreaker_access_token)

    # 1. Get all episodes from Spreaker for the show
    ok, spreaker_episodes_data = client.get_all_episodes_for_show(podcast.spreaker_show_id)
    if not ok or not isinstance(spreaker_episodes_data, dict):
        log.error(f"Failed to fetch episodes from Spreaker for show {podcast.spreaker_show_id}: {spreaker_episodes_data}")
        raise HTTPException(status_code=502, detail="Could not fetch episodes from Spreaker.")
    
    spreaker_episodes = spreaker_episodes_data.get("items", [])
    if not spreaker_episodes:
        return {"recovered_count": 0, "message": "No episodes found on Spreaker for this show."}

    # 2. Get all existing Spreaker episode IDs from the local DB for this podcast
    existing_spreaker_ids_stmt = select(Episode.spreaker_episode_id).where(
        Episode.podcast_id == podcast.id,
        Episode.spreaker_episode_id != None  # noqa: E711 - intentional IS NOT NULL check
    )
    existing_ids = set(session.exec(existing_spreaker_ids_stmt).all())

    # 3. Find missing episodes and create them
    recovered_count = 0
    episodes_to_add = []
    for spk_ep in spreaker_episodes:
        spreaker_episode_id = str(spk_ep.get("episode_id"))
        if spreaker_episode_id in existing_ids:
            continue

        publish_date_str = spk_ep.get("published_at")
        publish_date = None
        if publish_date_str:
            try:
                dt = datetime.strptime(publish_date_str, "%Y-%m-%d %H:%M:%S")
                publish_date = dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                log.warning(f"Could not parse publish date '{publish_date_str}' for episode {spreaker_episode_id}")

        new_episode = Episode(
            user_id=current_user.id, podcast_id=podcast.id, title=spk_ep.get("title", "Untitled Recovered Episode"),
            show_notes=spk_ep.get("description"), spreaker_episode_id=spreaker_episode_id,
            final_audio_path=spk_ep.get("stream_url") or spk_ep.get("download_url"),
            remote_cover_url=spk_ep.get("image_original_url") or spk_ep.get("image_url"),
            status=EpisodeStatus.published if publish_date and publish_date <= datetime.now(timezone.utc) else EpisodeStatus.processed,
            publish_at=publish_date, is_published_to_spreaker=True,
            created_at=publish_date or datetime.now(timezone.utc)
        )
        episodes_to_add.append(new_episode)
        recovered_count += 1

    if episodes_to_add:
        session.add_all(episodes_to_add)
        session.commit()
        log.info(f"Recovered and created {recovered_count} new episode records for podcast {podcast.id}")

    return {"recovered_count": recovered_count, "message": f"Successfully recovered {recovered_count} missing episodes."}

@router.get("/", response_model=List[Podcast])
async def get_user_podcasts(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    statement = select(Podcast).where(Podcast.user_id == current_user.id)
    pods = session.exec(statement).all()
    # Ensure remote_cover_url is preferred when present (response_model will include fields automatically)
    # Nothing to mutate except legacy cover_path retention for now.
    return pods


log = logging.getLogger(__name__)

@router.put("/{podcast_id}", response_model=Podcast)
async def update_podcast(
    podcast_id: UUID,
    request: Request,
    podcast_update: PodcastUpdate = Body(default=None),
    cover_image: Optional[UploadFile] = File(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    allow_spreaker_id_change: bool = False,
):
    """Update podcast metadata. Accepts JSON body for fields OR multipart with cover_image.
    If cover_image provided, saves new file and updates Spreaker artwork when show id + token present.
    """
    statement = select(Podcast).where(Podcast.id == podcast_id, Podcast.user_id == current_user.id)
    podcast_to_update = session.exec(statement).first()

    if not podcast_to_update:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Podcast not found or you don't have permission to edit it.")

    original_spreaker_id = podcast_to_update.spreaker_show_id
    if podcast_update:
        pd = podcast_update.model_dump(exclude_unset=True)
        log.debug(f"[podcast.update] JSON payload keys={list(pd.keys())}")
        for key, value in pd.items():
            if key == 'rss_url_locked':
                continue
            if key == 'spreaker_show_id' and value and value != original_spreaker_id:
                if not allow_spreaker_id_change:
                    raise HTTPException(
                        status_code=400,
                        detail="Changing spreaker_show_id can break existing episode links. Resubmit with allow_spreaker_id_change=true to confirm."
                    )
            setattr(podcast_to_update, key, value)
    else:
        ct = request.headers.get("content-type", "") if request else ""
        candidate_keys = [
            "name","description","podcast_type","language","copyright_line",
            "owner_name","author_name","spreaker_show_id","cover_path","contact_email",
            "category_id","category_2_id","category_3_id"
        ]
        # Multipart branch
        if ct.startswith("multipart/form-data"):
            form = await request.form()
            for key in candidate_keys:
                if key in form and form.get(key) not in (None, ""):
                    val = form.get(key)
                    if key == 'spreaker_show_id' and val != original_spreaker_id and not allow_spreaker_id_change:
                        raise HTTPException(status_code=400, detail="Changing spreaker_show_id can break existing episode links. Resubmit with allow_spreaker_id_change=true to confirm.")
                    setattr(podcast_to_update, key, val)
            log.debug(f"[podcast.update] multipart keys applied: {[k for k in candidate_keys if k in form]}")
        # JSON fallback branch (when FastAPI didn't bind podcast_update due to mixed params)
        elif ct.startswith("application/json"):
            try:
                raw_json = await request.json()
                if isinstance(raw_json, dict):
                    applied = []
                    for key in candidate_keys:
                        if key in raw_json and raw_json[key] not in (None, ""):
                            val = raw_json[key]
                            if key == 'spreaker_show_id' and val != original_spreaker_id and not allow_spreaker_id_change:
                                raise HTTPException(status_code=400, detail="Changing spreaker_show_id can break existing episode links. Resubmit with allow_spreaker_id_change=true to confirm.")
                            setattr(podcast_to_update, key, val)
                            applied.append(key)
                    log.debug(f"[podcast.update] JSON fallback applied keys: {applied}")
            except Exception as je:
                log.warning(f"[podcast.update] JSON fallback parse failed: {je}")

    new_cover_saved = None
    if cover_image and cover_image.filename:
        file_extension = Path(cover_image.filename).suffix
        unique_filename = f"{current_user.id}_{uuid4()}{file_extension}"
        save_path = UPLOAD_DIRECTORY / unique_filename
        try:
            with save_path.open("wb") as buffer:
                shutil.copyfileobj(cover_image.file, buffer)
            # Ensure constraints (resize/compress) and possibly swap path
            processed_path = ensure_cover_image_constraints(str(save_path))
            if processed_path != str(save_path):
                processed_path_rel = Path(processed_path).name
                podcast_to_update.cover_path = processed_path_rel
            else:
                podcast_to_update.cover_path = unique_filename
            new_cover_saved = save_path
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save new cover image: {e}")

    session.add(podcast_to_update)
    session.commit()
    session.refresh(podcast_to_update)
    log.debug(f"[podcast.update] After local commit id={podcast_to_update.id} name={podcast_to_update.name} lang={podcast_to_update.language} author={podcast_to_update.author_name} owner={podcast_to_update.owner_name}")

    if podcast_to_update.spreaker_show_id and current_user.spreaker_access_token:
        try:
            client = SpreakerClient(api_token=current_user.spreaker_access_token)
            # Cover update
            if new_cover_saved:
                ok_img, resp_img = client.update_show_image(show_id=podcast_to_update.spreaker_show_id, image_file_path=str(new_cover_saved))
                if not ok_img:
                    log.warning(f"Spreaker cover update failed: {resp_img}")
                else:
                    show_obj = resp_img.get('show') if isinstance(resp_img, dict) else None
                    if isinstance(show_obj, dict):
                        for k in ('image_url','cover_url','cover_art_url','image'):
                            if show_obj.get(k):
                                podcast_to_update.remote_cover_url = show_obj.get(k)
                                # After capturing remote URL, we can keep cover_path for legacy until migration
                                break
            # Metadata update
            # Only attempt metadata update if we still have a valid (numeric) show id
            ok_meta = True
            resp_meta = None
            if podcast_to_update.spreaker_show_id and str(podcast_to_update.spreaker_show_id).isdigit():
                log.debug(
                    f"[podcast.update] Updating Spreaker metadata show_id={podcast_to_update.spreaker_show_id} payload="
                    f"title={podcast_to_update.name} desc_len={len(podcast_to_update.description or '')} lang={podcast_to_update.language}"
                )
                ok_meta, resp_meta = client.update_show_metadata(
                    show_id=podcast_to_update.spreaker_show_id,
                    title=podcast_to_update.name,
                    description=podcast_to_update.description,
                    language=podcast_to_update.language,
                    author_name=podcast_to_update.author_name,
                    owner_name=podcast_to_update.owner_name,
                    email=podcast_to_update.contact_email or current_user.email,
                    copyright_line=podcast_to_update.copyright_line,
                    show_type=(podcast_to_update.podcast_type.value if podcast_to_update.podcast_type else None),
                    category_id=podcast_to_update.category_id,
                    category_2_id=podcast_to_update.category_2_id,
                    category_3_id=podcast_to_update.category_3_id,
                )
                if not ok_meta:
                    log.warning(f"Spreaker metadata update failed: {resp_meta}")
            else:
                log.debug("[podcast.update] Skipped Spreaker metadata update (no numeric show id)")
            # If we don't yet have an RSS URL locked, fetch show details once.
            if not getattr(podcast_to_update, 'rss_url_locked', None):
                try:
                    ok_show, resp_show = client.get_show(podcast_to_update.spreaker_show_id)
                    if ok_show:
                        show_obj = resp_show.get("show") or resp_show
                        rss_candidate = (
                            show_obj.get("rss_url")
                            or show_obj.get("feed_url")
                            or show_obj.get("xml_url")
                        )
                        if rss_candidate:
                            podcast_to_update.rss_url_locked = rss_candidate
                            if not podcast_to_update.rss_url:
                                podcast_to_update.rss_url = rss_candidate
                            session.add(podcast_to_update)
                            session.commit()
                except Exception as ie:
                    log.warning(f"Failed fetching RSS URL for show update: {ie}")
        except Exception as e:
            log.warning(f"Spreaker metadata/cover update error: {e}")

    return podcast_to_update


@router.delete("/{podcast_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_podcast(
    podcast_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    statement = select(Podcast).where(Podcast.id == podcast_id, Podcast.user_id == current_user.id)
    podcast_to_delete = session.exec(statement).first()

    if not podcast_to_delete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Podcast not found.")

    session.delete(podcast_to_delete)
    session.commit()
    return None


@router.post("/{podcast_id}/link-spreaker-show", status_code=200)
async def link_spreaker_show(
    podcast_id: UUID,
    show_id: str = Body(..., embed=True, description="Numeric Spreaker show id to link"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Link an existing Spreaker show to this podcast by setting spreaker_show_id.
    Verifies the show exists and captures RSS URL and remote cover URL if available.
    """
    pod = session.exec(select(Podcast).where(Podcast.id == podcast_id, Podcast.user_id == current_user.id)).first()
    if not pod:
        raise HTTPException(status_code=404, detail="Podcast not found.")
    if not isinstance(show_id, str) or not show_id.isdigit():
        raise HTTPException(status_code=400, detail="show_id must be a numeric Spreaker id")
    token = getattr(current_user, 'spreaker_access_token', None)
    # Always set the numeric show id; enrich when token present.
    pod.spreaker_show_id = show_id
    if token:
        try:
            client = SpreakerClient(api_token=token)
            ok, resp = client.get_show(show_id)
            if ok and isinstance(resp, dict):
                show_obj = resp.get('show') or resp
                try:
                    rss_candidate = (
                        show_obj.get("rss_url")
                        or show_obj.get("feed_url")
                        or show_obj.get("xml_url")
                    )
                    if rss_candidate:
                        pod.rss_url_locked = pod.rss_url_locked or rss_candidate
                        if not pod.rss_url:
                            pod.rss_url = rss_candidate
                except Exception:
                    pass
                try:
                    for k in ('image_url','cover_url','cover_art_url','image'):
                        if show_obj.get(k):
                            pod.remote_cover_url = show_obj.get(k)
                            break
                except Exception:
                    pass
        except Exception:
            # If enrichment fails, we still keep the linked id
            pass
    session.add(pod)
    session.commit()
    session.refresh(pod)
    return {"message": "Linked to Spreaker show", "podcast": pod}


@router.post("/{podcast_id}/create-spreaker-show", status_code=200)
async def create_spreaker_show_for_podcast(
    podcast_id: UUID,
    title: Optional[str] = Body(None, embed=True),
    description: Optional[str] = Body(None, embed=True),
    language: Optional[str] = Body("en", embed=True),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Create a new Spreaker show for an existing podcast and store its show id.
    If the podcast already has a spreaker_show_id, returns a 400 unless client wants to recreate manually.
    """
    pod = session.exec(select(Podcast).where(Podcast.id == podcast_id, Podcast.user_id == current_user.id)).first()
    if not pod:
        raise HTTPException(status_code=404, detail="Podcast not found.")
    if getattr(pod, 'spreaker_show_id', None):
        raise HTTPException(status_code=400, detail="Podcast already linked to a Spreaker show.")
    token = getattr(current_user, 'spreaker_access_token', None)
    if not token:
        raise HTTPException(status_code=401, detail="User is not connected to Spreaker")
    client = SpreakerClient(api_token=token)
    t = (title or pod.name or "Untitled").strip()
    d = description if description is not None else (pod.description or "")
    ok, result = client.create_show(title=t, description=d, language=language or "en")
    if not ok:
        # Provide a friendlier error when user hits Spreaker's free plan show limit.
        msg = str(result)
        low = msg.lower()
        if "free account" in low or "can't create any more shows" in low or "cant create any more shows" in low:
            raise HTTPException(
                status_code=403,
                detail="You can only have one show on a free Spreaker account. Please upgrade your Spreaker plan to create additional shows.",
            )
        raise HTTPException(status_code=502, detail=f"Failed to create show on Spreaker: {result}")
    show_id = str(result.get("show_id")) if isinstance(result, dict) else None
    if not show_id or not show_id.isdigit():
        raise HTTPException(status_code=502, detail="Spreaker did not return a numeric show_id")
    pod.spreaker_show_id = show_id
    # Try to fetch details once to capture RSS and cover
    try:
        ok_show, resp_show = client.get_show(show_id)
        if ok_show:
            show_obj = resp_show.get("show") or resp_show
            rss_candidate = (
                show_obj.get("rss_url")
                or show_obj.get("feed_url")
                or show_obj.get("xml_url")
            )
            if rss_candidate:
                pod.rss_url_locked = pod.rss_url_locked or rss_candidate
                if not pod.rss_url:
                    pod.rss_url = rss_candidate
            for k in ('image_url','cover_url','cover_art_url','image'):
                if isinstance(show_obj, dict) and show_obj.get(k):
                    pod.remote_cover_url = show_obj.get(k)
                    break
    except Exception:
        pass
    session.add(pod)
    session.commit()
    session.refresh(pod)
    return {"message": "Spreaker show created and linked", "spreaker_show_id": show_id, "podcast": pod}
