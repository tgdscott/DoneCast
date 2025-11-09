"""
Self-hosted RSS 2.0 podcast feed generation.

This replaces Spreaker's RSS feed with our own, giving full control over:
- Episode delivery (served from Cloudflare R2 with signed URLs)
- Feed metadata and iTunes tags
- Analytics and tracking
- No platform fees or restrictions
"""

from collections import defaultdict
from datetime import datetime, timezone
from html import unescape
import logging
import os
import re
from typing import List, Optional, Sequence
from uuid import UUID
import xml.etree.ElementTree as ET
from xml.dom import minidom

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlmodel import Session, select, desc

from api.core.database import get_session
from api.models.podcast import Podcast, Episode, EpisodeStatus
from api.models.website import PodcastWebsite, PodcastWebsiteStatus
from api.routers.podcasts.categories import APPLE_PODCAST_CATEGORIES_FLAT
from api.core.config import settings
from infrastructure.storage import get_public_audio_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rss", tags=["rss-feed"])


_CDATA_START_TOKEN = "__PPP_CDATA_START__"
_CDATA_END_TOKEN = "__PPP_CDATA_END__"

_CATEGORY_LABELS = {
    entry["category_id"]: entry["name"]
    for entry in APPLE_PODCAST_CATEGORIES_FLAT
}

_HTML_TAG_RE = re.compile(r"<[^>]+>")

_R2_HOST_TOKEN = ".r2.cloudflarestorage.com/"


def _looks_like_r2_path(value: Optional[str]) -> bool:
    if not value:
        return False

    lowered = value.strip().lower()
    if not lowered:
        return False

    if lowered.startswith("r2://"):
        return True

    if _R2_HOST_TOKEN in lowered:
        return True

    bucket = (getattr(settings, "R2_BUCKET", None) or os.getenv("R2_BUCKET", "")).strip().lower()
    if bucket and bucket in lowered and "r2" in lowered:
        return True

    return False


def _looks_like_gcs_path(value: Optional[str]) -> bool:
    if not value:
        return False

    lowered = value.strip().lower()
    if not lowered:
        return False

    return lowered.startswith("gs://") or "storage.googleapis.com" in lowered


def _format_rfc2822(dt: Optional[datetime]) -> str:
    """Format datetime as RFC 2822 (required for RSS pubDate)"""
    if not dt:
        return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S %z")


def _format_duration(duration_ms: Optional[int]) -> str:
    """Format duration in HH:MM:SS or MM:SS"""
    if not duration_ms:
        return "00:00"
    total_seconds = duration_ms // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"



def _strip_html(value: Optional[str]) -> str:
    if not value:
        return ""
    text = _HTML_TAG_RE.sub(" ", value)
    return unescape(text).strip()


def _truncate(value: str, limit: int) -> str:
    if not value:
        return ""
    if len(value) <= limit:
        return value
    truncated = value[: max(limit - 1, 0)].rstrip()
    return f"{truncated}…"


def _resolve_site_url(session: Session, podcast: Podcast) -> str:
    base_domain = (getattr(settings, "PODCAST_WEBSITE_BASE_DOMAIN", "podcastplusplus.com") or "podcastplusplus.com").strip()
    base_domain = base_domain.strip("/") or "podcastplusplus.com"

    website = session.exec(
        select(PodcastWebsite)
        .where(PodcastWebsite.podcast_id == podcast.id)
        .where(PodcastWebsite.status == PodcastWebsiteStatus.published)
        .limit(1)
    ).first()

    url: Optional[str] = None

    if website:
        if website.custom_domain:
            domain = website.custom_domain.strip()
            if domain:
                url = domain
        elif website.subdomain:
            url = f"https://{website.subdomain.strip()}.{base_domain}"

    if not url:
        fallback = getattr(settings, "APP_BASE_URL", None)
        identifier = podcast.slug or str(podcast.id)
        if fallback:
            url = f"{fallback.rstrip('/')}/podcast/{identifier}"
        else:
            url = f"https://{base_domain}/podcast/{identifier}"

    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"

    return url.rstrip("/")


