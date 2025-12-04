from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.exc import OperationalError, ProgrammingError
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Field, Session, SQLModel


logger = logging.getLogger(__name__)


class AppSetting(SQLModel, table=True):
    """Simple key/value app-wide setting store (JSON string in value_json).

    Use a small set of well-known keys, e.g., 'admin_settings'.
    """

    key: str = Field(primary_key=True, index=True)
    value_json: str = Field(default='{}')
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AdminSettings(BaseModel):
    """App-wide admin-configurable settings.

    - test_mode: legacy toggle used by parts of the system/tests
    - default_user_active: whether newly created users start active (True) or inactive (False)
    - default_user_tier: default tier for newly created users (e.g., 'free', 'creator', 'pro', 'unlimited')
    - maintenance_mode: when True, non-admin API requests are rejected with HTTP 503
    - maintenance_message: optional string surfaced to clients when maintenance is active
    - browser_audio_conversion_enabled: feature flag exposed to clients for toggling
      browser-side audio conversion support
    """

    test_mode: bool = False
    default_user_active: bool = True
    default_user_tier: str = "trial"  # Default tier for new users - all accounts start as trial
    # Maximum upload size for main content (in MB). Exposed publicly for client hints.
    max_upload_mb: int = 500
    maintenance_mode: bool = False
    maintenance_message: Optional[str] = None
    browser_audio_conversion_enabled: bool = True
    free_trial_days: int = 7  # Length of free trial in days (configurable in admin settings)


def load_admin_settings(session: Session) -> AdminSettings:
    """Load AdminSettings from the AppSetting row ``admin_settings``.

    The helper is intentionally defensive: if the settings table is missing or
    contains malformed JSON we log the error, roll back the current transaction
    (to keep the caller's session usable) and fall back to the default
    ``AdminSettings`` values.
    """

    try:
        rec = session.get(AppSetting, "admin_settings")
        if not rec or not (rec.value_json or "").strip():
            return AdminSettings()
        data = json.loads(rec.value_json)
        if not isinstance(data, dict):
            return AdminSettings()
        return AdminSettings(**data)
    except Exception as exc:  # pragma: no cover - defensive fallback
        try:
            session.rollback()
        except Exception:  # pragma: no cover - rollback may fail if session closed
            pass
        if _is_missing_table_error(exc):
            _ensure_appsetting_table(session)
        logger.warning("Failed loading admin settings, using defaults: %s", exc)
        return AdminSettings()


def _is_missing_table_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "no such table" in text
        or "does not exist" in text
        or "undefined table" in text
    )


def _ensure_appsetting_table(session: Session) -> None:
    try:
        bind = session.get_bind()
        if bind is None:
            return
        AppSetting.__table__.create(bind, checkfirst=True)  # type: ignore[arg-type]
    except Exception as exc:  # pragma: no cover - best effort safeguard
        logger.debug("Unable to ensure appsetting table: %s", exc)


def save_admin_settings(session: Session, settings: AdminSettings) -> AdminSettings:
    """Persist AdminSettings into AppSetting row 'admin_settings'. Returns the reloaded value."""

    def _load_or_create() -> AppSetting:
        rec = session.get(AppSetting, 'admin_settings')
        payload = json.dumps(settings.model_dump())
        if not rec:
            rec = AppSetting(key='admin_settings', value_json=payload)
        else:
            rec.value_json = payload
        try:
            rec.updated_at = datetime.utcnow()
        except Exception:  # pragma: no cover - timestamp best effort
            pass
        session.add(rec)
        return rec

    try:
        rec = _load_or_create()
        session.commit()
    except (ProgrammingError, OperationalError) as exc:
        if not _is_missing_table_error(exc):
            session.rollback()
            raise
        session.rollback()
        _ensure_appsetting_table(session)
        rec = _load_or_create()
        session.commit()
    except Exception:
        session.rollback()
        raise
    return load_admin_settings(session)


