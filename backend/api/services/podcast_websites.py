from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import UUID

import requests
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from api.core.config import settings
from api.models.podcast import Episode, Podcast
from api.models.user import User
from api.models.website import PodcastWebsite, PodcastWebsiteStatus
from api.services.ai_content import client_gemini

try:  # pragma: no cover - optional dependency in local dev
    from google.cloud import storage  # type: ignore
except Exception:  # pragma: no cover
    storage = None  # type: ignore

try:  # pragma: no cover - optional dependency in local dev
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    Image = None  # type: ignore
import io
import colorsys

log = logging.getLogger(__name__)

_SITE_SCHEMA_PROMPT = """
You are Podcast Plus Plus SiteBuilder, an expert AI web designer.
Create warm, inviting, accessible landing pages that help listeners subscribe.
ALWAYS respond with a single JSON object matching this schema exactly:
{
  "hero_title": string,              # big headline for the hero section
  "hero_subtitle": string,           # supportive subtitle or elevator pitch
  "hero_image_url": string | null,   # podcast cover or on-brand hero image
  "about": {
      "heading": string,
      "body": string                # 2-3 short paragraphs in markdown-compatible text
  },
  "hosts": [
      {"name": string, "bio": string}
  ],
  "episodes": [
      {
         "episode_id": string,      # UUID provided in the context
         "title": string,
         "description": string,     # teaser copy encouraging a listen
         "cta_label": string,       # e.g. "Play episode"
         "cta_url": string | null   # fill when an explicit link provided, else null
      }
  ],
  "call_to_action": {
      "heading": string,
      "body": string,
      "button_label": string,
      "button_url": string
  },
  "section_suggestions": [
      {
          "type": string,               # semantic identifier e.g. "newsletter", "events"
          "label": string,              # short client-facing label
          "description": string,        # 1-2 sentence idea for the section content
          "include_by_default": boolean # true when this section should be pre-populated on the layout
      }
  ],
  "additional_sections": [
      {
          "type": string,           # e.g. "newsletter", "testimonials"
          "heading": string,
          "body": string,
          "items": [object]         # optional structured items (can be empty list)
      }
  ],
  "theme": {
      "primary_color": string,     # hex color
      "secondary_color": string,
      "accent_color": string
  }
}
Craft ~10 distinct section_suggestion entries (do NOT include a basic "Listen now" card) that a client could toggle on/off.
For any suggestion where include_by_default is true, add a corresponding entry to additional_sections so the preview feels complete.
Do not include Markdown fences or explanations—return JSON only.
""".strip()

_BASE_DOMAIN = settings.PODCAST_WEBSITE_BASE_DOMAIN.strip() or "podcastplusplus.com"
_PROMPT_BUCKET = settings.PODCAST_WEBSITE_GCS_BUCKET.strip() if settings.PODCAST_WEBSITE_GCS_BUCKET else ""
_CUSTOM_DOMAIN_MIN_TIER = settings.PODCAST_WEBSITE_CUSTOM_DOMAIN_MIN_TIER.strip().lower() or "pro"

_TIER_ORDER = ["free", "creator", "pro", "unlimited"]

DEFAULT_SECTION_SUGGESTIONS: List[Dict[str, Any]] = [
    {
        "type": "newsletter",
        "label": "Newsletter Sign-up",
        "description": "Collect emails from superfans who want updates and bonus content.",
        "include_by_default": True,
    },
    {
        "type": "testimonials",
        "label": "Listener Testimonials",
        "description": "Highlight quotes from reviews to build trust with newcomers.",
        "include_by_default": True,
    },
    {
        "type": "hosts",
        "label": "Meet the Hosts",
        "description": "Introduce each host with a short story that shows their personality.",
        "include_by_default": False,
    },
    {
        "type": "events",
        "label": "Upcoming Events",
        "description": "Promote live shows, AMAs, or conference appearances.",
        "include_by_default": False,
    },
    {
        "type": "community",
        "label": "Community Highlights",
        "description": "Feature fan art, shout-outs, or social media conversations.",
        "include_by_default": False,
    },
    {
        "type": "press",
        "label": "Press & Media",
        "description": "List notable press coverage and media kits for collaborators.",
        "include_by_default": False,
    },
    {
        "type": "sponsors",
        "label": "Sponsor Spotlight",
        "description": "Thank sponsors or partners and include calls-to-action for inquiries.",
        "include_by_default": False,
    },
    {
        "type": "resources",
        "label": "Resource Library",
        "description": "Share guides, downloads, or companion materials mentioned in episodes.",
        "include_by_default": False,
    },
    {
        "type": "faqs",
        "label": "FAQ",
        "description": "Answer the top questions new listeners and collaborators ask.",
        "include_by_default": False,
    },
    {
        "type": "support",
        "label": "Support the Show",
        "description": "Provide Patreon, merch, or donation links for fans who want to contribute.",
        "include_by_default": True,
    },
]