def _resolve_category_labels(podcast: Podcast) -> List[str]:
    candidate_ids: Sequence[Optional[str]] = (
        getattr(podcast, "category_id", None),
        getattr(podcast, "category_2_id", None),
        getattr(podcast, "category_3_id", None),
    )

    labels: List[str] = []
    for category_id in candidate_ids:
        if not category_id:
            continue
        label = _CATEGORY_LABELS.get(category_id)
        if label:
            labels.append(label)

    if not labels:
        fallback = getattr(podcast, "itunes_category", None)
        if fallback:
            labels.append(fallback)

    if not labels:
        labels.append("Technology")

    return labels


def _append_itunes_categories(channel: ET.Element, labels: Sequence[str]) -> None:
    primary_elements: dict[str, ET.Element] = {}
    secondary_seen: defaultdict[str, set[str]] = defaultdict(set)
    seen_pairs: set[tuple[str, Optional[str]]] = set()

    for label in labels:
        parts = [part.strip() for part in label.split("›") if part.strip()]
        if not parts:
            continue

        primary = parts[0]
        secondary = parts[1] if len(parts) > 1 else None
        key = (primary, secondary)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)

        primary_elem = primary_elements.get(primary)
        if primary_elem is None:
            primary_elem = ET.SubElement(channel, "itunes:category", {"text": primary})
            primary_elements[primary] = primary_elem

        if secondary and secondary not in secondary_seen[primary]:
            ET.SubElement(primary_elem, "itunes:category", {"text": secondary})
            secondary_seen[primary].add(secondary)


def _collect_keywords(existing: dict[str, str], tags: Sequence[str]) -> None:
    for tag in tags:
        normalized = tag.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in existing:
            continue
        existing[key] = normalized