class LandingReview(BaseModel):
    quote: str
    author: str
    role: Optional[str] = None
    avatar_url: Optional[str] = None
    rating: Optional[float] = None


class LandingFAQ(BaseModel):
    question: str
    answer: str


class HeroSection(BaseModel):
    label: str = "Patent-Pending AI Technology"
    title: str = "Professional Podcasting"
    title_highlight: str = "For Everyone"
    description: str = (
        "No experience needed. No technical skills required. No age limit. Just your voice and our patent-pending "
        "technology. DoneCast makes professional podcasting so easy, it's faster and cheaper than hiring someone else to do it."
    )
    cta_text: str = "Start Your Free Trial"
    meta_items: list[str] = PydanticField(default_factory=lambda: ["Anyone can do this", "Setup in 5 minutes"])


class AIEditingSection(BaseModel):
    pill_text: str = "AI That Works For You"
    title: str = "Edit in Real-Time While You Record"
    description: str = (
        "Our AI removes awkward pauses, balances audio levels, writes show notes, and adds start-of-the-art features all as you speak. "
        "It's like having an entire production team behind the scenes—without the cost."
    )
    bullets: list[str] = PydanticField(
        default_factory=lambda: [
            "Smart cleanup removes filler words and awkward silence automatically",
            "Automatically generate show notes and SEO tags for every episode",
            "Our one-stop shop lets you take care of everything in just a few clicks.",
        ]
    )


class PillarCard(BaseModel):
    title: str
    description: str
    tone: str = "primary"  # primary, secondary, or accent


class DoneForYouSection(BaseModel):
    title: str = "Done For You,"
    title_highlight: str = "By You"
    description: str = (
        "Why pay someone else when you can do it yourself—faster, cheaper, and with complete creative control? "
        "DoneCast is so intuitive that publishing your podcast takes less time and effort than explaining it to someone else."
    )
    pillars: list[PillarCard] = PydanticField(
        default_factory=lambda: [
            PillarCard(
                title="Faster",
                description="Record, edit, and publish in minutes. No back-and-forth with editors. No waiting days for revisions.",
                tone="primary",
            ),
            PillarCard(
                title="Cheaper",
                description="One affordable subscription replaces expensive editors, hosting fees, and distribution services.",
                tone="secondary",
            ),
            PillarCard(
                title="Easier",
                description="So simple, your grandparents could use it. So powerful, professionals choose it. That's the magic.",
                tone="accent",
            ),
        ]
    )


class StepCard(BaseModel):
    number: int
    title: str
    description: str
    color: str = "primary"  # primary, secondary, or accent


class ThreeStepsSection(BaseModel):
    title: str = "From Idea to Published in"
    title_highlight: str = "3 Simple Steps"
    description: str = "Seriously, it's this easy. No technical knowledge required. No learning curve. Just start talking."
    steps: list[StepCard] = PydanticField(
        default_factory=lambda: [
            StepCard(
                number=1,
                title="Record",
                description="Hit record and start talking. Our AI handles the rest—removing mistakes, enhancing audio, and creating chapters.",
                color="primary",
            ),
            StepCard(
                number=2,
                title="Review",
                description="Preview your episode with AI-applied edits. Make any final tweaks with our simple, intuitive editor.",
                color="secondary",
            ),
            StepCard(
                number=3,
                title="Publish",
                description="One click distributes your podcast to Spotify, Apple Podcasts, and 20+ platforms. You're live!",
                color="accent",
            ),
        ]
    )
    cta_text: str = "Start Your First Episode Now"


class FeatureCard(BaseModel):
    title: str
    description: str
    tone: str = "primary"  # primary, secondary, or accent


