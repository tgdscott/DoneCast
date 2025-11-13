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
from api.services.ai_content import client_router as ai_client

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
    # PostgreSQL NULL ordering - sort in Python to ensure consistent behavior
    episodes.sort(key=lambda ep: (ep.publish_at or ep.created_at or datetime.min), reverse=True)
    return episodes


def _color_distance(c1: Tuple[int, int, int], c2: Tuple[int, int, int]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def _rgb_to_hex(color: Tuple[int, int, int]) -> str:
    r, g, b = color
    return f"#{r:02X}{g:02X}{b:02X}"


def _extract_theme_colors(image_bytes: bytes) -> Dict[str, str]:
    """Extract comprehensive color palette with accessibility and harmony."""
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
    
    # Calculate complementary text color for primary
    def _get_contrast_text(bg_color: Tuple[int, int, int]) -> str:
        """Get white or black text color based on background luminance."""
        r, g, b = (c / 255.0 for c in bg_color)
        # Calculate relative luminance (WCAG formula)
        luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
        # Use white text on dark backgrounds, black text on light backgrounds
        return "#ffffff" if luminance < 0.5 else "#1e293b"
    
    # Calculate background color (lightened version of secondary or white)
    def _lighten_color(color: Tuple[int, int, int], factor: float = 0.9) -> Tuple[int, int, int]:
        """Lighten a color by blending with white."""
        return tuple(min(255, int(c + (255 - c) * factor)) for c in color)
    
    background = _lighten_color(secondary, 0.95)
    
    # Detect mood based on color characteristics
    def _detect_mood(primary_rgb: Tuple[int, int, int]) -> str:
        r, g, b = (c / 255.0 for c in primary_rgb)
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        
        if s < 0.2:
            return "professional"
        elif s > 0.6 and l > 0.5:
            return "energetic"
        elif l < 0.4:
            return "sophisticated"
        elif h < 0.15 or h > 0.85:  # Red/orange tones
            return "warm"
        elif 0.4 < h < 0.7:  # Blue/green tones
            return "calm"
        else:
            return "balanced"
    
    mood = _detect_mood(primary)

    return {
        "primary_color": _rgb_to_hex(primary),
        "secondary_color": _rgb_to_hex(secondary),
        "accent_color": _rgb_to_hex(accent),
        "background_color": _rgb_to_hex(background),
        "text_color": _get_contrast_text(primary),
        "mood": mood,
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


def _analyze_podcast_content(podcast: Podcast, episodes: List[Episode]) -> Dict[str, Any]:
    """Deep analysis of podcast content to extract themes, patterns, and audience hints."""
    if not episodes:
        return {
            "total_episodes": 0,
            "publish_frequency": "irregular",
            "avg_episode_length": "unknown",
            "key_topics": [],
            "tone": "conversational",
        }
    
    # Calculate total episodes (may be more than what we fetched)
    total_episodes = len(episodes)
    
    # Analyze publish frequency
    if len(episodes) >= 3:
        dates = [ep.publish_at or ep.created_at for ep in episodes if ep.publish_at or ep.created_at]
        if len(dates) >= 2:
            dates_sorted = sorted(dates, reverse=True)
            avg_days_between = sum((dates_sorted[i] - dates_sorted[i+1]).days for i in range(len(dates_sorted)-1)) / (len(dates_sorted) - 1)
            if avg_days_between <= 1.5:
                publish_frequency = "daily"
            elif avg_days_between <= 8:
                publish_frequency = "weekly"
            elif avg_days_between <= 16:
                publish_frequency = "bi-weekly"
            elif avg_days_between <= 35:
                publish_frequency = "monthly"
            else:
                publish_frequency = "irregular"
        else:
            publish_frequency = "irregular"
    else:
        publish_frequency = "new show"
    
    # Extract keywords from titles and show notes
    all_text = " ".join([
        (ep.title or "") + " " + (ep.show_notes or "")[:500]
        for ep in episodes
    ]).lower()
    
    # Simple keyword extraction (you could use spaCy/NLTK here for better results)
    common_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "from", "about", "as", "is", "was", "are", "were", "been", "be", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "can", "this", "that", "these", "those", "i", "you", "he", "she", "it", "we", "they", "them", "our", "your", "his", "her", "its", "their", "what", "which", "who", "when", "where", "why", "how"}
    words = [w.strip(".,!?;:\"'()[]{}") for w in all_text.split() if len(w) > 3 and w.strip(".,!?;:\"'()[]{}") not in common_words]
    word_freq = Counter(words)
    key_topics = [word for word, count in word_freq.most_common(10) if count >= 2][:5]
    
    # Detect tone from description and episode titles
    tone_words = {
        "educational": ["learn", "tutorial", "guide", "how", "lesson", "teach", "explain", "introduction", "beginner"],
        "conversational": ["chat", "talk", "discussion", "conversation", "interview", "guest", "episode"],
        "professional": ["business", "industry", "professional", "enterprise", "corporate", "strategy", "analysis"],
        "entertaining": ["fun", "comedy", "laugh", "entertainment", "hilarious", "funny", "story", "adventure"],
    }
    tone_scores = {tone: sum(1 for word in all_text.split() if word in keywords) for tone, keywords in tone_words.items()}
    tone = max(tone_scores.items(), key=lambda x: x[1])[0] if max(tone_scores.values()) > 0 else "conversational"
    
    # Estimate average episode length (if we had duration data)
    avg_episode_length = "45 minutes"  # Default estimate
    
    # Check if there's category/genre information
    category = getattr(podcast, "category", None) or "General"
    
    return {
        "total_episodes": total_episodes,
        "publish_frequency": publish_frequency,
        "avg_episode_length": avg_episode_length,
        "key_topics": key_topics,
        "tone": tone,
        "category": category,
    }


def _build_context_prompt(ctx: WebsiteContext, include_layout: Optional[Dict[str, Any]] = None, user_request: Optional[str] = None) -> str:
    # Analyze content for richer context
    content_analysis = _analyze_podcast_content(ctx.podcast, ctx.episodes)
    
    lines = [
        _SITE_SCHEMA_PROMPT,
        "",
        f"Podcast name: {ctx.podcast.name}",
        f"Podcast description: {ctx.podcast.description or 'Not provided'}",
        f"Hosts: {', '.join(ctx.host_names) if ctx.host_names else 'Unknown'}",
        f"Total episodes: {content_analysis['total_episodes']}",
        f"Publish frequency: {content_analysis['publish_frequency']}",
        f"Content tone: {content_analysis['tone']}",
        f"Key topics: {', '.join(content_analysis['key_topics']) if content_analysis['key_topics'] else 'varied'}",
        "",
        "Recent Episodes:",
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
            mood = ctx.theme_colors.get('mood', 'balanced')
            lines.append(
                "Suggested brand colors from the cover image: "
                f"primary={ctx.theme_colors.get('primary_color')}, "
                f"secondary={ctx.theme_colors.get('secondary_color')}, "
                f"accent={ctx.theme_colors.get('accent_color')}, "
                f"mood={mood}"
            )
            lines.append(
                f"Design hint: The cover art suggests a '{mood}' aesthetic. "
                "Craft copy and section suggestions that complement this visual tone."
            )
    
    # Add content-aware prompts
    if content_analysis['publish_frequency'] in ['daily', 'weekly']:
        lines.append(f"Note: This is a {content_analysis['publish_frequency']} show. Emphasize consistency and regular listening habits in CTAs.")
    
    if content_analysis['total_episodes'] > 50:
        lines.append(f"Note: With {content_analysis['total_episodes']}+ episodes, highlight the depth of content available.")
    elif content_analysis['total_episodes'] < 10:
        lines.append("Note: This is a new show. Focus CTAs on 'join early' and 'be part of the journey' messaging.")
    
    if include_layout:
        lines.append("")
        lines.append("Current website JSON:")
        lines.append(json.dumps(include_layout, indent=2))
    if user_request:
        lines.append("")
        lines.append("Apply this request:")
        lines.append(user_request.strip())
    lines.append("")
    lines.append("Return ONLY the JSON object, fully populated with rich, personalized content based on the analysis above.")
    return "\n".join(lines)


def _invoke_site_builder(prompt: str) -> Dict[str, Any]:
    try:
        raw = ai_client.generate(prompt, max_output_tokens=2048, temperature=0.75)
    except Exception as exc:
        log.exception("AI client generate() failed: %s", exc)
        raise PodcastWebsiteAIError(f"AI service unavailable: {str(exc)}")
    
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
        log.error("AI response was not valid JSON. Raw response (first 500 chars): %s", raw[:500])
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


def _hex_to_rgb_tuple(hex_color: str):
    """Parse hex color to RGB tuple."""
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return (r, g, b)


def _adjust_color_brightness(hex_color: str, factor: float) -> str:
    """Adjust color brightness. factor > 1 = lighter, factor < 1 = darker"""
    r, g, b = _hex_to_rgb_tuple(hex_color)
    r = min(255, int(r * factor))
    g = min(255, int(g * factor))
    b = min(255, int(b * factor))
    return f"#{r:02x}{g:02x}{b:02x}"


def _generate_css_from_theme(theme: Dict[str, str], podcast_name: str) -> str:
    """Generate custom CSS based on theme colors with enhanced accessibility and typography."""
    primary = theme.get("primary_color", "#0f172a")
    secondary = theme.get("secondary_color", "#ffffff")
    accent = theme.get("accent_color", "#2563eb")
    background = theme.get("background_color", "#f8fafc")
    text_color = theme.get("text_color", "#ffffff")
    mood = theme.get("mood", "balanced")
    
    # Generate color variants
    primary_light = _adjust_color_brightness(primary, 1.2)
    primary_dark = _adjust_color_brightness(primary, 0.8)
    accent_light = _adjust_color_brightness(accent, 1.15)
    accent_hover = _adjust_color_brightness(accent, 0.9)
    
    # Surface colors for cards and sections
    surface_color = _adjust_color_brightness(background, 0.98)
    
    # Select typography based on mood
    if mood in ["professional", "sophisticated"]:
        font_heading = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
        font_body = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    elif mood in ["warm", "energetic"]:
        font_heading = "'Poppins', 'Inter', sans-serif"
        font_body = "'Open Sans', 'Inter', sans-serif"
    elif mood == "calm":
        font_heading = "'Merriweather', Georgia, serif"
        font_body = "'Source Sans Pro', 'Inter', sans-serif"
    else:
        font_heading = "'Inter', sans-serif"
        font_body = "'Inter', sans-serif"
    
    css = f"""/* Auto-generated CSS for {podcast_name} */
/* Theme colors extracted from podcast cover art - Mood: {mood} */

:root {{
  /* Primary palette */
  --color-primary: {primary};
  --color-primary-light: {primary_light};
  --color-primary-dark: {primary_dark};
  --color-primary-contrast: {text_color};
  
  /* Secondary & backgrounds */
  --color-secondary: {secondary};
  --color-background: {background};
  --color-surface: {surface_color};
  
  /* Accent & interactive */
  --color-accent: {accent};
  --color-accent-light: {accent_light};
  --color-accent-hover: {accent_hover};
  
  /* Text hierarchy */
  --color-text-primary: #1e293b;
  --color-text-secondary: #475569;
  --color-text-muted: #94a3b8;
  
  /* Typography */
  --font-heading: {font_heading};
  --font-body: {font_body};
  
  /* Spacing scale */
  --space-xs: 0.5rem;
  --space-sm: 0.75rem;
  --space-md: 1rem;
  --space-lg: 1.5rem;
  --space-xl: 2rem;
  --space-2xl: 3rem;
  
  /* Border radius */
  --radius-sm: 0.375rem;
  --radius-md: 0.5rem;
  --radius-lg: 0.75rem;
  --radius-xl: 1rem;
  
  /* Shadows */
  --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
  --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
  --shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
}}

body {{
  font-family: var(--font-body);
  color: var(--color-text-primary);
  background: linear-gradient(135deg, var(--color-background) 0%, var(--color-primary-light) 100%);
  min-height: 100vh;
  line-height: 1.6;
}}

.website-header {{
  background: var(--color-primary);
  color: var(--color-primary-contrast);
  box-shadow: var(--shadow-md);
  padding: var(--space-lg) var(--space-xl);
}}

.website-footer {{
  background: var(--color-primary-dark);
  color: var(--color-primary-contrast);
  padding: var(--space-2xl) var(--space-xl);
  margin-top: var(--space-2xl);
}}

.section-container {{
  background: var(--color-surface);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  margin: var(--space-xl) auto;
  max-width: 1200px;
  padding: var(--space-xl);
}}

.cta-button {{
  background: var(--color-accent);
  color: white;
  padding: var(--space-md) var(--space-lg);
  border-radius: var(--radius-md);
  font-weight: 600;
  font-family: var(--font-heading);
  transition: all 0.2s ease;
  border: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
}}

.cta-button:hover {{
  background: var(--color-accent-hover);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}}

.cta-button:active {{
  transform: translateY(0);
}}

.episode-card {{
  border: 2px solid var(--color-accent-light);
  border-radius: var(--radius-lg);
  padding: var(--space-lg);
  transition: all 0.3s ease;
  background: white;
  margin-bottom: var(--space-md);
}}

.episode-card:hover {{
  border-color: var(--color-accent);
  box-shadow: var(--shadow-lg);
  transform: translateY(-4px);
}}

h1, h2, h3, h4, h5, h6 {{
  color: var(--color-primary);
  font-family: var(--font-heading);
  line-height: 1.2;
  margin-bottom: var(--space-md);
}}

h1 {{
  font-size: 2.5rem;
  font-weight: 700;
}}

h2 {{
  font-size: 2rem;
  font-weight: 600;
}}

h3 {{
  font-size: 1.5rem;
  font-weight: 600;
}}

p {{
  margin-bottom: var(--space-md);
  color: var(--color-text-secondary);
}}

a {{
  color: var(--color-accent);
  text-decoration: none;
  transition: color 0.2s ease;
}}

a:hover {{
  color: var(--color-accent-hover);
  text-decoration: underline;
}}

.subscribe-link {{
  display: inline-flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: var(--color-accent-light);
  color: var(--color-primary-dark);
  border-radius: var(--radius-md);
  transition: all 0.2s ease;
  font-weight: 500;
}}

.subscribe-link:hover {{
  background: var(--color-accent);
  color: white;
  text-decoration: none;
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}}

.podcast-stats {{
  display: flex;
  gap: var(--space-lg);
  margin: var(--space-lg) 0;
  flex-wrap: wrap;
}}

.stat-item {{
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-md);
  background: white;
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  min-width: 120px;
}}

.stat-value {{
  font-size: 2rem;
  font-weight: 700;
  color: var(--color-accent);
  font-family: var(--font-heading);
}}

.stat-label {{
  font-size: 0.875rem;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}

/* Responsive design */
@media (max-width: 768px) {{
  .section-container {{
    margin: var(--space-md);
    padding: var(--space-md);
  }}
  
  h1 {{
    font-size: 2rem;
  }}
  
  h2 {{
    font-size: 1.5rem;
  }}
  
  .podcast-stats {{
    gap: var(--space-md);
  }}
}}
"""
    return css


def _create_default_sections(podcast: Podcast, cover_url: Optional[str], theme: Optional[Dict[str, str]] = None):
    """Create default section configuration for new websites.
    
    Args:
        podcast: Podcast model
        cover_url: URL to podcast cover art
        theme: Theme colors extracted from cover art
    
    Returns:
        Tuple of (sections_order, sections_config, sections_enabled)
    """
    # Use theme colors if available, otherwise use defaults
    if theme:
        primary_color = theme.get("primary_color", "#0f172a")
        secondary_color = theme.get("secondary_color", "#ffffff")
        accent_color = theme.get("accent_color", "#2563eb")
        background_color = theme.get("background_color", "#f8fafc")
        text_color = theme.get("text_color", "#ffffff")
    else:
        primary_color = "#0f172a"
        secondary_color = "#ffffff"
        accent_color = "#2563eb"
        background_color = "#f8fafc"
        text_color = "#ffffff"
    
    sections_order = ["header", "hero", "about", "latest-episodes", "subscribe", "footer"]
    
    sections_config = {
        "header": {
            "type": "header",
            "logo_type": "image" if cover_url else "text",
            "logo_url": cover_url,
            "logo_text": podcast.name,
            "height": "normal",
            "show_logo": True,
            "show_navigation": True,
            "show_player": False,
            "background_color": "#ffffff",
            "text_color": primary_color,
            "show_shadow": True,
        },
        "hero": {
            "type": "hero",
            "title": podcast.name,
            "subtitle": podcast.description or "Welcome to our podcast",
            "cta_text": "Listen Now",
            "cta_url": None,
            "background_color": primary_color,
            "text_color": text_color,
            "show_cover_art": True,
        },
        "about": {
            "type": "about",
            "heading": f"About {podcast.name}",
            "body": podcast.description or "Tell your listeners what your podcast is about.",
        },
        "latest-episodes": {
            "type": "episodes",
            "heading": "Latest Episodes",
            "count": 3,
            "show_descriptions": True,
            "show_dates": True,
            "layout": "cards",
        },
        "subscribe": {
            "type": "subscribe",
            "heading": "Subscribe & Listen",
            "rss_url": podcast.rss_url,
            "show_rss": True,
            "layout": "icons",
        },
        "footer": {
            "type": "footer",
            "layout": "columns",
            "show_social_links": True,
            "show_subscribe_links": True,
            "copyright_text": f"© {datetime.utcnow().year} {podcast.name}. All rights reserved.",
            "background_color": primary_color,
            "text_color": text_color,
        },
    }
    
    sections_enabled = {
        "header": True,
        "hero": True,
        "about": True,
        "latest-episodes": True,
        "subscribe": True,
        "footer": True,
    }
    
    return sections_order, sections_config, sections_enabled


def create_or_refresh_site(session: Session, podcast: Podcast, user: User) -> Tuple[PodcastWebsite, PodcastWebsiteContent]:
    website = session.exec(select(PodcastWebsite).where(PodcastWebsite.podcast_id == podcast.id)).first()
    desired_slug = _slugify_base(podcast.name)
    is_new_website = website is None
    
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
    
    # For new websites, set up default sections and generate AI theme
    if is_new_website or not website.get_sections_order():
        sections_order, sections_config, sections_enabled = _create_default_sections(podcast, cover_url, theme)
        website.set_sections_order(sections_order)
        website.set_sections_config(sections_config)
        website.set_sections_enabled(sections_enabled)
        
        # Auto-generate AI theme for new websites
        try:
            from api.services.ai_theme_generator import generate_complete_theme
            if generate_complete_theme is not None:
                log.info("Auto-generating AI theme for new website")
                theme_result = generate_complete_theme(podcast, cover_url, None)
                
                # Merge theme into sections config (don't overwrite existing)
                current_config = website.get_sections_config()
                for section_id, section_config in theme_result.sections_config.get("sections_config", {}).items():
                    if section_id not in current_config:
                        current_config[section_id] = section_config
                    elif section_id == "_theme_metadata":
                        # Always include theme metadata
                        current_config[section_id] = section_config
                
                website.set_sections_config(current_config)
                
                # Apply theme CSS (merge with existing if any)
                if theme_result.css:
                    website.global_css = theme_result.css
        except Exception as e:
            log.warning("Failed to auto-generate AI theme (non-fatal): %s", e)
    
    # Only regenerate CSS from theme colors if no AI theme CSS exists
    # This preserves AI-generated themes when user clicks "Regenerate"
    if not website.global_css or not website.get_sections_config().get("_theme_metadata"):
        # ALWAYS regenerate CSS from theme colors (so colors update when user clicks "Regenerate")
        # If theme extraction failed, use default colors but still generate CSS
        if theme:
            css = _generate_css_from_theme(theme, podcast.name)
        else:
            # Fallback to default theme if extraction failed
            default_theme = {
                "primary_color": "#0f172a",
                "secondary_color": "#ffffff",
                "accent_color": "#2563eb",
                "background_color": "#f8fafc",
                "text_color": "#ffffff",
                "mood": "balanced",
            }
            css = _generate_css_from_theme(default_theme, podcast.name)
        website.global_css = css

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


def generate_css_with_ai(podcast: Podcast, theme: Dict[str, str], user_prompt: str) -> str:
    """Use AI to generate custom CSS based on user's request and theme colors."""
    primary = theme.get("primary_color", "#0f172a")
    secondary = theme.get("secondary_color", "#ffffff")
    accent = theme.get("accent_color", "#2563eb")
    
    prompt = f"""You are a CSS expert. Generate clean, modern CSS for a podcast website.

Podcast: {podcast.name}
Description: {podcast.description or 'N/A'}

Current theme colors:
- Primary: {primary}
- Secondary: {secondary}
- Accent: {accent}

User request: {user_prompt}

Generate complete CSS that:
1. Uses the theme colors appropriately
2. Follows the user's request
3. Is modern, clean, and accessible
4. Works well with Tailwind CSS base styles
5. Includes responsive design considerations

Return ONLY the CSS code, no explanations or markdown fences."""

    try:
        css = ai_client.generate(prompt, max_output_tokens=2048, temperature=0.7)
        
        # Remove markdown code fences if present
        if css.startswith("```css"):
            css = css[6:]
        elif css.startswith("```"):
            css = css[3:]
        if css.endswith("```"):
            css = css[:-3]
        
        return css.strip()
    except Exception as exc:
        log.exception("Failed to generate CSS with AI: %s", exc)
        raise PodcastWebsiteAIError(f"AI CSS generation failed: {exc}")
