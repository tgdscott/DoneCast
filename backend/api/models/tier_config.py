"""
Tier configuration models for database-driven feature gating.

Replaces hard-coded TIER_LIMITS and feature checks with flexible database configuration.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional, Any
from uuid import UUID

from sqlmodel import SQLModel, Field
from pydantic import BaseModel


class TierConfiguration(SQLModel, table=True):
    """
    Database table storing tier configurations.
    Each row represents one tier (free, creator, pro, unlimited, etc.)
    """
    __tablename__ = "tierconfiguration"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    tier_name: str = Field(index=True, unique=True, description="Internal tier key: free, creator, pro, unlimited")
    display_name: str = Field(description="User-facing display name: Free, Creator, Pro, Unlimited")
    is_public: bool = Field(default=True, description="False for admin-only tiers like unlimited")
    sort_order: int = Field(default=0, description="Display order in UI")
    
    # JSON storage for all feature values
    features_json: str = Field(description="JSON dict of all feature keys and values")
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[UUID] = Field(default=None, description="Admin user who created this config")
    
    @property
    def features(self) -> dict[str, Any]:
        """Parse features from JSON storage"""
        try:
            return json.loads(self.features_json or '{}')
        except Exception:
            return {}
    
    @features.setter
    def features(self, value: dict[str, Any]):
        """Serialize features to JSON storage"""
        self.features_json = json.dumps(value, indent=2)


class TierConfigurationHistory(SQLModel, table=True):
    """
    Audit log of tier configuration changes for rollback capability.
    """
    __tablename__ = "tierconfigurationhistory"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    tier_name: str = Field(index=True)
    version: int = Field(description="Incrementing version number for this tier")
    features_json: str = Field(description="Snapshot of features at this version")
    changed_by: Optional[UUID] = Field(default=None, description="Admin user who made the change")
    change_reason: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class TierFeatureDefinition(BaseModel):
    """
    Defines a feature that can be configured per-tier.
    Used by admin UI to know what features exist and how to display them.
    """
    key: str
    label: str
    description: str
    category: str  # "credits", "processing", "ai_tts", "editing", "branding", "analytics", "support", "costs"
    type: str  # "boolean", "number", "string", "select"
    options: Optional[list[str]] = None  # For select type
    default_value: Any
    min_value: Optional[float] = None  # For number type
    max_value: Optional[float] = None  # For number type
    help_text: Optional[str] = None


# Feature definitions for the tier editor
TIER_FEATURE_DEFINITIONS: list[TierFeatureDefinition] = [
    # Credits & Quotas
    TierFeatureDefinition(
        key="monthly_credits",
        label="Monthly Credits",
        description="Base monthly credits allocation (1x minutes)",
        category="credits",
        type="number",
        default_value=60,
        min_value=0,
        help_text="1 minute of audio = 1 credit. Free: 60 (60 min), Creator: 300 (300 min), Pro: 1000 (1000 min)"
    ),
    TierFeatureDefinition(
        key="max_episodes_month",
        label="Max Episodes per Month",
        description="Maximum number of episodes that can be published per month",
        category="credits",
        type="number",
        default_value=5,
        min_value=0,
        help_text="Set to null for unlimited"
    ),
    TierFeatureDefinition(
        key="rollover_credits",
        label="Rollover Credits",
        description="Allow unused credits to roll over to next month",
        category="credits",
        type="boolean",
        default_value=False,
        help_text="Pro feature: unused credits don't expire"
    ),
    
    # Audio Processing Pipeline
    TierFeatureDefinition(
        key="audio_pipeline",
        label="Audio Processing Pipeline",
        description="Which transcription and processing stack to use",
        category="processing",
        type="select",
        options=["assemblyai", "auphonic"],
        default_value="assemblyai",
        help_text="Auphonic provides professional-grade processing with filler removal, leveling, and noise reduction"
    ),
    TierFeatureDefinition(
        key="auto_filler_removal",
        label="Auto Filler Word Removal",
        description="Automatically remove filler words (um, uh, like)",
        category="processing",
        type="boolean",
        default_value=False,
        help_text="Requires Auphonic pipeline. Not the same as Flubber (user-triggered)."
    ),
    TierFeatureDefinition(
        key="auto_noise_reduction",
        label="Auto Noise Reduction",
        description="Automatic background noise reduction",
        category="processing",
        type="boolean",
        default_value=False,
        help_text="Requires Auphonic pipeline"
    ),
    TierFeatureDefinition(
        key="auto_leveling",
        label="Auto Audio Leveling",
        description="Automatic loudness normalization and leveling",
        category="processing",
        type="boolean",
        default_value=False,
        help_text="Requires Auphonic pipeline"
    ),
    
    # AI & TTS
    TierFeatureDefinition(
        key="tts_provider",
        label="TTS Provider",
        description="Text-to-speech voice provider",
        category="ai_tts",
        type="select",
        options=["standard", "elevenlabs"],
        default_value="standard",
        help_text="ElevenLabs provides premium AI voices with higher credit costs"
    ),
    TierFeatureDefinition(
        key="elevenlabs_voices",
        label="ElevenLabs Voice Clones",
        description="Number of custom voice clones allowed",
        category="ai_tts",
        type="number",
        default_value=0,
        min_value=0,
        max_value=100,
        help_text="Pro feature: create custom voice clones"
    ),
    TierFeatureDefinition(
        key="ai_enhancement",
        label="AI Enhancement Features",
        description="Access to AI-powered enhancement features",
        category="ai_tts",
        type="boolean",
        default_value=False,
        help_text="Includes AI-powered audio improvements beyond basic processing"
    ),
    
    # Editing Features
    TierFeatureDefinition(
        key="manual_editor",
        label="Manual Editor Access",
        description="Access to manual audio editor",
        category="editing",
        type="boolean",
        default_value=True,
        help_text="Basic audio editing interface"
    ),
    TierFeatureDefinition(
        key="flubber_feature",
        label="Flubber Feature",
        description="User-triggered mistake removal (say 'flubber' to mark cuts)",
        category="editing",
        type="boolean",
        default_value=False,
        help_text="NOT automatic filler word removal - user says 'flubber' keyword to trigger cuts"
    ),
    TierFeatureDefinition(
        key="intern_feature",
        label="Intern Feature",
        description="Spoken command detection (e.g., 'insert intro here')",
        category="editing",
        type="boolean",
        default_value=False,
        help_text="AI detects spoken editing commands during recording"
    ),
    
    # Branding & Publishing
    TierFeatureDefinition(
        key="custom_branding",
        label="Custom Branding",
        description="Remove/customize platform branding",
        category="branding",
        type="boolean",
        default_value=False,
        help_text="Remove 'Powered by DoneCast' branding"
    ),
    TierFeatureDefinition(
        key="custom_domain",
        label="Custom Domain",
        description="Custom domain for podcast website",
        category="branding",
        type="boolean",
        default_value=False,
        help_text="Host podcast website on your own domain"
    ),
    TierFeatureDefinition(
        key="white_label",
        label="White Label Options",
        description="Full white-label customization",
        category="branding",
        type="boolean",
        default_value=False,
        help_text="Complete brand customization including admin interface"
    ),
    TierFeatureDefinition(
        key="rss_customization",
        label="Advanced RSS Customization",
        description="Advanced RSS feed customization options",
        category="branding",
        type="boolean",
        default_value=False,
        help_text="Custom RSS tags, artwork per episode, etc."
    ),
    
    # Analytics & Insights
    TierFeatureDefinition(
        key="analytics_basic",
        label="Basic Analytics",
        description="Basic download statistics",
        category="analytics",
        type="boolean",
        default_value=True,
        help_text="Simple download counts and basic metrics"
    ),
    TierFeatureDefinition(
        key="analytics_advanced",
        label="Advanced Analytics",
        description="Advanced analytics dashboard with insights",
        category="analytics",
        type="boolean",
        default_value=False,
        help_text="Detailed listener insights, geography, devices, etc."
    ),
    TierFeatureDefinition(
        key="op3_analytics",
        label="OP3 Analytics Integration",
        description="Open Podcast Prefix Project analytics",
        category="analytics",
        type="boolean",
        default_value=False,
        help_text="Industry-standard podcast analytics via OP3"
    ),
    
    # Support & Priority
    TierFeatureDefinition(
        key="support_level",
        label="Support Level",
        description="Level of customer support",
        category="support",
        type="select",
        options=["community", "email", "priority", "dedicated"],
        default_value="community",
        help_text="community: forums only, email: email support, priority: faster response, dedicated: personal account manager"
    ),
    TierFeatureDefinition(
        key="priority_processing",
        label="Priority Processing",
        description="Higher queue priority for episode processing",
        category="support",
        type="boolean",
        default_value=False,
        help_text="Episodes process faster during high load"
    ),
    TierFeatureDefinition(
        key="api_access",
        label="API Access",
        description="REST API access for automation",
        category="support",
        type="boolean",
        default_value=False,
        help_text="Programmatic access to platform features"
    ),
    
    # Cost Multipliers
    TierFeatureDefinition(
        key="auphonic_cost_multiplier",
        label="Auphonic Cost Multiplier",
        description="Extra credit cost multiplier when using Auphonic",
        category="costs",
        type="number",
        default_value=2.0,
        min_value=1.0,
        max_value=10.0,
        help_text="Base credits * this multiplier when using Auphonic pipeline. Example: 2.0 = double cost"
    ),
    TierFeatureDefinition(
        key="elevenlabs_cost_multiplier",
        label="ElevenLabs Cost Multiplier",
        description="Extra credit cost multiplier for ElevenLabs TTS",
        category="costs",
        type="number",
        default_value=3.0,
        min_value=1.0,
        max_value=10.0,
        help_text="Base TTS credits * this multiplier for ElevenLabs. Example: 3.0 = triple cost"
    ),
    TierFeatureDefinition(
        key="storage_gb_included",
        label="Storage GB Included",
        description="Included cloud storage in gigabytes",
        category="costs",
        type="number",
        default_value=10,
        min_value=0,
        max_value=10000,
        help_text="Amount of cloud storage included in plan"
    ),
]


__all__ = [
    "TierConfiguration",
    "TierConfigurationHistory",
    "TierFeatureDefinition",
    "TIER_FEATURE_DEFINITIONS",
]
