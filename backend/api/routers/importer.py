import httpx
import feedparser
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from sqlmodel import Session, select
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4
import os
import re
import json

from ..core.database import get_session
from ..models.user import User
from ..models.podcast import Podcast, Episode, EpisodeStatus
from api.core.auth import get_current_user
from api.core.paths import FINAL_DIR
from infrastructure.gcs import upload_fileobj

import logging

router = APIRouter(
    prefix="/import",
    tags=["Importer"],
)

class RssPayload(BaseModel):
    rss_url: str
    download_audio: bool | None = False
    import_tags: bool | None = True
    limit: int | None = None
    attempt_link_spreaker: bool | None = True
    auto_publish_to_spreaker: bool | None = False
    publish_state: str | None = None  # 'unpublished' | 'public' | 'limited'

@router.post("/rss", status_code=201)
async def import_from_rss(
    payload: RssPayload,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    logger = logging.getLogger("api.importer")
    logger.info(f"Starting RSS import for user {current_user.id} with URL: {payload.rss_url}")
    try:
        existing_podcast = session.exec(select(Podcast).where(Podcast.rss_url == payload.rss_url, Podcast.user_id == current_user.id)).first()
        if existing_podcast:
            logger.warning(f"Podcast with RSS URL {payload.rss_url} already exists for user {current_user.id}")
            raise HTTPException(status_code=409, detail=f"Podcast '{existing_podcast.name}' has already been imported.")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(payload.rss_url, timeout=30.0, follow_redirects=True)
                response.raise_for_status()
                logger.info(f"Successfully fetched RSS feed from {payload.rss_url}")
            except httpx.RequestError as e:
                logger.error(f"Failed to fetch RSS feed from {payload.rss_url}: {e}")
                raise HTTPException(status_code=400, detail=f"Failed to fetch RSS feed: {e}")
    
        # Parse feed and enforce acceptance criteria
        try:
            feed = feedparser.parse(response.content)

            if not getattr(feed, 'feed', None) or not getattr(feed, 'entries', None):
                logger.error(f"RSS feed from {payload.rss_url} is invalid or empty.")
                raise HTTPException(status_code=400, detail="Invalid or empty RSS feed.")

            feed_info = getattr(feed, 'feed', {}) or {}
            try:
                logger.info(f"Parsing feed: {feed_info.get('title')}")
            except Exception:
                logger.info("Parsing feed: (unknown title)")

            title_str = None
            if isinstance(feed_info, dict):
                t = feed_info.get("title")
                title_str = str(t) if t is not None else None
                desc = feed_info.get("summary") or feed_info.get("subtitle")
                desc_str = str(desc) if desc is not None else None
                img = feed_info.get("image") or {}
                img_href = img.get("href") if isinstance(img, dict) else None
                # Ownership/metadata fields
                locked = str(feed_info.get("podcast_locked") or feed_info.get("podcast:locked") or "").strip().lower() in {"1", "true", "yes"}
                podcast_guid = str(feed_info.get("podcast_guid") or feed_info.get("podcast:guid") or "").strip() or None
                owner_email = None
                try:
                    it_owner = feed_info.get("itunes_owner") or feed_info.get("itunes:owner")
                    if isinstance(it_owner, dict):
                        owner_email = it_owner.get("email") or it_owner.get("itunes:email")
                except Exception:
                    owner_email = None
            else:
                title_str = str(feed_info) if feed_info is not None else None
                desc_str = None
                img_href = None
                locked = False
                podcast_guid = None
                owner_email = None

            # 1) Import only if podcast:locked != yes
            if locked:
                raise HTTPException(status_code=423, detail={"code": "feed_locked", "message": "Your current host has locked this feed (industry standard). Ask them to switch <podcast:locked> to no, then try again."})

            # Canonical URL after redirects
            canonical_url = str(getattr(response, 'url', payload.rss_url))

            # Check for existing podcast with the same podcast:guid (collision)
            if podcast_guid:
                existing_guid_claim = session.exec(select(Podcast).where(Podcast.podcast_guid == podcast_guid)).first()
                if existing_guid_claim and existing_guid_claim.user_id != current_user.id:
                    raise HTTPException(status_code=409, detail={"code": "guid_collision", "message": "This show is already claimed here. To proceed, re-verify ownership."})

            # 2) Email or DNS TXT verification gate
            verification_method = None
            if owner_email:
                verification_method = "email"
            else:
                raise HTTPException(status_code=400, detail={"code": "no_owner_email", "message": "We couldn’t find a verified owner email in this feed. Quick alternative: add a DNS TXT record (takes ~2 minutes)."})
        except HTTPException:
            raise
        except Exception as parse_ex:
            logger.exception(f"Feed parse/validation error: {parse_ex}")
            raise HTTPException(status_code=400, detail="Unable to parse or validate RSS feed.")

        new_podcast = Podcast(
            name=title_str or "Untitled Podcast",
            description=desc_str,
            rss_url=payload.rss_url,
            user_id=current_user.id,
            cover_path=img_href,  # We save the original URL
            podcast_guid=podcast_guid,
            feed_url_canonical=canonical_url,
            contact_email=owner_email,
            verification_method=verification_method,
            verified_at=datetime.utcnow() if verification_method else None,
        )
        session.add(new_podcast)
        session.commit()
        session.refresh(new_podcast)
        logger.info(f"Created new podcast with ID {new_podcast.id}")

        def _it_int(obj, *keys):
            for k in keys:
                v = obj.get(k)
                if v is None: continue
                try:
                    return int(v)
                except Exception:
                    try:
                        return int(str(v).strip())
                    except Exception:
                        pass
            return None

        def infer_numbers(entry):
            s = _it_int(entry, 'itunes_season', 'itunes:season', 'season')
            e = _it_int(entry, 'itunes_episode', 'itunes:episode', 'episode')
            if s is not None and e is not None:
                return s, e
            # Try from title patterns
            title = (entry.get('title') or '')
            m = re.search(r"S(\d{1,2})\s*E(\d{1,3})", title, re.I)
            if m:
                return int(m.group(1)), int(m.group(2))
            m = re.search(r"Season\s*(\d{1,2}).*Episode\s*(\d{1,3})", title, re.I)
            if m:
                return int(m.group(1)), int(m.group(2))
            m = re.search(r"(?:Ep(?:isode)?\s*)(\d{1,4})", title, re.I)
            if m:
                return 1, int(m.group(1))
            return None, None

        # Sort by published for stable numbering fallback
        entries = list(getattr(feed, 'entries', []) or [])
        try:
            entries.sort(
                key=lambda en: (
                    getattr(en, 'published_parsed', None)
                    or (en.get('published') if isinstance(en, dict) else None)
                    or (en.get('updated') if isinstance(en, dict) else None)
                    or ''
                ),
                reverse=False,
            )
        except Exception:
            pass

        episodes_to_add = []
        count = 0
        mirrored_ok = 0
        gcs_ok = 0
        for entry in entries:
            if payload.limit is not None and count >= payload.limit:
                break
            links = entry.get("links") if isinstance(entry, dict) else getattr(entry, 'links', None)
            if not isinstance(links, list):
                links = []
            def _g(et, k, default=None):
                return (et.get(k) if isinstance(et, dict) else getattr(et, k, default)) if et is not None else default
            audio_url = next((getattr(link, 'href', None) or _g(link, 'href') for link in links if (_g(link, 'rel') == "enclosure")), None)
            if not audio_url: continue

            image = entry.get("image") if isinstance(entry, dict) else getattr(entry, 'image', None)
            if isinstance(image, dict):
                episode_cover_url = image.get("href", new_podcast.cover_path)
            else:
                episode_cover_url = new_podcast.cover_path
            pp = getattr(entry, 'published_parsed', None)
            try:
                publish_date = datetime(*pp[:6]) if pp else None
            except Exception:
                publish_date = None

            it_season, it_episode = infer_numbers(entry)
            # fallback numbering: chronological starting at 1 if nothing present
            season_number = it_season if it_season is not None else 1
            episode_number = it_episode

            # Tags and explicit
            tags = []
            if bool(payload.import_tags):
                raw_kw = entry.get('itunes_keywords') or entry.get('itunes:keywords') or entry.get('tags')
                if raw_kw:
                    if isinstance(raw_kw, str):
                        tags = [t.strip() for t in raw_kw.split(',') if t.strip()]
                    elif isinstance(raw_kw, list):
                        tags = [str(getattr(t, 'term', t)).strip() for t in raw_kw if str(getattr(t, 'term', t)).strip()]
            explicit = str(entry.get('itunes_explicit') or entry.get('itunes:explicit') or '').lower() in {'1','true','yes','explicit'}

            title_val = entry.get("title") if isinstance(entry, dict) else getattr(entry, 'title', None)
            notes_val = entry.get("summary") if isinstance(entry, dict) else getattr(entry, 'summary', None)
            item_guid = entry.get('guid') if isinstance(entry, dict) else getattr(entry, 'guid', None)

            # Optional audio mirroring: download enclosure to FINAL_DIR and also upload to GCS
            final_audio_path = audio_url  # default to remote URL
            meta_blob: dict = {}
            if bool(payload.download_audio):
                try:
                    # Determine extension from URL or content-type
                    def _infer_ext(url: str, ct: str | None) -> str:
                        try:
                            ext = os.path.splitext(url.split("?")[0])[1].lower()
                        except Exception:
                            ext = ""
                        if not ext and ct:
                            ct_l = ct.lower()
                            if "mpeg" in ct_l or ct_l == "audio/mp3":
                                return ".mp3"
                            if "x-m4a" in ct_l or "mp4" in ct_l:
                                return ".m4a"
                            if "aac" in ct_l:
                                return ".aac"
                            if "wav" in ct_l:
                                return ".wav"
                            if "ogg" in ct_l:
                                return ".ogg"
                            if "webm" in ct_l:
                                return ".webm"
                        return ext or ".mp3"

                    # Stream download with size cap
                    MB = 1024 * 1024
                    MAX_BYTES = 1536 * MB
                    headers_ct = None
                    async with httpx.AsyncClient() as dl:
                        r = await dl.get(audio_url, timeout=120.0, follow_redirects=True)
                        r.raise_for_status()
                        headers_ct = r.headers.get("content-type")
                        ext = _infer_ext(audio_url, headers_ct)
                        # Safe base filename from title or URL
                        def _sanitize(s: str) -> str:
                            return re.sub(r"[^A-Za-z0-9._-]", "_", s).strip("._") or "audio"
                        base_from_url = os.path.basename(audio_url.split("?")[0]) or "audio"
                        stem = os.path.splitext(base_from_url)[0]
                        if not stem or len(stem) < 3:
                            stem = str(title_val or "episode").strip()[:50] or "episode"
                        safe_stem = _sanitize(stem)
                        unique_name = f"{uuid4().hex}_{safe_stem}{ext}"
                        FINAL_DIR.mkdir(parents=True, exist_ok=True)
                        dest_path = (FINAL_DIR / unique_name)

                        total = 0
                        with open(dest_path, "wb") as out:
                            async for chunk in r.aiter_bytes(chunk_size=1024 * 1024):
                                if not chunk:
                                    break
                                total += len(chunk)
                                if total > MAX_BYTES:
                                    raise HTTPException(status_code=413, detail="Enclosure audio exceeds 1.5 GB limit")
                                out.write(chunk)

                    # Local publish/playback will use basename via /static/final
                    final_audio_path = unique_name
                    mirrored_ok += 1
                    meta_blob["source_enclosure_url"] = audio_url
                    meta_blob["mirrored_local_basename"] = unique_name
                    meta_blob["mirrored_content_type"] = headers_ct

                    # Upload to GCS as well for durable storage (dev shim writes to MEDIA_DIR)
                    try:
                        bucket = os.getenv("MEDIA_BUCKET") or ("dev-bucket")
                        key = f"{current_user.id}/imported/{unique_name}"
                        with open(dest_path, "rb") as fh:
                            gcs_uri = upload_fileobj(bucket, key, fh, size=os.path.getsize(dest_path), content_type=(headers_ct or "audio/mpeg"), chunk_mb=8)
                        meta_blob["mirrored_gcs_uri"] = gcs_uri
                        gcs_ok += 1
                    except Exception as up_ex:
                        meta_blob["gcs_upload_error"] = str(up_ex)
                except HTTPException:
                    # Bubble up size errors
                    raise
                except Exception as ex:
                    # Fallback to remote URL only
                    meta_blob["mirror_error"] = str(ex)

            new_episode = Episode(
                user_id=current_user.id,
                podcast_id=new_podcast.id,
                title=str(title_val or "Untitled Episode"),
                show_notes=str(notes_val) if notes_val is not None else None,
                final_audio_path=final_audio_path,
                status=EpisodeStatus.processed,
                publish_at=publish_date,
                cover_path=episode_cover_url,
                season_number=season_number,
                episode_number=episode_number,
                is_explicit=explicit,
                original_guid=(str(item_guid) if item_guid else None),
                source_media_url=audio_url,
                source_published_at=publish_date,
            )
            # Attach meta details if present
            try:
                if meta_blob:
                    # Merge into existing meta_json if any
                    existing = {}
                    try:
                        existing = json.loads(new_episode.meta_json or "{}")
                        if not isinstance(existing, dict):
                            existing = {}
                    except Exception:
                        existing = {}
                    existing.update(meta_blob)
                    new_episode.meta_json = json.dumps(existing)
            except Exception:
                pass
            try:
                if tags:
                    new_episode.set_tags(tags)
            except Exception:
                pass
            episodes_to_add.append(new_episode)
            count += 1
        
        session.add_all(episodes_to_add)
        session.commit()
        logger.info(f"Imported {len(episodes_to_add)} episodes for podcast {new_podcast.id} (mirrored={mirrored_ok}, gcs={gcs_ok})")

        # Optional: attempt to link to an existing Spreaker show and map episodes
        spreaker_linked = 0
        chosen_show_id: str | None = None
        spreaker_attempted = False
        if bool(payload.attempt_link_spreaker) and getattr(current_user, 'spreaker_access_token', None):
            spreaker_attempted = True
            try:
                # Try to infer show id from RSS URL if it's a Spreaker feed
                sid = None
                try:
                    import re as _re
                    m = _re.search(r"/show/(\d+)", str(payload.rss_url))
                    if m:
                        sid = m.group(1)
                except Exception:
                    sid = None
                from api.services.publisher import SpreakerClient
                client = SpreakerClient(api_token=str(current_user.spreaker_access_token))
                if not sid:
                    # Fallback: list user's shows and match title
                    ok_sh, shows = client.get_shows()
                    if ok_sh and isinstance(shows, list):
                        def _norm(s: str | None) -> str:
                            try:
                                return (s or '').strip().lower()
                            except Exception:
                                return ''
                        target = _norm(new_podcast.name)
                        for it in shows:
                            if isinstance(it, dict) and _norm(it.get('title')) == target:
                                sid = str(it.get('show_id')) if it.get('show_id') is not None else None
                                break
                if sid and str(sid).isdigit():
                    chosen_show_id = str(sid)
                    # Persist onto podcast if not already set
                    if not getattr(new_podcast, 'spreaker_show_id', None):
                        new_podcast.spreaker_show_id = chosen_show_id
                        session.add(new_podcast)
                        session.commit()
                    # Fetch remote episodes and link by normalized title + publish date (day)
                    ok_ep, spk_data = client.get_all_episodes_for_show(chosen_show_id)
                    spk_items = (spk_data.get('items') if ok_ep and isinstance(spk_data, dict) else None) or []
                    # Build local index for episodes we just added
                    locals_for_map = session.exec(select(Episode).where(Episode.podcast_id == new_podcast.id, Episode.user_id == current_user.id)).all()
                    from datetime import timezone as _tz
                    def _norm_title(t: str | None) -> str:
                        try:
                            return (t or '').strip().lower()
                        except Exception:
                            return ''
                    def _date_key(dt: datetime | None) -> str:
                        try:
                            return dt.date().isoformat() if dt else ''
                        except Exception:
                            return ''
                    local_index: dict[tuple[str, str], Episode] = {}
                    for le in locals_for_map:
                        if getattr(le, 'spreaker_episode_id', None):
                            continue
                        local_index[(_norm_title(le.title), _date_key(getattr(le, 'publish_at', None)))] = le
                    for it in spk_items:
                        if not isinstance(it, dict):
                            continue
                        spk_title = it.get('title') or ''
                        spk_id = str(it.get('episode_id')) if it.get('episode_id') is not None else None
                        pub_dt = None
                        pub_str = it.get('published_at')
                        if pub_str:
                            try:
                                pub_dt = datetime.strptime(pub_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_tz.utc)
                            except Exception:
                                pub_dt = None
                        key = (_norm_title(spk_title), _date_key(pub_dt))
                        cand = local_index.get(key)
                        if cand and not getattr(cand, 'spreaker_episode_id', None) and spk_id:
                            cand.spreaker_episode_id = spk_id
                            if not getattr(cand, 'final_audio_path', None):
                                cand.final_audio_path = it.get('stream_url') or it.get('download_url')
                            if pub_dt:
                                try:
                                    cand.publish_at = cand.publish_at or pub_dt
                                except Exception:
                                    pass
                            session.add(cand)
                            spreaker_linked += 1
                    if spreaker_linked:
                        session.commit()
            except Exception as link_ex:
                logger.warning(f"Spreaker linking attempt failed: {link_ex}")

        # Optional: auto-publish to Spreaker using mirrored/local files
        publish_jobs_started = 0
        auto_publish_skipped = None
        if bool(payload.auto_publish_to_spreaker) and getattr(current_user, 'spreaker_access_token', None):
            show_id_to_use = chosen_show_id or getattr(new_podcast, 'spreaker_show_id', None)
            if show_id_to_use and str(show_id_to_use).isdigit():
                try:
                    from api.services.episodes import publisher as _ep_pub
                    # Publish episodes lacking a spreaker_episode_id
                    candidates = session.exec(
                        select(Episode).where(Episode.podcast_id == new_podcast.id, Episode.user_id == current_user.id)
                    ).all()
                    for ep in candidates:
                        if getattr(ep, 'spreaker_episode_id', None):
                            continue
                        if not getattr(ep, 'final_audio_path', None):
                            continue
                        try:
                            _ = _ep_pub.publish(
                                session=session,
                                current_user=current_user,
                                episode_id=ep.id,
                                derived_show_id=str(show_id_to_use),
                                publish_state=(payload.publish_state or 'public'),
                                auto_publish_iso=None,
                            )
                            publish_jobs_started += 1
                        except Exception as ex_pub:
                            logger.warning(f"Auto-publish submit failed for episode {ep.id}: {ex_pub}")
                except Exception as ex_all:
                    logger.warning(f"Auto-publish batch error: {ex_all}")
            else:
                auto_publish_skipped = "no_show_id"

        return {
            "message": "Import successful!",
            "podcast_name": new_podcast.name,
            "episodes_imported": len(episodes_to_add),
            "mirrored_count": mirrored_ok,
            "gcs_mirrored_count": gcs_ok,
            "log": {
                "feed_url": payload.rss_url,
                "feed_url_canonical": canonical_url,
                "podcast_guid": podcast_guid,
                "email_used": owner_email,
                "verifier": verification_method,
                "timestamp": datetime.utcnow().isoformat(),
            },
            "spreaker_attempted": spreaker_attempted,
            "spreaker_linked": spreaker_linked,
            "spreaker_show_id": (chosen_show_id or getattr(new_podcast, 'spreaker_show_id', None)),
            "auto_publish_started": publish_jobs_started,
            "auto_publish_skipped": auto_publish_skipped,
        }
    except HTTPException:
        # Propagate expected HTTP errors
        raise
    except Exception as e:
        logger.exception(f"An unexpected error occurred during RSS import: {e}")
        try:
            session.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")