class PodcastWebsiteContent(BaseModel):
    """Lightweight typed representation of website content."""

    hero_title: str = ""
    hero_subtitle: str = ""
    hero_image_url: Optional[str] = None
    about: Dict[str, Any] = Field(default_factory=dict)
    hosts: List[Dict[str, str]] = Field(default_factory=list)
    episodes: List[Dict[str, Any]] = Field(default_factory=list)
    call_to_action: Dict[str, Any] = Field(default_factory=dict)
    section_suggestions: List[Dict[str, Any]] = Field(default_factory=list)
    additional_sections: List[Dict[str, Any]] = Field(default_factory=list)
    theme: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "ignore"


@dataclass
class WebsiteContext:
    podcast: Podcast
    host_names: List[str]
    episodes: List[Episode]
    base_domain: str = _BASE_DOMAIN
    cover_url: Optional[str] = None
    theme_colors: Dict[str, str] = field(default_factory=dict)

    def default_layout(self) -> Dict[str, Any]:
        """Fallback layout when AI output is incomplete."""

        primary_color = (self.theme_colors or {}).get("primary_color", "#1F2A44")
        secondary_color = (self.theme_colors or {}).get("secondary_color", "#F5F6FA")
        accent_color = (self.theme_colors or {}).get("accent_color", "#FF7A59")

        ep_cards = [
            {
                "episode_id": str(ep.id),
                "title": ep.title,
                "description": (ep.show_notes or "").strip()[:240] or "Listen to this episode to learn more.",
                "cta_label": "Play episode",
                "cta_url": None,
            }
            for ep in self.episodes[:3]
        ]
        return {
            "hero_title": self.podcast.name,
            "hero_subtitle": (self.podcast.description or "A podcast hosted on Podcast Plus Plus").strip(),
            "hero_image_url": self.cover_url,
            "about": {
                "heading": f"About {self.podcast.name}",
                "body": (self.podcast.description or "We're still learning about this show!").strip(),
            },
            "hosts": [
                {"name": name, "bio": ""}
                for name in self.host_names
            ] or [{"name": "Your Host", "bio": "Add host details by chatting with the builder."}],
            "episodes": ep_cards,
            "call_to_action": {
                "heading": "Subscribe for new episodes",
                "body": "Join the community and never miss a release.",
                "button_label": "Subscribe now",
                "button_url": f"https://{self.base_domain}",
            },
            "section_suggestions": [dict(section) for section in DEFAULT_SECTION_SUGGESTIONS],
            "additional_sections": [],
            "theme": {
                "primary_color": primary_color,
                "secondary_color": secondary_color,
                "accent_color": accent_color,
            },
        }


class PodcastWebsiteError(RuntimeError):
    """Base error for website builder operations."""


class PodcastWebsiteDomainError(PodcastWebsiteError):
    """Raised when a custom domain fails validation or entitlement checks."""


class PodcastWebsiteAIError(PodcastWebsiteError):
    """Raised when AI generation fails."""


def _slugify_base(name: str) -> str:
    base = "".join(ch if ch.isalnum() else "-" for ch in (name or "").lower())
    base = re.sub(r"-+", "-", base).strip("-")
    if not base:
        base = "podcast"
    return base[:40]


def _ensure_unique_subdomain(session: Session, desired: str, existing_id: Optional[UUID]) -> str:
    slug = desired
    counter = 1
    while True:
        stmt = select(PodcastWebsite).where(PodcastWebsite.subdomain == slug)
        match = session.exec(stmt).first()
        if match is None or (existing_id and match.id == existing_id):
            return slug
        counter += 1
        slug = f"{desired}-{counter}"


