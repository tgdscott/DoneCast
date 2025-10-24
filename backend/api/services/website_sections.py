"""
Website section definitions and configuration schema.

Each section type defines:
- Metadata (label, category, icon)
- Configuration fields (required/optional)
- Default values
- AI refinement hints
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class SectionFieldDefinition(BaseModel):
    """Configuration field for a section."""
    
    name: str
    type: Literal["text", "textarea", "url", "image", "select", "multiselect", "toggle", "color", "number"]
    label: str
    placeholder: Optional[str] = None
    default: Any = None
    options: Optional[List[str]] = None  # for select/multiselect
    validation_pattern: Optional[str] = None  # regex pattern
    help_text: Optional[str] = None
    required: bool = False


class SectionDefinition(BaseModel):
    """Definition of a website section type."""
    
    id: str
    label: str
    category: Literal["layout", "core", "content", "marketing", "community", "advanced"]
    icon: str  # lucide-react icon name
    description: str
    default_enabled: bool = False
    order_priority: int = 100  # lower numbers appear first in palette
    behavior: Optional[Literal["sticky", "fixed", "normal"]] = "normal"  # Layout behavior
    required_fields: List[SectionFieldDefinition] = Field(default_factory=list)
    optional_fields: List[SectionFieldDefinition] = Field(default_factory=list)
    ai_prompt_hints: List[str] = Field(default_factory=list)
    preview_image_url: Optional[str] = None  # optional screenshot/mockup


# ============================================================================
# LAYOUT SECTIONS (Headers & Footers)
# ============================================================================

SECTION_HEADER = SectionDefinition(
    id="header",
    label="Site Header",
    category="layout",
    icon="LayoutDashboard",
    description="Persistent header with logo, navigation, and optional audio player",
    default_enabled=True,
    order_priority=1,  # Always first
    behavior="sticky",  # Stays at top when scrolling
    required_fields=[],
    optional_fields=[
        SectionFieldDefinition(
            name="show_logo",
            type="toggle",
            label="Show Logo",
            default=True,
        ),
        SectionFieldDefinition(
            name="logo_url",
            type="image",
            label="Logo Image",
            help_text="Custom logo (uses podcast cover if not set)",
        ),
        SectionFieldDefinition(
            name="logo_text",
            type="text",
            label="Logo Text",
            placeholder="Podcast Name",
            help_text="Alternative to logo image",
        ),
        SectionFieldDefinition(
            name="show_navigation",
            type="toggle",
            label="Show Navigation Menu",
            default=True,
            help_text="Links to different pages (for multi-page sites)",
        ),
        SectionFieldDefinition(
            name="show_player",
            type="toggle",
            label="Show Audio Player",
            default=False,
            help_text="Compact player that persists across navigation",
        ),
        SectionFieldDefinition(
            name="player_position",
            type="select",
            label="Player Position",
            options=["left", "center", "right"],
            default="right",
        ),
        SectionFieldDefinition(
            name="background_color",
            type="color",
            label="Background Color",
            default="#ffffff",
        ),
        SectionFieldDefinition(
            name="text_color",
            type="color",
            label="Text Color",
            default="#1e293b",
        ),
        SectionFieldDefinition(
            name="height",
            type="select",
            label="Header Height",
            options=["compact", "normal", "tall"],
            default="normal",
        ),
        SectionFieldDefinition(
            name="show_shadow",
            type="toggle",
            label="Show Drop Shadow",
            default=True,
        ),
    ],
    ai_prompt_hints=[
        "Design a clean, professional header that matches the podcast brand",
        "Suggest navigation menu items based on the podcast content",
        "Consider whether a persistent player enhances user experience",
    ],
)

SECTION_FOOTER = SectionDefinition(
    id="footer",
    label="Site Footer",
    category="layout",
    icon="PanelBottom",
    description="Bottom section with social links, copyright, and additional navigation",
    default_enabled=True,
    order_priority=999,  # Always last
    behavior="normal",  # Scrolls with page
    required_fields=[],
    optional_fields=[
        SectionFieldDefinition(
            name="show_social_links",
            type="toggle",
            label="Show Social Media Links",
            default=True,
        ),
        SectionFieldDefinition(
            name="social_platforms",
            type="multiselect",
            label="Social Platforms",
            options=["twitter", "facebook", "instagram", "youtube", "tiktok", "linkedin", "threads", "mastodon"],
            default=["twitter", "instagram", "youtube"],
        ),
        SectionFieldDefinition(
            name="twitter_url",
            type="url",
            label="Twitter/X URL",
            placeholder="https://twitter.com/yourpodcast",
        ),
        SectionFieldDefinition(
            name="facebook_url",
            type="url",
            label="Facebook URL",
            placeholder="https://facebook.com/yourpodcast",
        ),
        SectionFieldDefinition(
            name="instagram_url",
            type="url",
            label="Instagram URL",
            placeholder="https://instagram.com/yourpodcast",
        ),
        SectionFieldDefinition(
            name="youtube_url",
            type="url",
            label="YouTube URL",
            placeholder="https://youtube.com/@yourpodcast",
        ),
        SectionFieldDefinition(
            name="tiktok_url",
            type="url",
            label="TikTok URL",
            placeholder="https://tiktok.com/@yourpodcast",
        ),
        SectionFieldDefinition(
            name="linkedin_url",
            type="url",
            label="LinkedIn URL",
            placeholder="https://linkedin.com/company/yourpodcast",
        ),
        SectionFieldDefinition(
            name="show_subscribe_links",
            type="toggle",
            label="Show Podcast Subscribe Links",
            default=True,
            help_text="Links to Apple Podcasts, Spotify, etc.",
        ),
        SectionFieldDefinition(
            name="copyright_text",
            type="text",
            label="Copyright Text",
            placeholder="© 2025 Your Podcast Name. All rights reserved.",
        ),
        SectionFieldDefinition(
            name="show_privacy_links",
            type="toggle",
            label="Show Privacy/Terms Links",
            default=False,
        ),
        SectionFieldDefinition(
            name="privacy_url",
            type="url",
            label="Privacy Policy URL",
            placeholder="https://yoursite.com/privacy",
        ),
        SectionFieldDefinition(
            name="terms_url",
            type="url",
            label="Terms of Service URL",
            placeholder="https://yoursite.com/terms",
        ),
        SectionFieldDefinition(
            name="background_color",
            type="color",
            label="Background Color",
            default="#f8fafc",
        ),
        SectionFieldDefinition(
            name="text_color",
            type="color",
            label="Text Color",
            default="#64748b",
        ),
        SectionFieldDefinition(
            name="layout",
            type="select",
            label="Footer Layout",
            options=["simple", "columns", "centered"],
            default="columns",
        ),
    ],
    ai_prompt_hints=[
        "Suggest relevant social media platforms based on podcast content",
        "Generate appropriate copyright text with current year",
        "Recommend footer layout that matches the site design",
    ],
)


# ============================================================================
# TIER 1: CORE SECTIONS (Required)
# ============================================================================

SECTION_HERO = SectionDefinition(
    id="hero",
    label="Hero Section",
    category="core",
    icon="Sparkles",
    description="Large header with podcast name, tagline, and primary call-to-action",
    default_enabled=True,
    order_priority=10,
    required_fields=[
        SectionFieldDefinition(
            name="title",
            type="text",
            label="Headline",
            placeholder="Your Podcast Name",
            required=True,
        ),
        SectionFieldDefinition(
            name="subtitle",
            type="textarea",
            label="Tagline",
            placeholder="A catchy description that hooks listeners",
            required=True,
        ),
    ],
    optional_fields=[
        SectionFieldDefinition(
            name="cta_text",
            type="text",
            label="Button Text",
            placeholder="Listen Now",
            default="Listen Now",
        ),
        SectionFieldDefinition(
            name="cta_url",
            type="url",
            label="Button Link",
            placeholder="https://...",
        ),
        SectionFieldDefinition(
            name="background_color",
            type="color",
            label="Background Color",
            default="#1e293b",
        ),
        SectionFieldDefinition(
            name="text_color",
            type="color",
            label="Text Color",
            default="#ffffff",
        ),
        SectionFieldDefinition(
            name="background_image",
            type="image",
            label="Background Image",
            help_text="Optional hero background (will overlay with color)",
        ),
        SectionFieldDefinition(
            name="show_cover_art",
            type="toggle",
            label="Show Podcast Cover Art",
            default=True,
        ),
    ],
    ai_prompt_hints=[
        "Create an attention-grabbing headline that summarizes the podcast's unique value",
        "Write a subtitle that clearly explains what listeners will get",
        "Suggest CTA text that drives subscriptions or plays",
    ],
)

SECTION_ABOUT = SectionDefinition(
    id="about",
    label="About the Show",
    category="core",
    icon="Info",
    description="Overview of your podcast concept and target audience",
    default_enabled=True,
    order_priority=11,
    required_fields=[
        SectionFieldDefinition(
            name="heading",
            type="text",
            label="Section Heading",
            placeholder="About the Show",
            required=True,
        ),
        SectionFieldDefinition(
            name="body",
            type="textarea",
            label="Description",
            placeholder="Tell listeners what your podcast is about...",
            required=True,
            help_text="Markdown supported (bold, italic, links)",
        ),
    ],
    optional_fields=[
        SectionFieldDefinition(
            name="image",
            type="image",
            label="Section Image",
            help_text="Optional visual to accompany the description",
        ),
        SectionFieldDefinition(
            name="layout",
            type="select",
            label="Layout Style",
            options=["text-only", "image-left", "image-right"],
            default="text-only",
        ),
    ],
    ai_prompt_hints=[
        "Expand the description with SEO-friendly keywords",
        "Explain the target audience and value proposition",
        "Add information about episode format and schedule",
    ],
)

SECTION_LATEST_EPISODES = SectionDefinition(
    id="latest-episodes",
    label="Latest Episodes",
    category="core",
    icon="Radio",
    description="Display recent episodes with play buttons and descriptions",
    default_enabled=True,
    order_priority=12,
    required_fields=[
        SectionFieldDefinition(
            name="count",
            type="number",
            label="Number of Episodes",
            default=3,
            required=True,
        ),
    ],
    optional_fields=[
        SectionFieldDefinition(
            name="heading",
            type="text",
            label="Section Heading",
            placeholder="Latest Episodes",
            default="Latest Episodes",
        ),
        SectionFieldDefinition(
            name="layout",
            type="select",
            label="Layout Style",
            options=["list", "grid", "cards"],
            default="cards",
        ),
        SectionFieldDefinition(
            name="show_descriptions",
            type="toggle",
            label="Show Episode Descriptions",
            default=True,
        ),
        SectionFieldDefinition(
            name="show_dates",
            type="toggle",
            label="Show Publish Dates",
            default=True,
        ),
    ],
    ai_prompt_hints=[
        "Write engaging episode descriptions that encourage listening",
        "Generate compelling teaser copy for each episode",
    ],
)

SECTION_SUBSCRIBE = SectionDefinition(
    id="subscribe",
    label="Subscribe Links",
    category="core",
    icon="Rss",
    description="Platform links for subscribing (Apple Podcasts, Spotify, etc.)",
    default_enabled=True,
    order_priority=13,
    required_fields=[],
    optional_fields=[
        SectionFieldDefinition(
            name="heading",
            type="text",
            label="Section Heading",
            placeholder="Subscribe & Listen",
            default="Subscribe & Listen",
        ),
        SectionFieldDefinition(
            name="apple_podcasts_url",
            type="url",
            label="Apple Podcasts URL",
            placeholder="https://podcasts.apple.com/...",
        ),
        SectionFieldDefinition(
            name="spotify_url",
            type="url",
            label="Spotify URL",
            placeholder="https://open.spotify.com/show/...",
        ),
        SectionFieldDefinition(
            name="google_podcasts_url",
            type="url",
            label="Google Podcasts URL",
            placeholder="https://podcasts.google.com/...",
        ),
        SectionFieldDefinition(
            name="youtube_url",
            type="url",
            label="YouTube URL",
            placeholder="https://youtube.com/@...",
        ),
        SectionFieldDefinition(
            name="rss_url",
            type="url",
            label="RSS Feed URL",
            help_text="Auto-filled from your podcast RSS feed",
        ),
        SectionFieldDefinition(
            name="show_rss",
            type="toggle",
            label="Show RSS Feed Link",
            default=True,
        ),
        SectionFieldDefinition(
            name="layout",
            type="select",
            label="Layout Style",
            options=["buttons", "icons", "icon-grid"],
            default="icons",
        ),
    ],
    ai_prompt_hints=[
        "Suggest compelling CTA text for subscription section",
    ],
)


# ============================================================================
# TIER 2: RECOMMENDED SECTIONS
# ============================================================================

SECTION_HOSTS = SectionDefinition(
    id="hosts",
    label="Meet the Hosts",
    category="content",
    icon="Users",
    description="Introduce your podcast hosts with photos and bios",
    default_enabled=True,
    order_priority=20,
    required_fields=[],
    optional_fields=[
        SectionFieldDefinition(
            name="heading",
            type="text",
            label="Section Heading",
            placeholder="Meet the Hosts",
            default="Meet the Hosts",
        ),
        # Note: hosts array is dynamically managed via separate API
    ],
    ai_prompt_hints=[
        "Write engaging host bios that showcase personality",
        "Include relevant expertise and background",
        "Add personal touches that help listeners connect",
    ],
)

SECTION_NEWSLETTER = SectionDefinition(
    id="newsletter",
    label="Newsletter Sign-Up",
    category="marketing",
    icon="Mail",
    description="Email capture form for listener updates",
    default_enabled=True,
    order_priority=21,
    required_fields=[
        SectionFieldDefinition(
            name="form_action_url",
            type="url",
            label="Form Action URL",
            placeholder="https://your-email-service.com/subscribe",
            required=True,
            help_text="Your email service provider's form endpoint",
        ),
    ],
    optional_fields=[
        SectionFieldDefinition(
            name="heading",
            type="text",
            label="Heading",
            placeholder="Stay in the Loop",
            default="Stay in the Loop",
        ),
        SectionFieldDefinition(
            name="description",
            type="textarea",
            label="Description",
            placeholder="Get episode updates, behind-the-scenes content, and exclusive offers.",
        ),
        SectionFieldDefinition(
            name="button_text",
            type="text",
            label="Button Text",
            placeholder="Subscribe",
            default="Subscribe",
        ),
        SectionFieldDefinition(
            name="privacy_url",
            type="url",
            label="Privacy Policy URL",
            placeholder="https://yoursite.com/privacy",
        ),
    ],
    ai_prompt_hints=[
        "Write compelling value propositions for newsletter subscribers",
        "Highlight exclusive benefits of subscribing",
    ],
)

SECTION_TESTIMONIALS = SectionDefinition(
    id="testimonials",
    label="Listener Testimonials",
    category="marketing",
    icon="Quote",
    description="Showcase positive reviews and listener feedback",
    default_enabled=True,
    order_priority=22,
    required_fields=[],
    optional_fields=[
        SectionFieldDefinition(
            name="heading",
            type="text",
            label="Section Heading",
            placeholder="What Listeners Are Saying",
            default="What Listeners Are Saying",
        ),
        SectionFieldDefinition(
            name="layout",
            type="select",
            label="Layout Style",
            options=["carousel", "grid", "stacked"],
            default="grid",
        ),
        # Note: testimonials array is dynamically managed via separate API
    ],
    ai_prompt_hints=[
        "Suggest ways to present testimonials for maximum impact",
        "Generate placeholder testimonials if real ones aren't available yet",
    ],
)

SECTION_SUPPORT_CTA = SectionDefinition(
    id="support-cta",
    label="Support the Show",
    category="marketing",
    icon="DollarSign",
    description="Links to Patreon, merch, donations, or sponsorship inquiries",
    default_enabled=True,
    order_priority=23,
    required_fields=[
        SectionFieldDefinition(
            name="cta_url",
            type="url",
            label="Support URL",
            placeholder="https://patreon.com/yourshow",
            required=True,
        ),
    ],
    optional_fields=[
        SectionFieldDefinition(
            name="heading",
            type="text",
            label="Heading",
            placeholder="Support the Show",
            default="Support the Show",
        ),
        SectionFieldDefinition(
            name="description",
            type="textarea",
            label="Description",
            placeholder="Help us keep making great content...",
        ),
        SectionFieldDefinition(
            name="button_text",
            type="text",
            label="Button Text",
            placeholder="Become a Supporter",
            default="Become a Supporter",
        ),
        SectionFieldDefinition(
            name="support_type",
            type="select",
            label="Support Type",
            options=["patreon", "buymeacoffee", "merchandise", "sponsorship", "donation", "custom"],
            default="patreon",
        ),
    ],
    ai_prompt_hints=[
        "Write compelling support CTAs that explain the value of contributions",
        "Highlight benefits for supporters (bonus content, recognition, etc.)",
    ],
)


# ============================================================================
# TIER 3: OPTIONAL SECTIONS
# ============================================================================

SECTION_EVENTS = SectionDefinition(
    id="events",
    label="Events Calendar",
    category="community",
    icon="Calendar",
    description="Upcoming live shows, watch parties, or virtual events",
    default_enabled=False,
    order_priority=30,
    required_fields=[],
    optional_fields=[
        SectionFieldDefinition(
            name="heading",
            type="text",
            label="Section Heading",
            placeholder="Upcoming Events",
            default="Upcoming Events",
        ),
        # Note: events array is dynamically managed via separate API
    ],
    ai_prompt_hints=[
        "Write engaging event descriptions that drive RSVPs",
        "Suggest event ideas based on podcast content",
    ],
)

SECTION_COMMUNITY = SectionDefinition(
    id="community",
    label="Community Highlights",
    category="community",
    icon="Heart",
    description="Feature fan art, listener shout-outs, or social conversations",
    default_enabled=False,
    order_priority=31,
    required_fields=[],
    optional_fields=[
        SectionFieldDefinition(
            name="heading",
            type="text",
            label="Section Heading",
            placeholder="Community Highlights",
            default="Community Highlights",
        ),
        SectionFieldDefinition(
            name="description",
            type="textarea",
            label="Description",
            placeholder="Check out what our amazing community is creating...",
        ),
        # Note: community items array is dynamically managed via separate API
    ],
    ai_prompt_hints=[
        "Write descriptions that celebrate community contributions",
        "Suggest ways to encourage more community engagement",
    ],
)

SECTION_PRESS = SectionDefinition(
    id="press",
    label="Press & Media",
    category="advanced",
    icon="Newspaper",
    description="Notable press mentions and media kit downloads",
    default_enabled=False,
    order_priority=40,
    required_fields=[],
    optional_fields=[
        SectionFieldDefinition(
            name="heading",
            type="text",
            label="Section Heading",
            placeholder="Press & Media",
            default="Press & Media",
        ),
        SectionFieldDefinition(
            name="media_kit_url",
            type="url",
            label="Media Kit URL",
            placeholder="https://yoursite.com/media-kit.pdf",
        ),
        # Note: press items array is dynamically managed via separate API
    ],
    ai_prompt_hints=[
        "Suggest how to present press coverage professionally",
    ],
)

SECTION_SPONSORS = SectionDefinition(
    id="sponsors",
    label="Sponsors Showcase",
    category="marketing",
    icon="Award",
    description="Thank current sponsors and invite sponsorship inquiries",
    default_enabled=False,
    order_priority=41,
    required_fields=[],
    optional_fields=[
        SectionFieldDefinition(
            name="heading",
            type="text",
            label="Section Heading",
            placeholder="Our Sponsors",
            default="Our Sponsors",
        ),
        SectionFieldDefinition(
            name="description",
            type="textarea",
            label="Description",
            placeholder="This show is brought to you by...",
        ),
        SectionFieldDefinition(
            name="inquiry_email",
            type="text",
            label="Sponsorship Inquiry Email",
            placeholder="sponsors@yourpodcast.com",
        ),
        # Note: sponsor items array is dynamically managed via separate API
    ],
    ai_prompt_hints=[
        "Write sponsor thank-you messages that feel authentic",
        "Create compelling sponsorship inquiry CTAs",
    ],
)

SECTION_RESOURCES = SectionDefinition(
    id="resources",
    label="Resource Library",
    category="content",
    icon="BookOpen",
    description="Episode guides, templates, worksheets, and downloads",
    default_enabled=False,
    order_priority=42,
    required_fields=[],
    optional_fields=[
        SectionFieldDefinition(
            name="heading",
            type="text",
            label="Section Heading",
            placeholder="Resources",
            default="Resources",
        ),
        SectionFieldDefinition(
            name="description",
            type="textarea",
            label="Description",
            placeholder="Download helpful guides and tools mentioned in our episodes.",
        ),
        # Note: resource items array is dynamically managed via separate API
    ],
    ai_prompt_hints=[
        "Suggest resource ideas based on episode topics",
        "Write descriptions that explain the value of each resource",
    ],
)

SECTION_FAQ = SectionDefinition(
    id="faq",
    label="FAQ",
    category="content",
    icon="HelpCircle",
    description="Answer common questions about your podcast",
    default_enabled=False,
    order_priority=43,
    required_fields=[],
    optional_fields=[
        SectionFieldDefinition(
            name="heading",
            type="text",
            label="Section Heading",
            placeholder="Frequently Asked Questions",
            default="Frequently Asked Questions",
        ),
        # Note: FAQ items array is dynamically managed via separate API
    ],
    ai_prompt_hints=[
        "Generate common questions new listeners might have",
        "Write clear, concise answers",
        "Include questions about episode format, schedule, and how to engage",
    ],
)

SECTION_CONTACT = SectionDefinition(
    id="contact",
    label="Contact Form",
    category="community",
    icon="MessageSquare",
    description="Let listeners reach out for guest pitches, feedback, or inquiries",
    default_enabled=False,
    order_priority=44,
    required_fields=[
        SectionFieldDefinition(
            name="form_action_url",
            type="url",
            label="Form Action URL",
            placeholder="https://your-form-service.com/submit",
            required=True,
            help_text="Your form backend endpoint",
        ),
    ],
    optional_fields=[
        SectionFieldDefinition(
            name="heading",
            type="text",
            label="Section Heading",
            placeholder="Get in Touch",
            default="Get in Touch",
        ),
        SectionFieldDefinition(
            name="description",
            type="textarea",
            label="Description",
            placeholder="Have a guest idea? Want to share feedback? We'd love to hear from you.",
        ),
        SectionFieldDefinition(
            name="show_fields",
            type="multiselect",
            label="Form Fields",
            options=["name", "email", "subject", "message"],
            default=["name", "email", "message"],
        ),
    ],
    ai_prompt_hints=[
        "Write welcoming contact form descriptions",
        "Suggest specific use cases (guest pitches, feedback, etc.)",
    ],
)

SECTION_TRANSCRIPTS = SectionDefinition(
    id="transcripts",
    label="Transcript Archive",
    category="advanced",
    icon="FileText",
    description="Searchable episode transcripts for accessibility and SEO",
    default_enabled=False,
    order_priority=45,
    required_fields=[],
    optional_fields=[
        SectionFieldDefinition(
            name="heading",
            type="text",
            label="Section Heading",
            placeholder="Episode Transcripts",
            default="Episode Transcripts",
        ),
        SectionFieldDefinition(
            name="show_search",
            type="toggle",
            label="Show Search Bar",
            default=True,
        ),
        SectionFieldDefinition(
            name="episodes_per_page",
            type="number",
            label="Episodes Per Page",
            default=10,
        ),
    ],
    ai_prompt_hints=[
        "Explain the value of transcripts for accessibility and searchability",
    ],
)

SECTION_SOCIAL_FEED = SectionDefinition(
    id="social-feed",
    label="Social Media Feed",
    category="community",
    icon="Share2",
    description="Embedded social media posts from your podcast accounts",
    default_enabled=False,
    order_priority=46,
    required_fields=[
        SectionFieldDefinition(
            name="platform",
            type="select",
            label="Platform",
            options=["twitter", "instagram", "tiktok"],
            required=True,
        ),
        SectionFieldDefinition(
            name="username",
            type="text",
            label="Username/Handle",
            placeholder="@yourpodcast",
            required=True,
        ),
    ],
    optional_fields=[
        SectionFieldDefinition(
            name="heading",
            type="text",
            label="Section Heading",
            placeholder="Follow Us",
            default="Follow Us",
        ),
        SectionFieldDefinition(
            name="post_count",
            type="number",
            label="Number of Posts",
            default=6,
        ),
    ],
    ai_prompt_hints=[
        "Write descriptions that encourage social media follows",
    ],
)

SECTION_BEHIND_SCENES = SectionDefinition(
    id="behind-scenes",
    label="Behind the Scenes",
    category="content",
    icon="Film",
    description="Production notes, outtakes, and exclusive bonus content",
    default_enabled=False,
    order_priority=47,
    required_fields=[],
    optional_fields=[
        SectionFieldDefinition(
            name="heading",
            type="text",
            label="Section Heading",
            placeholder="Behind the Scenes",
            default="Behind the Scenes",
        ),
        SectionFieldDefinition(
            name="description",
            type="textarea",
            label="Description",
            placeholder="Get an inside look at how we make the show...",
        ),
        # Note: content items array is dynamically managed via separate API
    ],
    ai_prompt_hints=[
        "Suggest behind-the-scenes content ideas",
        "Write engaging descriptions that give listeners insider access",
    ],
)


# ============================================================================
# SECTION REGISTRY
# ============================================================================

ALL_SECTIONS: Dict[str, SectionDefinition] = {
    # Layout sections
    "header": SECTION_HEADER,
    "footer": SECTION_FOOTER,
    
    # Core (Tier 1)
    "hero": SECTION_HERO,
    "about": SECTION_ABOUT,
    "latest-episodes": SECTION_LATEST_EPISODES,
    "subscribe": SECTION_SUBSCRIBE,
    
    # Recommended (Tier 2)
    "hosts": SECTION_HOSTS,
    "newsletter": SECTION_NEWSLETTER,
    "testimonials": SECTION_TESTIMONIALS,
    "support-cta": SECTION_SUPPORT_CTA,
    
    # Optional (Tier 3)
    "events": SECTION_EVENTS,
    "community": SECTION_COMMUNITY,
    "press": SECTION_PRESS,
    "sponsors": SECTION_SPONSORS,
    "resources": SECTION_RESOURCES,
    "faq": SECTION_FAQ,
    "contact": SECTION_CONTACT,
    "transcripts": SECTION_TRANSCRIPTS,
    "social-feed": SECTION_SOCIAL_FEED,
    "behind-scenes": SECTION_BEHIND_SCENES,
}


def get_section_definition(section_id: str) -> Optional[SectionDefinition]:
    """Retrieve a section definition by ID."""
    return ALL_SECTIONS.get(section_id)


def get_sections_by_category(category: str) -> List[SectionDefinition]:
    """Get all sections in a specific category."""
    return [s for s in ALL_SECTIONS.values() if s.category == category]


def get_default_enabled_sections() -> List[SectionDefinition]:
    """Get all sections that are enabled by default."""
    return [s for s in ALL_SECTIONS.values() if s.default_enabled]


def get_all_sections_sorted() -> List[SectionDefinition]:
    """Get all sections sorted by order_priority."""
    return sorted(ALL_SECTIONS.values(), key=lambda s: s.order_priority)