class FeaturesSection(BaseModel):
    title: str = "Everything You Need to"
    title_highlight: str = "Succeed"
    description: str = "Professional-grade tools that would normally cost thousands. All included in one simple platform."
    features: list[FeatureCard] = PydanticField(
        default_factory=lambda: [
            FeatureCard(
                title="Unlimited Hosting",
                description="Upload unlimited episodes with no storage limits. Your content, your way, without restrictions.",
                tone="primary",
            ),
            FeatureCard(
                title="AI-Powered Editing",
                description="Edit while you record with AI that removes mistakes, adds effects, and polishes your audio in real-time.",
                tone="secondary",
            ),
            FeatureCard(
                title="Global Distribution",
                description="Automatically distribute to Spotify, Apple Podcasts, Google Podcasts, and 20+ platforms.",
                tone="accent",
            ),
            FeatureCard(
                title="Lightning Fast",
                description="Global CDN ensures your episodes load instantly for listeners anywhere in the world.",
                tone="primary",
            ),
            FeatureCard(
                title="Team Collaboration",
                description="Invite team members, manage permissions, and collaborate seamlessly on your podcast.",
                tone="secondary",
            ),
            FeatureCard(
                title="Custom Player",
                description="Beautiful, embeddable podcast player that matches your brand and engages listeners.",
                tone="accent",
            ),
        ]
    )


class Differentiator(BaseModel):
    title: str
    description: str
    tone: str = "primary"  # primary, secondary, or accent


class WhySection(BaseModel):
    title: str = "Why"
    title_highlight: str = "DoneCast"
    title_suffix: str = "?"
    description: str = (
        "We've built something truly special here. Technology that doesn't exist anywhere else. A platform that makes the "
        "impossible feel effortless. This is podcasting, reimagined."
    )
    differentiators: list[Differentiator] = PydanticField(
        default_factory=lambda: [
            Differentiator(
                title="Patent-Pending Innovation",
                description="Technology you literally can't get anywhere else. We invented it.",
                tone="primary",
            ),
            Differentiator(
                title="Built For Everyone",
                description="From first-timers to seasoned pros. From teens to retirees. Anyone can create here.",
                tone="secondary",
            ),
            Differentiator(
                title="Unbeatable Value",
                description="Replace your editor, hosting, and distribution services with one affordable platform.",
                tone="accent",
            ),
            Differentiator(
                title="AI That Actually Works",
                description="Not gimmicky features. Real AI that saves you hours and makes you sound professional.",
                tone="primary",
            ),
        ]
    )


class FinalCTASection(BaseModel):
    pill_text: str = "Ready when you are"
    title: str = "Ready to Take Your Podcast to the Next Level?"
    description: str = "Join the next generation of podcasters who are building their audience with DoneCast."
    cta_text: str = "Start Your Free Trial"
    fine_print: str = "14-day free trial • No credit card required • Cancel anytime"


_DEFAULT_HERO_HTML = (
    "<p>Join thousands of creators who've discovered the joy of effortless podcasting."
    " <strong>Average setup time: Under 5 minutes.</strong></p>"
)


def _default_reviews() -> list[LandingReview]:
    return [
        LandingReview(
            quote=(
                "I was terrified of the technical side of podcasting. DoneCast made it so simple that I "
                "launched my first episode in under 30 minutes! Now I have 50+ episodes and growing."
            ),
            author="Sarah Johnson",
            role="Wellness Coach • 12 months on DoneCast",
            avatar_url="https://placehold.co/60x60/E2E8F0/A0AEC0?text=SJ",
            rating=5.0,
        ),
        LandingReview(
            quote=(
                "My podcast now reaches 10,000+ listeners monthly. The automatic distribution to all platforms was a "
                "game-changer for my reach!"
            ),
            author="Maria Rodriguez",
            role="Community Leader • 8 months on DoneCast",
            avatar_url="https://placehold.co/60x60/E2E8F0/A0AEC0?text=MR",
            rating=5.0,
        ),
        LandingReview(
            quote=(
                "The AI editing tools are unbelievable. I cut my production time by 80% and the quality actually went up."
            ),
            author="Dev Patel",
            role="Startup Founder • 6 months on DoneCast",
            avatar_url="https://placehold.co/60x60/E2E8F0/A0AEC0?text=DP",
            rating=5.0,
        ),
    ]