def _discover_hosts(podcast: Podcast, user: User) -> List[str]:
    names: List[str] = []
    for candidate in [
        podcast.owner_name,
        podcast.author_name,
        getattr(user, "first_name", None) and getattr(user, "last_name", None) and f"{user.first_name} {user.last_name}",
        getattr(user, "first_name", None),
        getattr(user, "last_name", None),
    ]:
        if candidate:
            cleaned = " ".join(str(candidate).split())
            if cleaned and cleaned not in names:
                names.append(cleaned)
    if not names and getattr(user, "email", None):
        names.append(user.email.split("@")[0].replace(".", " ").title())
    return names[:4]


def _fetch_recent_episodes(session: Session, podcast_id: UUID, limit: int = 6) -> List[Episode]:
    stmt = select(Episode).where(Episode.podcast_id == podcast_id).order_by(Episode.publish_at.desc(), Episode.created_at.desc()).limit(limit)
    episodes = session.exec(stmt).all()
    # SQLite treats NULL as largest when ordering desc, but to be safe sort in Python
    episodes.sort(key=lambda ep: (ep.publish_at or ep.created_at or datetime.min), reverse=True)
    return episodes


def _color_distance(c1: Tuple[int, int, int], c2: Tuple[int, int, int]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def _rgb_to_hex(color: Tuple[int, int, int]) -> str:
    r, g, b = color
    return f"#{r:02X}{g:02X}{b:02X}"


def _extract_theme_colors(image_bytes: bytes) -> Dict[str, str]:
    if Image is None:
        return {}
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("RGB")
            img.thumbnail((160, 160))
            pixels = list(img.getdata())
    except Exception as exc:  # pragma: no cover - pillow decoding failure
        log.debug("Failed to decode cover image for palette extraction: %s", exc)
        return {}

    if not pixels:
        return {}

    counts: Counter[Tuple[int, int, int]] = Counter(pixels)
    most_common = [color for color, _ in counts.most_common(32)]
    if not most_common:
        return {}

    primary = most_common[0]

    distinct: List[Tuple[int, int, int]] = [primary]
    for color in most_common[1:]:
        if all(_color_distance(color, existing) > 40 for existing in distinct):
            distinct.append(color)
        if len(distinct) >= 5:
            break

    secondary = distinct[1] if len(distinct) > 1 else primary

    def _saturation(color: Tuple[int, int, int]) -> float:
        r, g, b = (channel / 255.0 for channel in color)
        _, l, s = colorsys.rgb_to_hls(r, g, b)
        # prefer moderately bright colors for accents
        return (s * 0.7) + (1 - abs(0.5 - l)) * 0.3

    accent_candidates = [c for c in distinct[1:]] or most_common[1:]
    accent = None
    for candidate in accent_candidates:
        if _color_distance(candidate, primary) > 55 and _color_distance(candidate, secondary) > 40:
            accent = candidate
            break
    if accent is None and accent_candidates:
        accent = max(accent_candidates, key=_saturation)
    if accent is None:
        accent = primary

    return {
        "primary_color": _rgb_to_hex(primary),
        "secondary_color": _rgb_to_hex(secondary),
        "accent_color": _rgb_to_hex(accent),
    }


def _derive_visual_identity(podcast: Podcast) -> Tuple[Optional[str], Dict[str, str]]:
    cover_url = podcast.preferred_cover_url
    theme: Dict[str, str] = {}
    if not cover_url:
        return None, theme
    try:
        response = requests.get(cover_url, timeout=5)
        if response.status_code == 200 and response.content:
            palette = _extract_theme_colors(response.content)
            if palette:
                theme = palette
    except Exception as exc:  # pragma: no cover - network issues
        log.debug("Failed to fetch cover image for podcast %s: %s", podcast.id, exc)
    return cover_url, theme


def _build_context_prompt(ctx: WebsiteContext, include_layout: Optional[Dict[str, Any]] = None, user_request: Optional[str] = None) -> str:
    lines = [
        _SITE_SCHEMA_PROMPT,
        "",
        f"Podcast name: {ctx.podcast.name}",
        f"Podcast description: {ctx.podcast.description or 'Not provided'}",
        f"Hosts: {', '.join(ctx.host_names) if ctx.host_names else 'Unknown'}",
        "Episodes:",
    ]
    for ep in ctx.episodes:
        summary = (ep.show_notes or "").strip().replace("\n", " ")
        if len(summary) > 320:
            summary = summary[:320].rstrip() + "…"
        lines.append(f"- {ep.title} (id: {ep.id}) :: {summary or 'No summary yet.'}")
    lines.append("")
    lines.append(f"Base subdomain: https://{ctx.podcast.name.lower().replace(' ', '-')}.{ctx.base_domain}")
    if ctx.cover_url:
        lines.append(f"Podcast cover image URL: {ctx.cover_url}")
        if ctx.theme_colors:
            lines.append(
                "Suggested brand colors from the cover image: "
                f"primary={ctx.theme_colors.get('primary_color')}, "
                f"secondary={ctx.theme_colors.get('secondary_color')}, "
                f"accent={ctx.theme_colors.get('accent_color')}"
            )
    if include_layout:
        lines.append("Current website JSON:")
        lines.append(json.dumps(include_layout, indent=2))
    if user_request:
        lines.append("")
        lines.append("Apply this request:")
        lines.append(user_request.strip())
    lines.append("")
    lines.append("Return ONLY the JSON object, fully populated.")
    return "\n".join(lines)


def _invoke_site_builder(prompt: str) -> Dict[str, Any]:
    raw = client_gemini.generate(prompt, max_output_tokens=2048, temperature=0.75)
    if not raw:
        raise PodcastWebsiteAIError("Empty response from AI site builder")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Attempt to salvage JSON substring
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = raw[start : end + 1]
            try:
                return json.loads(snippet)
            except Exception as exc:  # pragma: no cover - defensive logging
                log.warning("Failed to parse JSON snippet from AI response: %s", exc)
        raise PodcastWebsiteAIError("AI response was not valid JSON")


def _normalize_layout(data: Dict[str, Any], ctx: WebsiteContext) -> PodcastWebsiteContent:
    baseline = ctx.default_layout()
    merged: Dict[str, Any] = {}

    merged["hero_title"] = str(data.get("hero_title") or baseline["hero_title"]).strip() or baseline["hero_title"]
    merged["hero_subtitle"] = str(data.get("hero_subtitle") or baseline["hero_subtitle"]).strip() or baseline["hero_subtitle"]
    hero_image_url = data.get("hero_image_url")
    if isinstance(hero_image_url, str) and hero_image_url.strip():
        merged["hero_image_url"] = hero_image_url.strip()
    else:
        merged["hero_image_url"] = baseline.get("hero_image_url")

    about = data.get("about") or {}
    if not isinstance(about, dict):
        about = {}
    merged["about"] = {
        "heading": str(about.get("heading") or baseline["about"]["heading"]).strip() or baseline["about"]["heading"],
        "body": str(about.get("body") or baseline["about"]["body"]).strip() or baseline["about"]["body"],
    }

    hosts: Iterable[Dict[str, str]] = []
    raw_hosts = data.get("hosts")
    if isinstance(raw_hosts, list):
        cleaned_hosts: List[Dict[str, str]] = []
        for item in raw_hosts:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            bio = str(item.get("bio") or "").strip()
            if name:
                cleaned_hosts.append({"name": name, "bio": bio})
        hosts = cleaned_hosts
    hosts_list = list(hosts)
    if not hosts_list:
        hosts_list = baseline["hosts"]
    merged["hosts"] = hosts_list[:4]

    raw_eps = data.get("episodes")
    episode_cards: List[Dict[str, Any]] = []
    if isinstance(raw_eps, list):
        for card in raw_eps:
            if not isinstance(card, dict):
                continue
            ep_id = str(card.get("episode_id") or "").strip() or None
            title = str(card.get("title") or "").strip()
            description = str(card.get("description") or "").strip()
            cta_label = str(card.get("cta_label") or "Play episode").strip() or "Play episode"
            cta_url = card.get("cta_url") if isinstance(card.get("cta_url"), str) else None
            if ep_id:
                episode_cards.append({
                    "episode_id": ep_id,
                    "title": title or "Untitled Episode",
                    "description": description or "Listen now to hear more.",
                    "cta_label": cta_label,
                    "cta_url": cta_url,
                })
    if not episode_cards:
        episode_cards = baseline["episodes"]
    merged["episodes"] = episode_cards[:6]

    raw_cta = data.get("call_to_action") if isinstance(data.get("call_to_action"), dict) else {}
    merged["call_to_action"] = {
        "heading": str(raw_cta.get("heading") or baseline["call_to_action"]["heading"]).strip() or baseline["call_to_action"]["heading"],
        "body": str(raw_cta.get("body") or baseline["call_to_action"]["body"]).strip() or baseline["call_to_action"]["body"],
        "button_label": str(raw_cta.get("button_label") or baseline["call_to_action"]["button_label"]).strip() or baseline["call_to_action"]["button_label"],
        "button_url": str(raw_cta.get("button_url") or baseline["call_to_action"]["button_url"]).strip() or baseline["call_to_action"]["button_url"],
    }

    raw_suggestions = data.get("section_suggestions")
    suggestions: List[Dict[str, Any]] = []
    if isinstance(raw_suggestions, list):
        for suggestion in raw_suggestions:
            if not isinstance(suggestion, dict):
                continue
            type_val = str(suggestion.get("type") or "custom").strip() or "custom"
            label_val = str(suggestion.get("label") or type_val.title()).strip()
            description_val = str(suggestion.get("description") or "").strip()
            include_val = bool(suggestion.get("include_by_default"))
            suggestions.append(
                {
                    "type": type_val,
                    "label": label_val,
                    "description": description_val,
                    "include_by_default": include_val,
                }
            )
    if not suggestions:
        suggestions = [dict(section) for section in DEFAULT_SECTION_SUGGESTIONS]
    merged["section_suggestions"] = suggestions[:12]

    raw_sections = data.get("additional_sections")
    sections: List[Dict[str, Any]] = []
    if isinstance(raw_sections, list):
        for section in raw_sections:
            if not isinstance(section, dict):
                continue
            type_val = str(section.get("type") or "custom").strip() or "custom"
            heading_val = str(section.get("heading") or "").strip()
            body_val = str(section.get("body") or "").strip()
            items_val = section.get("items") if isinstance(section.get("items"), list) else []
            sections.append({
                "type": type_val,
                "heading": heading_val,
                "body": body_val,
                "items": items_val,
            })
    if not sections:
        sections = [
            {
                "type": suggestion["type"],
                "heading": suggestion["label"],
                "body": suggestion.get("description", ""),
                "items": [],
            }
            for suggestion in suggestions
            if suggestion.get("include_by_default")
        ]
    merged["additional_sections"] = sections

    theme = data.get("theme") if isinstance(data.get("theme"), dict) else {}
    merged["theme"] = {
        "primary_color": str(theme.get("primary_color") or baseline["theme"]["primary_color"]).strip() or baseline["theme"]["primary_color"],
        "secondary_color": str(theme.get("secondary_color") or baseline["theme"]["secondary_color"]).strip() or baseline["theme"]["secondary_color"],
        "accent_color": str(theme.get("accent_color") or baseline["theme"]["accent_color"]).strip() or baseline["theme"]["accent_color"],
    }

    return PodcastWebsiteContent(**merged)


def _record_prompt_blob(podcast_id: UUID, website_id: UUID, payload: Dict[str, Any]) -> Optional[str]:
    if not _PROMPT_BUCKET:
        return None
    if storage is None:
        log.warning("google-cloud-storage not installed; skipping prompt archival for website %s", website_id)
        return None
    try:
        client = storage.Client()
        bucket = client.bucket(_PROMPT_BUCKET)
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
        path = f"prompts/{podcast_id}/{website_id}/{timestamp}.json"
        blob = bucket.blob(path)
        blob.upload_from_string(json.dumps(payload, ensure_ascii=False, indent=2), content_type="application/json")
        return f"gs://{_PROMPT_BUCKET}/{path}"
    except Exception as exc:  # pragma: no cover - network/cloud failure best effort
        log.warning("Failed to persist prompt log for website %s: %s", website_id, exc)
        return None


def _serialize_content(content: PodcastWebsiteContent) -> Dict[str, Any]:
    return content.model_dump(exclude_none=True)


def _tier_index(tier: str) -> int:
    t = (tier or "").lower()
    if t in _TIER_ORDER:
        return _TIER_ORDER.index(t)
    return -1


def is_custom_domain_allowed(user: User) -> bool:
    if getattr(user, "is_admin", False):
        return True
    min_idx = _tier_index(_CUSTOM_DOMAIN_MIN_TIER)
    if min_idx < 0:
        min_idx = _tier_index("pro")
    return _tier_index(getattr(user, "tier", "free")) >= min_idx


def validate_custom_domain(domain: str) -> str:
    cleaned = domain.strip().lower()
    if not cleaned:
        raise PodcastWebsiteDomainError("Custom domain cannot be empty")
    if len(cleaned) > 253:
        raise PodcastWebsiteDomainError("Custom domain is too long")
    if cleaned.endswith("." + _BASE_DOMAIN):
        raise PodcastWebsiteDomainError("Custom domain must be outside the managed base domain")
    pattern = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))*\.[a-z]{2,}$")
    if not pattern.match(cleaned):
        raise PodcastWebsiteDomainError("Custom domain format is invalid")
    return cleaned