def _ensure_https(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    stripped = url.strip()
    if stripped.startswith("https://"):
        return stripped
    if stripped.startswith("http://"):
        return "https://" + stripped[len("http://"):]
    return stripped


def _wrap_with_op3(url: str) -> str:
    if not url:
        return url
    normalized = url.strip()
    if not normalized:
        return normalized
    if normalized.startswith("https://analytics.podcastplusplus.com/e/"):
        return normalized
    return f"https://analytics.podcastplusplus.com/e/{normalized}"


def _resolve_storage_asset(
    storage_path: Optional[str],
    *,
    asset_kind: str,
    expiration_days: int = 14,
    wrap_with_op3: bool = False,
) -> Optional[str]:
    if not storage_path:
        return None

    cleaned = storage_path.strip()
    if not cleaned:
        return None

    if _looks_like_gcs_path(cleaned):
        logger.warning(
            "RSS Feed: %s path %s is still hosted on GCS; skipping (R2 required)",
            asset_kind,
            cleaned,
        )
        return None

    if not _looks_like_r2_path(cleaned):
        logger.warning(
            "RSS Feed: %s path %s is not hosted on R2; skipping",
            asset_kind,
            cleaned,
        )
        return None

    resolved = get_public_audio_url(
        cleaned,
        expiration_days=expiration_days,
        use_cdn=False,
    )

    if not resolved:
        logger.warning(
            "RSS Feed: Failed to resolve %s path %s to signed URL",
            asset_kind,
            cleaned,
        )
        return None

    if _looks_like_gcs_path(resolved) or not _looks_like_r2_path(resolved):
        logger.warning(
            "RSS Feed: %s resolved URL %s is not served from R2; skipping",
            asset_kind,
            resolved,
        )
        return None

    resolved = _ensure_https(resolved)

    if wrap_with_op3 and resolved:
        resolved = _wrap_with_op3(resolved)

    return resolved


def _generate_podcast_rss(
    podcast: Podcast,
    episodes: List[Episode],
    base_url: str,
    feed_url: Optional[str] = None,
) -> str:
    """Generate RSS 2.0 feed XML for a podcast with iTunes namespace tags."""

    rss = ET.Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
            "xmlns:podcast": "https://podcastindex.org/namespace/1.0",
            "xmlns:content": "http://purl.org/rss/1.0/modules/content/",
            "xmlns:atom": "http://www.w3.org/2005/Atom",
        },
    )

    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = podcast.name
    ET.SubElement(channel, "link").text = base_url

    description_html = getattr(podcast, "description", None) or "A podcast"
    description_text = _strip_html(description_html) or "A podcast"
    ET.SubElement(channel, "description").text = description_text
    ET.SubElement(channel, "language").text = podcast.language or "en"

    ET.SubElement(channel, "itunes:author").text = podcast.author_name or podcast.owner_name or "Unknown"
    ET.SubElement(channel, "itunes:explicit").text = "yes" if getattr(podcast, "is_explicit", False) else "no"
    ET.SubElement(channel, "itunes:type").text = getattr(podcast, "podcast_type", "episodic") or "episodic"
    ET.SubElement(channel, "itunes:summary").text = _truncate(description_text, 4000)
    ET.SubElement(channel, "itunes:subtitle").text = _truncate(description_text, 255)
    ET.SubElement(channel, "generator").text = "Podcast Plus Plus RSS Generator"

    if podcast.contact_email:
        ET.SubElement(channel, "managingEditor").text = podcast.contact_email

    # Atom links for feed discovery
    ET.SubElement(
        channel,
        "atom:link",
        {
            "href": feed_url or podcast.rss_feed_url or base_url,
            "rel": "self",
            "type": "application/rss+xml",
        },
    )
    ET.SubElement(
        channel,
        "atom:link",
        {
            "href": base_url,
            "rel": "alternate",
            "type": "text/html",
        },
    )

    if podcast.contact_email or podcast.owner_name:
        owner = ET.SubElement(channel, "itunes:owner")
        if podcast.owner_name:
            ET.SubElement(owner, "itunes:name").text = podcast.owner_name
        if podcast.contact_email:
            ET.SubElement(owner, "itunes:email").text = podcast.contact_email

    # CRITICAL: Push-only relationship with Spreaker - NEVER use Spreaker URLs in RSS feeds
    # ONLY use cover_path (our own storage) - IGNORE remote_cover_url (contains Spreaker URLs)
    cover_url = None
    if podcast.cover_path:
        raw_cover = podcast.cover_path.strip()
        # Only process R2 paths (bucket/key format, r2://, or R2 HTTPS URLs)
        if _looks_like_r2_path(raw_cover):
            if raw_cover.startswith("http") and ".r2.cloudflarestorage.com" in raw_cover:
                # R2 HTTPS URL - resolve to signed URL
                cover_url = _resolve_storage_asset(
                    raw_cover,
                    asset_kind="podcast-cover",
                    expiration_days=30,
                )
            elif not raw_cover.startswith("http"):
                # R2 path format (r2:// or bucket/key) - resolve to signed URL
                cover_url = _resolve_storage_asset(
                    raw_cover,
                    asset_kind="podcast-cover",
                    expiration_days=30,
                )
        # Reject any HTTP URLs that aren't R2 (likely Spreaker or other external URLs)
        elif raw_cover.startswith("http"):
            logger.warning(
                "RSS Feed: Podcast %s cover_path contains external URL (not R2); rejecting: %s",
                podcast.id,
                raw_cover[:50],
            )
            cover_url = None
        # GCS paths are deprecated (migrated to R2)
        elif _looks_like_gcs_path(raw_cover):
            logger.warning(
                "RSS Feed: Podcast %s cover is still on GCS (should be migrated to R2); skipping",
                podcast.id,
            )
    # Explicitly ignore remote_cover_url - it contains Spreaker URLs which we never serve

    if cover_url:
        ET.SubElement(channel, "itunes:image", {"href": cover_url})
        image_elem = ET.SubElement(channel, "image")
        ET.SubElement(image_elem, "url").text = cover_url
        ET.SubElement(image_elem, "title").text = podcast.name
        ET.SubElement(image_elem, "link").text = base_url

    _append_itunes_categories(channel, _resolve_category_labels(podcast))

    if podcast.copyright_line:
        ET.SubElement(channel, "copyright").text = podcast.copyright_line

    if podcast.podcast_guid:
        ET.SubElement(channel, "podcast:guid").text = podcast.podcast_guid

    latest_pub: Optional[datetime] = None
    channel_keyword_index: dict[str, str] = {}

    for episode in episodes:
        audio_url = _resolve_storage_asset(
            getattr(episode, "gcs_audio_path", None),
            asset_kind="audio",
            wrap_with_op3=True,
        )
        if audio_url:
            logger.info(
                "RSS Feed: Generated OP3-prefixed R2 URL for episode %s",
                episode.episode_number,
            )
        else:
            logger.warning(
                "RSS Feed: Episode %s has no R2 audio available; skipping",
                episode.episode_number,
            )

        if not audio_url:
            logger.warning(
                "RSS Feed: Skipping episode %s due to missing audio URL",
                episode.id,
            )
            continue

        item = ET.SubElement(channel, "item")

        ET.SubElement(item, "title").text = episode.title
        ET.SubElement(item, "itunes:title").text = episode.title

        episode_link = f"{base_url}/episodes/{episode.id}" if base_url else ""
        if episode_link:
            ET.SubElement(item, "link").text = episode_link

        description_html = (episode.show_notes or "").strip() or episode.title
        description_text = _strip_html(description_html) or episode.title
        ET.SubElement(item, "description").text = description_text
        ET.SubElement(item, "itunes:summary").text = _truncate(description_text, 4000)
        ET.SubElement(item, "itunes:subtitle").text = _truncate(description_text, 255)
        if description_html:
            content_elem = ET.SubElement(item, "content:encoded")
            content_elem.text = f"{_CDATA_START_TOKEN}{description_html}{_CDATA_END_TOKEN}"

        guid_text = episode.original_guid or str(episode.id)
        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = guid_text

        pub_date = episode.publish_at or episode.source_published_at or episode.processed_at
        ET.SubElement(item, "pubDate").text = _format_rfc2822(pub_date)
        if pub_date and (latest_pub is None or pub_date > latest_pub):
            latest_pub = pub_date

        file_size = getattr(episode, "audio_file_size", None) or 0
        ET.SubElement(
            item,
            "enclosure",
            {
                "url": audio_url,
                "type": "audio/mpeg",
                "length": str(file_size),
            },
        )

        # CRITICAL: Push-only relationship with Spreaker - NEVER use remote_cover_url (contains Spreaker URLs)
        # Priority: gcs_cover_path (R2 URLs) > cover_path (if URL) > _resolve_storage_asset for cover_path
        episode_image = None
        
        # Priority 1: gcs_cover_path (contains R2 URLs for new episodes)
        if episode.gcs_cover_path:
            gcs_cover_str = str(episode.gcs_cover_path).strip()
            # If it's already an R2 HTTPS URL, use it directly
            if gcs_cover_str.lower().startswith(("http://", "https://")):
                # Reject Spreaker URLs (safety check)
                if "spreaker.com" not in gcs_cover_str.lower() and "cdn.spreaker.com" not in gcs_cover_str.lower():
                    episode_image = gcs_cover_str
                else:
                    logger.warning(
                        "RSS Feed: Episode %s gcs_cover_path contains Spreaker URL; rejecting: %s",
                        episode.id,
                        gcs_cover_str[:50],
                    )
            else:
                # GCS path or R2 path format - resolve using _resolve_storage_asset
                episode_image = _resolve_storage_asset(
                    episode.gcs_cover_path,
                    asset_kind="cover",
                )
        
        # Priority 2: cover_path if it's a URL (but not Spreaker)
        if not episode_image and episode.cover_path:
            cover_path_str = str(episode.cover_path).strip()
            if cover_path_str.lower().startswith(("http://", "https://")):
                # Reject Spreaker URLs
                if "spreaker.com" not in cover_path_str.lower() and "cdn.spreaker.com" not in cover_path_str.lower():
                    # Only use if it looks like an R2 URL
                    if ".r2.cloudflarestorage.com" in cover_path_str.lower():
                        episode_image = cover_path_str
                    else:
                        logger.warning(
                            "RSS Feed: Episode %s cover_path contains external URL (not R2); rejecting: %s",
                            episode.id,
                            cover_path_str[:50],
                        )
            else:
                # Local path - try to resolve as R2 asset
                episode_image = _resolve_storage_asset(
                    episode.cover_path,
                    asset_kind="cover",
                )
        
        # Explicitly ignore remote_cover_url - it contains Spreaker URLs which we never serve

        episode_image = _ensure_https(episode_image)

        if episode_image:
            ET.SubElement(item, "itunes:image", {"href": episode_image})

        duration_ms = getattr(episode, "duration_ms", None)
        if duration_ms:
            ET.SubElement(item, "itunes:duration").text = _format_duration(duration_ms)

        if episode.episode_number:
            ET.SubElement(item, "itunes:episode").text = str(episode.episode_number)
        if episode.season_number:
            ET.SubElement(item, "itunes:season").text = str(episode.season_number)

        ET.SubElement(item, "itunes:explicit").text = "yes" if episode.is_explicit else "no"

        episode_type = getattr(episode, "episode_type", "full") or "full"
        if episode_type in ("full", "trailer", "bonus"):
            ET.SubElement(item, "itunes:episodeType").text = episode_type

        tags = episode.tags()
        if tags:
            ET.SubElement(item, "itunes:keywords").text = ", ".join(tags[:10])
            _collect_keywords(channel_keyword_index, tags)

        ET.SubElement(item, "itunes:author").text = (
            podcast.author_name or podcast.owner_name or podcast.name
        )

    if latest_pub:
        ET.SubElement(channel, "lastBuildDate").text = _format_rfc2822(latest_pub)
    else:
        ET.SubElement(channel, "lastBuildDate").text = _format_rfc2822(datetime.now(timezone.utc))

    if channel_keyword_index:
        ordered_keywords: List[str] = []
        for keyword in channel_keyword_index.values():
            ordered_keywords.append(keyword)
            if len(ordered_keywords) >= 12:
                break
        if ordered_keywords:
            ET.SubElement(channel, "itunes:keywords").text = _truncate(
                ", ".join(ordered_keywords),
                255,
            )

    xml_string = ET.tostring(rss, encoding="unicode")
    dom = minidom.parseString(xml_string)
    pretty_xml = dom.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
    return (
        pretty_xml
        .replace(_CDATA_START_TOKEN, "<![CDATA[")
        .replace(_CDATA_END_TOKEN, "]]>")
    )