def _default_faqs() -> list[LandingFAQ]:
    return [
        LandingFAQ(
            question="Do I need any technical experience to use DoneCast?",
            answer=(
                "Absolutely not! DoneCast is designed for complete beginners. If you can use email, you can create "
                "professional podcasts with our platform."
            ),
        ),
        LandingFAQ(
            question="How long does it take to publish my first episode?",
            answer=(
                "Most users publish their first episode within 30 minutes of signing up. Our average setup time is under "
                "5 minutes, and episode creation takes just a few more minutes."
            ),
        ),
        LandingFAQ(
            question="What platforms will my podcast be available on?",
            answer=(
                "Your podcast will automatically be distributed to 20+ major platforms including Spotify, Apple Podcasts, "
                "Google Podcasts, and many more with just one click."
            ),
        ),
        LandingFAQ(
            question="Is there really a free trial with no credit card required?",
            answer=(
                "Yes! You get full access to all features for 14 days completely free. No credit card required, no hidden fees, "
                "and you can cancel anytime."
            ),
        ),
        LandingFAQ(
            question="What if I'm not satisfied with the service?",
            answer="We offer a 30-day money-back guarantee. If you're not completely satisfied, we'll refund your payment, no questions asked.",
        ),
    ]


class LandingPageContent(BaseModel):
    # Main sections
    hero: HeroSection = PydanticField(default_factory=HeroSection)
    ai_editing: AIEditingSection = PydanticField(default_factory=AIEditingSection)
    done_for_you: DoneForYouSection = PydanticField(default_factory=DoneForYouSection)
    three_steps: ThreeStepsSection = PydanticField(default_factory=ThreeStepsSection)
    features: FeaturesSection = PydanticField(default_factory=FeaturesSection)
    why: WhySection = PydanticField(default_factory=WhySection)
    final_cta: FinalCTASection = PydanticField(default_factory=FinalCTASection)
    
    # Legacy fields (keep for backward compatibility but not displayed on new landing page)
    hero_html: str = _DEFAULT_HERO_HTML
    
    # Testimonials/Reviews section
    reviews_heading: str = "Real Stories from Real Podcasters"
    reviews_summary: str = "4.9/5 from 2,847 reviews"
    reviews: list[LandingReview] = PydanticField(default_factory=_default_reviews)
    
    # FAQ section
    faq_heading: str = "Frequently Asked Questions"
    faq_subheading: str = "Everything you need to know about getting started with DoneCast"
    faqs: list[LandingFAQ] = PydanticField(default_factory=_default_faqs)
    
    updated_at: Optional[datetime] = None


def load_landing_content(session: Session) -> LandingPageContent:
    try:
        rec = session.get(AppSetting, "landing_page_content")
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Failed loading landing content, using defaults: %s", exc)
        return LandingPageContent()
    if not rec or not (rec.value_json or "").strip():
        return LandingPageContent()
    try:
        data = json.loads(rec.value_json)
        content = LandingPageContent(**data)
    except Exception as exc:  # pragma: no cover - invalid JSON falls back
        logger.warning("Invalid landing content payload, using defaults: %s", exc)
        return LandingPageContent()
    if content.updated_at is None and getattr(rec, "updated_at", None):
        try:
            content.updated_at = rec.updated_at
        except Exception:
            pass
    return content