def create_or_refresh_site(session: Session, podcast: Podcast, user: User) -> Tuple[PodcastWebsite, PodcastWebsiteContent]:
    website = session.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    desired_slug = _slugify_base(podcast.name)
    if website is None:
        unique_slug = _ensure_unique_subdomain(session, desired_slug, None)
        website = PodcastWebsite(
            podcast_id=podcast.id,
            user_id=user.id,
            subdomain=unique_slug,
        )

    if website.subdomain != desired_slug:
        # ensure slug remains unique even if podcast renamed
        website.subdomain = _ensure_unique_subdomain(session, desired_slug, website.id)

    cover_url, theme = _derive_visual_identity(podcast)
    ctx = WebsiteContext(
        podcast=podcast,
        host_names=_discover_hosts(podcast, user),
        episodes=_fetch_recent_episodes(session, podcast.id),
        cover_url=cover_url,
        theme_colors=theme,
    )

    prompt = _build_context_prompt(ctx)
    raw = _invoke_site_builder(prompt)
    content = _normalize_layout(raw, ctx)

    website.apply_layout(_serialize_content(content))
    website.status = PodcastWebsiteStatus.draft

    payload = {
        "type": "initial",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "prompt": prompt,
        "response": _serialize_content(content),
    }
    blob_path = _record_prompt_blob(podcast.id, website.id, payload)
    if blob_path:
        website.prompt_log_path = blob_path

    session.add(website)
    session.commit()
    session.refresh(website)
    return website, content


