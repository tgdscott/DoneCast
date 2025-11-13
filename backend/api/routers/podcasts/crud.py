from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlmodel import SQLModel, Session, delete, select

from ...routers.auth import get_current_user
from ...core.config import settings
from ...core.database import get_session
from ...core.paths import MEDIA_DIR
from ...models.podcast import (
    EpisodeSection,
    Podcast,
    PodcastDistributionStatus,
    PodcastImportState,
    PodcastTemplate,
    PodcastType,
)
from ...models.user import User
from ...services.image_utils import ensure_cover_image_constraints
from ...services.podcasts.utils import save_cover_upload
from ...services.publisher import SpreakerClient
from ...services import podcast_websites

log = logging.getLogger(__name__)

router = APIRouter()

UPLOAD_DIRECTORY = MEDIA_DIR
UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)


class PodcastUpdate(SQLModel):
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
    category_id: Optional[str] = None  # Changed from int to str to match database model
    category_2_id: Optional[str] = None  # Changed from int to str to match database model
    category_3_id: Optional[str] = None  # Changed from int to str to match database model


@router.post("/", response_model=Podcast, status_code=status.HTTP_201_CREATED)
async def create_podcast(
    name: str = Form(...),
    description: str = Form(...),
    cover_image: Optional[UploadFile] = File(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    log.info("--- Starting a new podcast creation process ---")
    log.info("Received request to create podcast with name: '%s'", name)

    try:
        name_clean = (name or "").strip()
        desc_clean = (description or "").strip()
    except Exception:
        name_clean = name
        desc_clean = description
    if not name_clean or len(name_clean) < 4:
        raise HTTPException(status_code=400, detail="Name must be at least 4 characters.")
    if not desc_clean:
        raise HTTPException(status_code=400, detail="Description is required.")

    spreaker_show_id: Optional[str] = None
    client: Optional[SpreakerClient] = None
    if current_user.spreaker_access_token:
        log.info("User has a Spreaker access token. Proceeding to create show on Spreaker.")
        client = SpreakerClient(api_token=current_user.spreaker_access_token)
        try:
            log.info("Calling SpreakerClient.create_show with title: '%s'", name_clean)
            success, result = client.create_show(title=name_clean, description=desc_clean, language="en")
            if not success:
                msg = str(result)
                low = msg.lower()
                if ("free account" in low) or ("can't create any more shows" in low) or ("cant create any more shows" in low):
                    log.warning("Spreaker free plan limit hit while creating show; proceeding without link.")
                else:
                    log.warning("Spreaker create_show failed: %s", result)
            else:
                log.info("Spreaker API call successful. Result: %s", result)
                spreaker_show_id = result.get("show_id") if isinstance(result, dict) else None
                if not spreaker_show_id:
                    log.warning("Spreaker created the show but did not return a valid show_id; proceeding without link.")
                else:
                    log.info("Successfully obtained Spreaker Show ID: %s", spreaker_show_id)
        except Exception as exc:
            log.warning("Spreaker create_show raised exception; proceeding without link: %s", exc)
    else:
        log.warning("User does not have a Spreaker access token. Skipping Spreaker show creation.")

    db_podcast = Podcast(
        name=name_clean,
        description=desc_clean,
        spreaker_show_id=spreaker_show_id,
        user_id=current_user.id,
    )

    if spreaker_show_id and client is not None:
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
                    if not getattr(db_podcast, "rss_url_locked", None):
                        db_podcast.rss_url_locked = rss_candidate
        except Exception as exc:
            log.warning("Failed to fetch show RSS after creation: %s", exc)

    if cover_image and cover_image.filename:
        log.info("Cover image provided: '%s'. Processing file.", cover_image.filename)
        try:
            stored_filename, save_path = save_cover_upload(
                cover_image,
                current_user.id,
                upload_dir=UPLOAD_DIRECTORY,
                allowed_extensions={".png", ".jpg", ".jpeg"},
                require_image_content_type=True,
            )
            # stored_filename is now a cloud storage URL (gs://bucket/path or https://... for R2)
            db_podcast.cover_path = stored_filename
            log.info("✅ Cover uploaded to cloud storage: %s", stored_filename)

            if spreaker_show_id and client is not None:
                log.info("Uploading cover art to Spreaker for show ID: %s", spreaker_show_id)
                try:
                    ok_img, resp_img = client.update_show_image(
                        show_id=spreaker_show_id,
                        image_file_path=str(save_path),
                    )
                    if ok_img and isinstance(resp_img, dict):
                        show_obj = resp_img.get("show") or resp_img
                        for key in ("image_url", "cover_url", "cover_art_url", "image"):
                            if isinstance(show_obj, dict) and show_obj.get(key):
                                db_podcast.remote_cover_url = show_obj.get(key)
                                break
                    elif not ok_img:
                        log.warning("Spreaker cover upload failed: %s", resp_img)
                except Exception as exc:
                    log.warning("Spreaker cover upload errored; continuing with local cover only: %s", exc)
        except HTTPException:
            raise
        except Exception as exc:
            log.error("Failed to save or upload cover image: %s", exc)
            raise HTTPException(status_code=500, detail=f"Failed to save or upload cover image: {exc}")
    else:
        log.info("No cover image was provided.")

    session.add(db_podcast)
    session.commit()
    session.refresh(db_podcast)
    log.info("Successfully saved podcast to local database with ID: %s", db_podcast.id)
    
    # 🎉 AUTO-CREATE WEBSITE & RSS FEED - New users get working URLs immediately!
    try:
        log.info("🚀 Auto-creating website and RSS feed for new podcast...")
        website, content = podcast_websites.create_or_refresh_site(session, db_podcast, current_user)
        
        # Get base domain from settings
        base_domain = getattr(settings, 'PODCAST_WEBSITE_BASE_DOMAIN', 'podcastplusplus.com')
        website_url = f"https://{website.subdomain}.{base_domain}"
        log.info(f"✅ Website auto-created: {website_url}")
        
        # Generate friendly slug for RSS feed URL
        if not db_podcast.slug:
            from ...services.podcast_websites import _slugify_base
            db_podcast.slug = _slugify_base(db_podcast.name)
            session.add(db_podcast)
            session.commit()
            session.refresh(db_podcast)
        
        rss_url = f"https://app.{base_domain}/rss/{db_podcast.slug}/feed.xml"
        log.info(f"✅ RSS feed available: {rss_url}")
        log.info(f"🎊 User can share immediately: {website_url} and {rss_url}")
    except Exception as exc:
        # Non-fatal - don't block podcast creation if website generation fails
        log.warning(f"⚠️ Failed to auto-create website/RSS feed (non-fatal): {exc}", exc_info=True)
    
    log.info("--- Podcast creation process finished ---")
    return db_podcast


def _load_user_podcasts(session: Session, user_id: UUID) -> List[Podcast]:
    statement = select(Podcast).where(Podcast.user_id == user_id)
    try:
        return session.exec(statement).all()
    except ProgrammingError as pe:
        message = str(pe).lower()
        if "remote_cover_url" not in message:
            raise

        session.rollback()
        log.warning(
            "[podcasts.list] remote_cover_url column missing for user=%s; using legacy fallback",
            user_id,
        )

        legacy_query = text(
            """
            SELECT
                id,
                user_id,
                name,
                description,
                cover_path,
                rss_url,
                rss_url_locked,
                podcast_type,
                language,
                copyright_line,
                owner_name,
                author_name,
                spreaker_show_id,
                contact_email,
                category_id,
                category_2_id,
                category_3_id,
                podcast_guid,
                feed_url_canonical,
                verification_method,
                verified_at
            FROM podcast
            WHERE user_id = :user_id
            """
        )

        rows = session.execute(legacy_query, {"user_id": str(user_id)}).all()
        podcasts: List[Podcast] = []
        for row in rows:
            data = dict(getattr(row, "_mapping", row))
            data.setdefault("remote_cover_url", None)
            podcasts.append(Podcast(**data))
        return podcasts


@router.get("/")
async def get_user_podcasts(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    try:
        # Get user ID safely
        user_id = getattr(current_user, "id", None)
        if not user_id:
            log.error("[podcasts.list] No user ID found in current_user")
            raise HTTPException(status_code=401, detail="User authentication failed")
        
        podcasts = _load_user_podcasts(session, user_id)
        podcast_ids = [p.id for p in podcasts]
        import_states: dict[UUID, PodcastImportState] = {}
        if podcast_ids:
            try:
                state_rows = session.exec(
                    select(PodcastImportState).where(PodcastImportState.podcast_id.in_(podcast_ids))
                ).all()
                import_states = {row.podcast_id: row for row in state_rows}
            except Exception as state_err:
                log.warning("[podcasts.list] Failed to load import states: %s", state_err, exc_info=True)
                # Continue without import states - non-fatal

        enriched: List[dict] = []
        for pod in podcasts:
            try:
                payload = pod.model_dump()
                state = import_states.get(pod.id)
                if state:
                    payload["import_status"] = {
                        "source": state.source,
                        "feed_total": state.feed_total,
                        "imported_count": state.imported_count,
                        "needs_full_import": state.needs_full_import,
                        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
                    }
                else:
                    payload["import_status"] = None
                
                # Add cover_url field with storage URL resolution (GCS/R2 ONLY - NEVER use Spreaker URLs)
                # CRITICAL: Push-only relationship with Spreaker - we never serve images from Spreaker
                cover_url = None
                try:
                    # ONLY use cover_path (our own storage) - IGNORE remote_cover_url (Spreaker URLs)
                    cover_source = pod.cover_path
                    
                    if not cover_source:
                        cover_url = None
                    # Priority 1: R2 URL (https://bucket.account-id.r2.cloudflarestorage.com/key)
                    elif cover_source.startswith("https://") and ".r2.cloudflarestorage.com" in cover_source:
                        # R2 URL - parse and generate signed URL
                        import os
                        from urllib.parse import unquote
                        try:
                            # Remove protocol
                            url_without_proto = cover_source.replace("https://", "").replace("http://", "")
                            # Split on first slash to separate host from path
                            if "/" in url_without_proto:
                                host_part, key_part = url_without_proto.split("/", 1)
                                # Extract bucket name (first part before first dot)
                                bucket_name = host_part.split(".")[0]
                                # URL-decode the key
                                key = unquote(key_part)
                                # Generate signed URL
                                from infrastructure.r2 import generate_signed_url
                                cover_url = generate_signed_url(bucket_name, key, expiration=86400)  # 24 hours
                            else:
                                # Fallback: try using storage abstraction
                                from infrastructure.storage import get_public_audio_url
                                resolved = get_public_audio_url(cover_source, expiration_days=1)
                                cover_url = resolved or cover_source
                        except Exception as r2_err:
                            log.warning(f"[podcasts.list] Failed to parse R2 URL {cover_source}: {r2_err}")
                            cover_url = None
                    # Priority 2: GCS path (gs://) → generate signed URL
                    elif cover_source.startswith("gs://"):
                        try:
                            from infrastructure.gcs import get_signed_url
                            gcs_str = cover_source[5:]  # Remove "gs://"
                            parts = gcs_str.split("/", 1)
                            if len(parts) == 2:
                                bucket, key = parts
                                cover_url = get_signed_url(bucket, key, expiration=3600)
                        except Exception as gcs_err:
                            log.warning(f"[podcasts.list] Failed to generate GCS signed URL: {gcs_err}")
                            cover_url = None
                    # Priority 3: R2 path (r2://) → resolve to signed URL
                    elif cover_source.startswith("r2://"):
                        try:
                            from infrastructure.storage import get_public_audio_url
                            cover_url = get_public_audio_url(cover_source, expiration_days=1)
                        except Exception as r2_storage_err:
                            log.warning(f"[podcasts.list] Failed to resolve R2 storage URL: {r2_storage_err}")
                            cover_url = None
                    # Priority 4: R2 bucket path (bucket/key format) → resolve to signed URL
                    elif "/" in cover_source and not cover_source.startswith("/") and not cover_source.startswith("http"):
                        # Might be R2 bucket/key format - try to resolve it
                        import os
                        r2_bucket = os.getenv("R2_BUCKET", "").strip()
                        if r2_bucket and r2_bucket in cover_source:
                            try:
                                from infrastructure.storage import get_public_audio_url
                                cover_url = get_public_audio_url(cover_source, expiration_days=1)
                            except Exception:
                                cover_url = None
                        # If not R2, fall through to local file handling
                        if not cover_url:
                            filename = os.path.basename(cover_source)
                            file_path = MEDIA_DIR / filename
                            if file_path.exists():
                                mtime = int(file_path.stat().st_mtime)
                                cover_url = f"/static/media/{filename}?t={mtime}"
                            else:
                                cover_url = f"/static/media/{filename}"
                    # Priority 5: Local file (dev only) - skip HTTP URLs (could be Spreaker)
                    elif not cover_source.startswith("http"):
                        import os
                        filename = os.path.basename(cover_source)
                        file_path = MEDIA_DIR / filename
                        if file_path.exists():
                            mtime = int(file_path.stat().st_mtime)
                            cover_url = f"/static/media/{filename}?t={mtime}"
                        else:
                            cover_url = f"/static/media/{filename}"
                    # Explicitly reject any HTTP URLs that aren't R2 (likely Spreaker)
                    else:
                        log.warning(f"[podcasts.list] Rejecting external URL in cover_path for podcast {pod.id}: {cover_source[:50]}...")
                        cover_url = None
                except Exception as e:
                    log.warning(f"[podcasts.list] Failed to resolve cover URL for podcast {pod.id}: {e}", exc_info=True)
                    cover_url = None
                
                payload["cover_url"] = cover_url
                enriched.append(payload)
            except Exception as pod_err:
                # If serializing a single podcast fails, log and skip it
                log.warning(f"[podcasts.list] Failed to serialize podcast {getattr(pod, 'id', 'unknown')}: {pod_err}", exc_info=True)
                continue

        return enriched
    except HTTPException:
        # Re-raise HTTP exceptions (like 401)
        raise
    except Exception as exc:
        log.error(
            "[podcasts.list] failed to load podcasts for user=%s: %s",
            getattr(current_user, "id", None),
            exc,
            exc_info=True
        )
        # Return empty list instead of raising - allows frontend to handle gracefully
        # But log the error so we can diagnose the issue
        return []


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
    statement = select(Podcast).where(Podcast.id == podcast_id, Podcast.user_id == current_user.id)
    podcast_to_update = session.exec(statement).first()

    if not podcast_to_update:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Podcast not found or you don't have permission to edit it.")

    original_spreaker_id = podcast_to_update.spreaker_show_id
    if podcast_update:
        payload = podcast_update.model_dump(exclude_unset=True)
        log.debug("[podcast.update] JSON payload keys=%s", list(payload.keys()))
        for key, value in payload.items():
            if key == "rss_url_locked":
                continue
            if key == "spreaker_show_id" and value and value != original_spreaker_id:
                if not allow_spreaker_id_change:
                    raise HTTPException(
                        status_code=400,
                        detail="Changing spreaker_show_id can break existing episode links. Resubmit with allow_spreaker_id_change=true to confirm.",
                    )
            setattr(podcast_to_update, key, value)
    else:
        content_type = request.headers.get("content-type", "") if request else ""
        candidate_keys = [
            "name",
            "description",
            "podcast_type",
            "language",
            "copyright_line",
            "owner_name",
            "author_name",
            "spreaker_show_id",
            "cover_path",
            "contact_email",
            "category_id",
            "category_2_id",
            "category_3_id",
        ]
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            for key in candidate_keys:
                if key in form and form.get(key) not in (None, ""):
                    value = form.get(key)
                    if key == "spreaker_show_id" and value != original_spreaker_id and not allow_spreaker_id_change:
                        raise HTTPException(
                            status_code=400,
                            detail="Changing spreaker_show_id can break existing episode links. Resubmit with allow_spreaker_id_change=true to confirm.",
                        )
                    setattr(podcast_to_update, key, value)
            log.debug(
                "[podcast.update] multipart keys applied: %s",
                [key for key in candidate_keys if key in form],
            )
        elif content_type.startswith("application/json"):
            try:
                raw_json = await request.json()
                if isinstance(raw_json, dict):
                    applied = []
                    for key in candidate_keys:
                        if key in raw_json and raw_json[key] not in (None, ""):
                            value = raw_json[key]
                            if key == "spreaker_show_id" and value != original_spreaker_id and not allow_spreaker_id_change:
                                raise HTTPException(
                                    status_code=400,
                                    detail="Changing spreaker_show_id can break existing episode links. Resubmit with allow_spreaker_id_change=true to confirm.",
                                )
                            setattr(podcast_to_update, key, value)
                            applied.append(key)
                    log.debug("[podcast.update] JSON fallback applied keys: %s", applied)
            except Exception as exc:
                log.warning("[podcast.update] JSON fallback parse failed: %s", exc)

    new_cover_saved: Optional[Path] = None
    if cover_image and cover_image.filename:
        try:
            stored_filename, save_path = save_cover_upload(
                cover_image,
                current_user.id,
                upload_dir=UPLOAD_DIRECTORY,
            )
            # Image processing is now done inside save_cover_upload before upload
            # stored_filename is the cloud storage URL (gs:// or https://)
            podcast_to_update.cover_path = stored_filename
            # save_path may not exist anymore (deleted after upload), but keep for Spreaker upload if needed
            new_cover_saved = save_path if save_path and save_path.exists() else None
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to save new cover image: {exc}")

    session.add(podcast_to_update)
    session.commit()
    session.refresh(podcast_to_update)
    log.debug(
        "[podcast.update] After local commit id=%s name=%s lang=%s author=%s owner=%s",
        podcast_to_update.id,
        podcast_to_update.name,
        podcast_to_update.language,
        podcast_to_update.author_name,
        podcast_to_update.owner_name,
    )

    if podcast_to_update.spreaker_show_id and current_user.spreaker_access_token:
        try:
            client = SpreakerClient(api_token=current_user.spreaker_access_token)
            if new_cover_saved:
                ok_img, resp_img = client.update_show_image(
                    show_id=podcast_to_update.spreaker_show_id,
                    image_file_path=str(new_cover_saved),
                )
                if not ok_img:
                    log.warning("Spreaker cover update failed: %s", resp_img)
                else:
                    show_obj = resp_img.get("show") if isinstance(resp_img, dict) else None
                    if isinstance(show_obj, dict):
                        for key in ("image_url", "cover_url", "cover_art_url", "image"):
                            if show_obj.get(key):
                                podcast_to_update.remote_cover_url = show_obj.get(key)
                                break
            ok_meta = True
            resp_meta = None
            if podcast_to_update.spreaker_show_id and str(podcast_to_update.spreaker_show_id).isdigit():
                log.debug(
                    "[podcast.update] Updating Spreaker metadata show_id=%s payload title=%s desc_len=%s lang=%s",
                    podcast_to_update.spreaker_show_id,
                    podcast_to_update.name,
                    len(podcast_to_update.description or ""),
                    podcast_to_update.language,
                )
                # Note: We don't send category_id to Spreaker anymore since we switched to Apple Podcasts
                # categories (string IDs like "arts", "technology") which are incompatible with Spreaker's
                # integer category system. Categories are stored in our database for RSS feed generation.
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
                    # Omit category_id fields - Apple Podcasts categories not compatible with Spreaker
                )
                if not ok_meta:
                    log.warning("Spreaker metadata update failed: %s", resp_meta)
            else:
                log.debug("[podcast.update] Skipped Spreaker metadata update (no numeric show id)")
            if not getattr(podcast_to_update, "rss_url_locked", None):
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
                except Exception as exc:
                    log.warning("Failed fetching RSS URL for show update: %s", exc)
        except Exception as exc:
            log.warning("Spreaker metadata/cover update error: %s", exc)

    # Enrich response with cover_url for frontend display
    # CRITICAL: Push-only relationship with Spreaker - we never serve images from Spreaker
    response_data = podcast_to_update.model_dump()
    cover_url = None
    try:
        # ONLY use cover_path (our own storage) - IGNORE remote_cover_url (Spreaker URLs)
        cover_source = podcast_to_update.cover_path
        
        if not cover_source:
            cover_url = None
        # Priority 1: R2 URL (https://bucket.account-id.r2.cloudflarestorage.com/key)
        elif cover_source.startswith("https://") and ".r2.cloudflarestorage.com" in cover_source:
            # R2 URL - parse and generate signed URL
            import os
            from urllib.parse import unquote
            try:
                # Remove protocol
                url_without_proto = cover_source.replace("https://", "").replace("http://", "")
                # Split on first slash to separate host from path
                if "/" in url_without_proto:
                    host_part, key_part = url_without_proto.split("/", 1)
                    # Extract bucket name (first part before first dot)
                    bucket_name = host_part.split(".")[0]
                    # URL-decode the key
                    key = unquote(key_part)
                    # Generate signed URL
                    from infrastructure.r2 import generate_signed_url
                    log.debug(f"[podcast.update] Parsing R2 URL: bucket={bucket_name}, key={key[:100]}...")
                    cover_url = generate_signed_url(bucket_name, key, expiration=86400)  # 24 hours
                    if cover_url:
                        log.info(f"[podcast.update] Generated R2 signed URL for cover (expires in 24h)")
                    else:
                        log.warning(f"[podcast.update] Failed to generate R2 signed URL for bucket={bucket_name}, key={key[:100]}...")
                else:
                    # Fallback: try using storage abstraction
                    from infrastructure.storage import get_public_audio_url
                    resolved = get_public_audio_url(cover_source, expiration_days=1)
                    cover_url = resolved or cover_source
            except Exception as r2_err:
                log.warning(f"[podcast.update] Failed to parse R2 URL {cover_source}: {r2_err}")
                cover_url = None
        # Priority 2: GCS path (gs://) → generate signed URL
        elif cover_source.startswith("gs://"):
            from infrastructure.gcs import get_signed_url
            gcs_str = cover_source[5:]  # Remove "gs://"
            parts = gcs_str.split("/", 1)
            if len(parts) == 2:
                bucket, key = parts
                cover_url = get_signed_url(bucket, key, expiration=3600)
        # Priority 3: R2 path (r2://) → resolve to signed URL
        elif cover_source.startswith("r2://"):
            from infrastructure.storage import get_public_audio_url
            cover_url = get_public_audio_url(cover_source, expiration_days=1)
        # Priority 4: R2 bucket path (bucket/key format) → resolve to signed URL
        elif "/" in cover_source and not cover_source.startswith("/") and not cover_source.startswith("http"):
            # Might be R2 bucket/key format - try to resolve it
            import os
            r2_bucket = os.getenv("R2_BUCKET", "").strip()
            if r2_bucket and r2_bucket in cover_source:
                from infrastructure.storage import get_public_audio_url
                cover_url = get_public_audio_url(cover_source, expiration_days=1)
            # If not R2, fall through to local file handling
            if not cover_url:
                filename = os.path.basename(cover_source)
                file_path = MEDIA_DIR / filename
                if file_path.exists():
                    mtime = int(file_path.stat().st_mtime)
                    cover_url = f"/static/media/{filename}?t={mtime}"
                else:
                    cover_url = f"/static/media/{filename}"
        # Priority 5: Local file (dev only) - skip HTTP URLs (could be Spreaker)
        elif not cover_source.startswith("http"):
            import os
            filename = os.path.basename(cover_source)
            file_path = MEDIA_DIR / filename
            if file_path.exists():
                mtime = int(file_path.stat().st_mtime)
                cover_url = f"/static/media/{filename}?t={mtime}"
            else:
                cover_url = f"/static/media/{filename}"
        # Explicitly reject any HTTP URLs that aren't R2 (likely Spreaker)
        else:
            log.warning(f"[podcast.update] Rejecting external URL in cover_path for podcast {podcast_to_update.id}: {cover_source[:50]}...")
            cover_url = None
    except Exception as e:
        log.warning(f"[podcast.update] Failed to resolve cover URL: {e}", exc_info=True)
    
    response_data["cover_url"] = cover_url
    log.info(f"[podcast.update] Returning response with cover_url={'SET' if cover_url else 'None'}, cover_path={podcast_to_update.cover_path[:100] if podcast_to_update.cover_path else 'None'}...")
    # Return dict directly to include cover_url (not in Podcast model)
    # FastAPI will serialize this dict and include all fields, even if not in response_model
    return response_data


@router.delete("/{podcast_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_podcast(
    podcast_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    statement = select(Podcast).where(Podcast.id == podcast_id, Podcast.user_id == current_user.id)
    podcast_to_delete = session.exec(statement).first()

    if not podcast_to_delete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Podcast not found.")

    # Clean up dependent records referencing this podcast.
    # Templates retain their data but should no longer be scoped to a deleted show.
    templates = session.exec(
        select(PodcastTemplate).where(PodcastTemplate.podcast_id == podcast_id)
    ).all()
    for template in templates:
        template.podcast_id = None
        session.add(template)

    session.exec(
        delete(PodcastDistributionStatus).where(
            PodcastDistributionStatus.podcast_id == podcast_id
        )
    )
    session.exec(
        delete(EpisodeSection).where(EpisodeSection.podcast_id == podcast_id)
    )

    session.delete(podcast_to_delete)
    session.commit()
    return None