def save_landing_content(session: Session, content: LandingPageContent) -> LandingPageContent:
    payload = content.model_copy(update={"updated_at": datetime.utcnow()})

    def _load_or_create() -> AppSetting:
        rec = session.get(AppSetting, "landing_page_content")
        data = payload.model_dump_json()
        if not rec:
            rec = AppSetting(key="landing_page_content", value_json=data)
        else:
            rec.value_json = data
        try:
            rec.updated_at = datetime.utcnow()
        except Exception:  # pragma: no cover
            pass
        session.add(rec)
        return rec

    try:
        rec = _load_or_create()
        session.commit()
    except (ProgrammingError, OperationalError) as exc:
        if not _is_missing_table_error(exc):
            session.rollback()
            raise
        session.rollback()
        _ensure_appsetting_table(session)
        rec = _load_or_create()
        session.commit()
    except Exception:
        session.rollback()
        raise
    try:
        data = json.loads(rec.value_json or "{}")
        return LandingPageContent(**data)
    except Exception:  # pragma: no cover - fallback to defaults if corrupted immediately after save
        return LandingPageContent()


# ===== PRICING PAGE CONTENT =====

class PricingTierFeature(BaseModel):
    """Feature flags for a pricing tier"""
    uploadRecord: bool = True
    basicCleanup: bool = True
    manualPublish: bool = True
    flubber: bool = False
    intern: bool = False
    advancedIntern: bool = False
    sfxTemplates: bool = False
    analytics: str = "Basic"  # "Basic", "Advanced", "Full"
    multiUser: bool | str = False  # Can be bool or "Coming soon" string
    priorityQueue: bool = False
    premiumSupport: bool = False


class PricingTier(BaseModel):
    """Pricing tier configuration for the pricing page"""
    key: str  # "starter", "creator", "pro", "executive", "enterprise"
    name: str
    monthly: int | None = None
    annual: int | None = None
    credits: str  # Display string like "28,800"
    maxEpisodeLength: str  # Display string like "40 min"
    queuePriority: str  # Display string like "Low"
    queue: str  # Display string like "2 hrs, held 7 days"
    features: PricingTierFeature = PydanticField(default_factory=PricingTierFeature)
    cta: dict[str, str] = PydanticField(default_factory=lambda: {"label": "Get Started", "href": ""})
    popular: bool = False
    badge: str | None = None
    contact: bool = False
    earlyOffers: list[dict[str, str]] | None = None  # For early access mode


def _default_pricing_tiers() -> list[PricingTier]:
    """Default pricing tiers matching the current Pricing.jsx hardcoded data"""
    return [
        PricingTier(
            key="starter",
            name="Starter",
            monthly=19,
            annual=None,
            credits="28,800",
            maxEpisodeLength="40 min",
            queuePriority="Low",
            queue="2 hrs, held 7 days",
            features=PricingTierFeature(
                uploadRecord=True,
                basicCleanup=True,
                manualPublish=True,
                flubber=False,
                intern=False,
                advancedIntern=False,
                sfxTemplates=False,
                analytics="Basic",
                multiUser=False,
                priorityQueue=False,
                premiumSupport=False,
            ),
            cta={"label": "Get Started", "href": "https://app.podcastpro.plus/signup?plan=starter"},
        ),
        PricingTier(
            key="creator",
            name="Creator",
            monthly=39,
            annual=31,
            credits="72,000",
            maxEpisodeLength="80 min",
            queuePriority="Medium",
            queue="10 hrs, held 14 days",
            features=PricingTierFeature(
                uploadRecord=True,
                basicCleanup=True,
                manualPublish=True,
                flubber=True,
                intern=True,
                advancedIntern=False,
                sfxTemplates=False,
                analytics="Advanced",
                multiUser=False,
                priorityQueue=False,
                premiumSupport=False,
            ),
            cta={"label": "Start Creating", "href": "https://app.podcastpro.plus/signup?plan=creator"},
            popular=True,
            badge="Most Popular",
        ),
        PricingTier(
            key="pro",
            name="Pro",
            monthly=79,
            annual=63,
            credits="172,800",
            maxEpisodeLength="120 min",
            queuePriority="High",
            queue="25 hrs, held 30 days",
            features=PricingTierFeature(
                uploadRecord=True,
                basicCleanup=True,
                manualPublish=True,
                flubber=True,
                intern=True,
                advancedIntern=True,
                sfxTemplates=True,
                analytics="Full",
                multiUser=False,
                priorityQueue=False,
                premiumSupport=False,
            ),
            cta={"label": "Go Pro", "href": "https://app.podcastpro.plus/signup?plan=pro"},
        ),
        PricingTier(
            key="executive",
            name="Executive",
            monthly=129,
            annual=107,
            credits="288,000",
            maxEpisodeLength="240 min*",
            queuePriority="Highest",
            queue="50 hrs, held 60 days",
            features=PricingTierFeature(
                uploadRecord=True,
                basicCleanup=True,
                manualPublish=True,
                flubber=True,
                intern=True,
                advancedIntern=True,
                sfxTemplates=True,
                analytics="Full",
                multiUser="Coming soon",
                priorityQueue=True,
                premiumSupport=True,
            ),
            cta={"label": "Go Executive", "href": "https://app.podcastpro.plus/signup?plan=executive"},
        ),
        PricingTier(
            key="enterprise",
            name="Enterprise",
            monthly=None,
            annual=None,
            credits="Custom",
            maxEpisodeLength="Custom",
            queuePriority="Highest",
            queue="Custom",
            features=PricingTierFeature(
                uploadRecord=True,
                basicCleanup=True,
                manualPublish=True,
                flubber=True,
                intern=True,
                advancedIntern=True,
                sfxTemplates=True,
                analytics="Full",
                multiUser=True,
                priorityQueue=True,
                premiumSupport=True,
            ),
            cta={"label": "Contact Us"},
            contact=True,
        ),
    ]


