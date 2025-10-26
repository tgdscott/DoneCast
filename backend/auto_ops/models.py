"""Pydantic models shared across the alert automation package."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Iterable, List, Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """High-level severity used by the analysis agent."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AlertMetadata(BaseModel):
    """Metadata about the original Slack alert message."""

    channel: str
    ts: str = Field(..., description="Slack timestamp identifier for the message.")
    sender: Optional[str] = Field(None, description="Slack user ID who posted the alert.")
    permalink: Optional[str] = None
    severity: Optional[str] = Field(None, description="Severity extracted from monitoring system (critical/high/medium/low).")


class AlertPayload(BaseModel):
    """User-facing details extracted from the Slack message."""

    text: str
    attachments: List[str] = Field(default_factory=list)


class Alert(BaseModel):
    """Full alert data consumed by the orchestrator."""

    metadata: AlertMetadata
    payload: AlertPayload
    created_at: datetime


class AnalysisResult(BaseModel):
    """Structured output from the analysis agent."""

    summary: str
    suspected_causes: List[str]
    diagnostic_steps: List[str]
    severity: Severity
    requires_manual_confirmation: bool = False


class FixProposal(BaseModel):
    """Output produced by the fixer agent during each iteration."""

    plan: str
    patch: Optional[str] = None
    validation_steps: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class ReviewResult(BaseModel):
    """Reviewer agent decision for a single proposal."""

    approved: bool
    feedback: str
    risks: List[str] = Field(default_factory=list)


class AgentTurn(BaseModel):
    """Represents one round-trip between the fixer and reviewer agents."""

    proposal: FixProposal
    review: ReviewResult


class RunSummary(BaseModel):
    """Summary returned to Slack once the automation finishes working the alert."""

    analysis: AnalysisResult
    turns: List[AgentTurn]
    final_status: str

    def to_slack_blocks(self) -> List[dict]:
        """Render the run summary as a set of Slack block kit elements."""

        blocks: List[dict] = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Alert triage summary*\n{self.analysis.summary}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity*\n{self.analysis.severity.value.title()}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Manual confirmation*\n{'Yes' if self.analysis.requires_manual_confirmation else 'No'}",
                    },
                ],
            },
        ]

        if self.analysis.suspected_causes:
            causes = "\n".join(f"• {item}" for item in self.analysis.suspected_causes)
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Suspected causes*\n{causes}"},
                }
            )

        if self.turns:
            for idx, turn in enumerate(self.turns, start=1):
                blocks.append(
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"*Iteration {idx}: Fixer confidence {turn.proposal.confidence:.0%}*\n"
                                f"{turn.proposal.plan}\n\n"
                                f"*Reviewer*\n{'✅ Approved' if turn.review.approved else '✏️ Revisions needed'}\n"
                                f"{turn.review.feedback}"
                            ),
                        },
                    }
                )

        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Final status:* {self.final_status}",
                    }
                ],
            }
        )
        return blocks


def render_bullet_list(items: Iterable[str]) -> str:
    return "\n".join(f"• {item}" for item in items)


__all__ = [
    "Alert",
    "AlertMetadata",
    "AlertPayload",
    "AnalysisResult",
    "FixProposal",
    "ReviewResult",
    "AgentTurn",
    "RunSummary",
    "Severity",
    "render_bullet_list",
]
