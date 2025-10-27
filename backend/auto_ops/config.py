"""Configuration objects for the auto-ops alert orchestration system."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class AutoOpsSettings(BaseSettings):
    """Pydantic settings describing how the orchestrator should run."""

    slack_bot_token: str = Field(
        ..., description="Bot token used to authenticate with the Slack Web API."
    )
    slack_alert_channel: str = Field(
        ..., description="Channel ID where alert notifications are posted."
    )
    openai_api_key: str = Field(
        ..., description="API key for GitHub Models or OpenAI (powers the cooperating agents)."
    )
    api_base_url: Optional[str] = Field(
        None,
        description=(
            "Optional API base URL. Use 'https://models.inference.ai.azure.com' for GitHub Models, "
            "or leave None for standard OpenAI API."
        ),
    )
    repository_root: Path = Field(
        Path("."),
        description=(
            "Absolute path to the repository root. This is passed to the agents so they "
            "can reason about the layout of the codebase."
        ),
    )
    max_iterations: int = Field(
        3,
        ge=1,
        le=6,
        description="Maximum number of fix/review negotiation rounds before giving up.",
    )
    poll_interval_seconds: int = Field(
        30,
        ge=10,
        description="When running in daemon mode, how often to poll Slack for new alerts.",
    )
    daemon_mode: bool = Field(
        False,
        description=(
            "If True the runner will stay active and poll Slack forever. When False it "
            "processes the backlog once and exits."
        ),
    )
    state_file: Path = Field(
        Path("auto_ops_state.json"),
        description="File used to persist the timestamp of the most recent processed alert.",
    )
    model: str = Field(
        "gpt-4o-mini",
        description=(
            "Model name to use. GitHub Models examples: 'gpt-4o', 'o1-preview', "
            "'claude-3.5-sonnet', 'gemini-2.0-flash-exp'. OpenAI: 'gpt-4o-mini', 'gpt-4o'."
        ),
    )
    dry_run: bool = Field(
        False,
        description=(
            "When enabled the orchestrator will run the agents but avoid posting back to Slack."
        ),
    )
    slack_thread_prefix: Optional[str] = Field(
        None,
        description=(
            "Optional prefix added to Slack thread replies so humans can quickly identify"
            " automated responses."
        ),
    )
    alert_cooldown_hours: int = Field(
        24,
        ge=1,
        le=168,  # max 1 week
        description=(
            "Prevent re-processing the same alert within this many hours. "
            "Prevents repetitive comments on persistent alerts."
        ),
    )

    class Config:
        env_prefix = "AUTO_OPS_"
        env_file = [".env.local", ".env"]  # Try .env.local first, then .env
        env_file_encoding = "utf-8"
        extra = "ignore"


__all__ = ["AutoOpsSettings"]