class PricingFeatureDefinition(BaseModel):
    """Definition of a feature/benefit row in the pricing matrix"""
    key: str  # Unique identifier (e.g., "credits", "maxEpisodeLength", "flubber")
    label: str  # Display name (e.g., "Monthly Credits", "Flubber")
    description: str = ""  # Optional description/tooltip
    type: str = "text"  # "boolean", "number", "text", "select"
    options: list[str] | None = None  # For select type
    fieldPath: str = ""  # Where to store the value (e.g., "credits" or "features.flubber")
    order: int = 0  # Display order
    category: str = "general"  # Optional category for grouping


def _default_feature_definitions() -> list[PricingFeatureDefinition]:
    """Default feature definitions matching current hardcoded rows"""
    return [
        PricingFeatureDefinition(key="monthly", label="Monthly Price", description="Monthly subscription price in USD", type="number", fieldPath="monthly", order=1),
        PricingFeatureDefinition(key="annual", label="Annual Price", description="Annual subscription price in USD (null if not available)", type="number", fieldPath="annual", order=2),
        PricingFeatureDefinition(key="credits", label="Monthly Credits", description="Monthly credits allocation (display string)", type="text", fieldPath="credits", order=3),
        PricingFeatureDefinition(key="maxEpisodeLength", label="Max Episode Length", description="Maximum episode length (e.g., \"40 min\")", type="text", fieldPath="maxEpisodeLength", order=4),
        PricingFeatureDefinition(key="queuePriority", label="Queue Priority", description="Processing queue priority", type="select", options=["Low", "Medium", "High", "Highest"], fieldPath="queuePriority", order=5),
        PricingFeatureDefinition(key="queue", label="Queue Storage", description="Queue storage description (e.g., \"2 hrs, held 7 days\")", type="text", fieldPath="queue", order=6),
        PricingFeatureDefinition(key="uploadRecord", label="Upload & Record", description="Allow upload and recording", type="boolean", fieldPath="features.uploadRecord", order=7),
        PricingFeatureDefinition(key="basicCleanup", label="Basic Cleanup", description="Basic cleanup (noise, trim)", type="boolean", fieldPath="features.basicCleanup", order=8),
        PricingFeatureDefinition(key="manualPublish", label="Manual Publish", description="Manual publishing capability", type="boolean", fieldPath="features.manualPublish", order=9),
        PricingFeatureDefinition(key="flubber", label="Flubber", description="Flubber (filler removal)", type="boolean", fieldPath="features.flubber", order=10),
        PricingFeatureDefinition(key="intern", label="Intern", description="Intern (spoken edits)", type="boolean", fieldPath="features.intern", order=11),
        PricingFeatureDefinition(key="advancedIntern", label="Advanced Intern", description="Advanced Intern (multi-step edits)", type="boolean", fieldPath="features.advancedIntern", order=12),
        PricingFeatureDefinition(key="sfxTemplates", label="SFX & Templates", description="Sound Effects & templates", type="boolean", fieldPath="features.sfxTemplates", order=13),
        PricingFeatureDefinition(key="analytics", label="Analytics", description="Analytics level", type="select", options=["Basic", "Advanced", "Full"], fieldPath="features.analytics", order=14),
        PricingFeatureDefinition(key="multiUser", label="Multi-user", description="Multi-user accounts (true/false/\"Coming soon\")", type="text", fieldPath="features.multiUser", order=15),
        PricingFeatureDefinition(key="priorityQueue", label="Priority Queue", description="Priority processing queue", type="boolean", fieldPath="features.priorityQueue", order=16),
        PricingFeatureDefinition(key="premiumSupport", label="Premium Support", description="Premium support access", type="boolean", fieldPath="features.premiumSupport", order=17),
    ]