@router.get("/{podcast_identifier}/feed.xml", response_class=Response)
def get_podcast_feed(
    podcast_identifier: str,
    request: Request,
    session: Session = Depends(get_session),
):
    """
    Generate RSS 2.0 podcast feed for a specific podcast.
    
    Supports both friendly slugs and UUIDs:
    - https://yoursite.com/rss/my-awesome-podcast/feed.xml (friendly!)
    - https://yoursite.com/rss/{uuid}/feed.xml (still works)
    
    This feed can be submitted to Apple Podcasts, Spotify, Google Podcasts, etc.
    """
    
    # Try to find podcast by slug first (friendly URL)
    podcast = session.exec(
        select(Podcast).where(Podcast.slug == podcast_identifier)
    ).first()
    
    # If not found by slug, try UUID
    if not podcast:
        try:
            podcast_uuid = UUID(podcast_identifier)
            podcast = session.get(Podcast, podcast_uuid)
        except (ValueError, AttributeError):
            pass
    
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")
    
    # Get all episodes with audio available, regardless of published/scheduled status
    # CRITICAL FIX (Oct 21): Scheduled episodes MUST be playable - they have assembled audio in GCS
    # The publish_at date controls WHEN they appear in podcast apps, but the audio itself
    # should be accessible as soon as it exists (for preview, manual editor, etc.)
    #
    # Include episodes that are:
    # 1. Published (status == published)
    # 2. Scheduled (status has future publish_at) - these have assembled audio ready
    # 3. Processed (status == processed) - fallback for episodes without explicit publish
    #
    # Filter out:
    # - Episodes without audio (no gcs_audio_path)
    # - Draft/pending/error episodes
    statement = (
        select(Episode)
        .where(Episode.podcast_id == podcast.id)
        .where(
            (Episode.status == EpisodeStatus.published) |
            (Episode.status == EpisodeStatus.processed)  # Includes scheduled episodes
        )
        .where(Episode.gcs_audio_path != None)  # Must have audio in GCS
        .order_by(desc(Episode.publish_at))
    )
    episodes = session.exec(statement).all()
    
    site_url = _resolve_site_url(session, podcast)
    feed_xml = _generate_podcast_rss(podcast, list(episodes), site_url, str(request.url))
    
    return Response(
        content=feed_xml,
        media_type="application/rss+xml",
        headers={
            "Cache-Control": "public, max-age=300",  # Cache for 5 minutes
            "Content-Disposition": f'inline; filename="feed.xml"',
        }
    )


@router.get("/user/feed.xml", response_class=Response)
def get_user_first_podcast_feed(
    request: Request,
    session: Session = Depends(get_session),
):
    """
    Convenience endpoint: RSS feed for user's first/primary podcast.
    Useful during migration when you have one podcast.
    """
    
    # Get first podcast (for single-podcast users)
    statement = select(Podcast).limit(1)
    podcast = session.exec(statement).first()
    
    if not podcast:
        raise HTTPException(status_code=404, detail="No podcasts found")
    
    # Use slug if available, otherwise UUID
    identifier = podcast.slug or str(podcast.id)
    return get_podcast_feed(identifier, request, session)