def apply_ai_update(session: Session, website: PodcastWebsite, podcast: Podcast, user: User, request_text: str) -> Tuple[PodcastWebsite, PodcastWebsiteContent]:
    if not request_text.strip():
        raise PodcastWebsiteAIError("Update request cannot be empty")

    cover_url, theme = _derive_visual_identity(podcast)
    ctx = WebsiteContext(
        podcast=podcast,
        host_names=_discover_hosts(podcast, user),
        episodes=_fetch_recent_episodes(session, podcast.id),
        cover_url=cover_url,
        theme_colors=theme,
    )

    current_layout = website.parsed_layout()
    prompt = _build_context_prompt(ctx, include_layout=current_layout, user_request=request_text)
    raw = _invoke_site_builder(prompt)
    content = _normalize_layout(raw, ctx)

    website.apply_layout(_serialize_content(content))

    payload = {
        "type": "update",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "prompt": prompt,
        "response": _serialize_content(content),
        "request": request_text,
    }
    blob_path = _record_prompt_blob(podcast.id, website.id, payload)
    if blob_path:
        website.prompt_log_path = blob_path

    session.add(website)
    session.commit()
    session.refresh(website)
    return website, content


def update_custom_domain(session: Session, website: PodcastWebsite, user: User, domain: Optional[str]) -> PodcastWebsite:
    if domain is None or domain == "":
        website.custom_domain = None
    else:
        if not is_custom_domain_allowed(user):
            raise PodcastWebsiteDomainError("Current plan does not allow custom domains")
        website.custom_domain = validate_custom_domain(domain)
    website.updated_at = datetime.utcnow()
    session.add(website)
    session.commit()
    session.refresh(website)
    return website


def get_default_domain(subdomain: str) -> str:
    return f"{subdomain}.{_BASE_DOMAIN}" if subdomain else _BASE_DOMAIN