class PricingPageContent(BaseModel):
    """Pricing page configuration"""
    standardTiers: list[PricingTier] = PydanticField(default_factory=_default_pricing_tiers)
    earlyAccessTiers: list[PricingTier] | None = None
    featureDefinitions: list[PricingFeatureDefinition] = PydanticField(default_factory=_default_feature_definitions)
    updated_at: Optional[datetime] = None


def load_pricing_content(session: Session) -> PricingPageContent:
    """Load pricing page content from database"""
    try:
        rec = session.get(AppSetting, "pricing_page_content")
    except Exception as exc:
        logger.warning("Failed loading pricing content, using defaults: %s", exc)
        return PricingPageContent()
    if not rec or not (rec.value_json or "").strip():
        return PricingPageContent()
    try:
        data = json.loads(rec.value_json)
        content = PricingPageContent(**data)
        # Ensure featureDefinitions exist (for backward compatibility)
        if not content.featureDefinitions:
            content.featureDefinitions = _default_feature_definitions()
        # Sort features by order
        content.featureDefinitions.sort(key=lambda f: f.order)
    except Exception as exc:
        logger.warning("Invalid pricing content payload, using defaults: %s", exc)
        return PricingPageContent()
    if content.updated_at is None and getattr(rec, "updated_at", None):
        try:
            content.updated_at = rec.updated_at
        except Exception:
            pass
    return content


def save_pricing_content(session: Session, content: PricingPageContent) -> PricingPageContent:
    """Save pricing page content to database"""
    payload = content.model_copy(update={"updated_at": datetime.utcnow()})

    def _load_or_create() -> AppSetting:
        rec = session.get(AppSetting, "pricing_page_content")
        data = payload.model_dump_json()
        if not rec:
            rec = AppSetting(key="pricing_page_content", value_json=data)
        else:
            rec.value_json = data
        try:
            rec.updated_at = datetime.utcnow()
        except Exception:
            pass
        session.add(rec)
        return rec

    try:
        rec = _load_or_create()
        session.commit()
    except (ProgrammingError, OperationalError) as exc:
        if not _is_missing_table_error(exc):
            session.rollback()
            raise
        session.rollback()
        _ensure_appsetting_table(session)
        rec = _load_or_create()
        session.commit()
    except Exception:
        session.rollback()
        raise
    try:
        data = json.loads(rec.value_json or "{}")
        return PricingPageContent(**data)
    except Exception:
        return PricingPageContent()