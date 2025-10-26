"""End-to-end alert orchestration for the cooperative agent workflow."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, List, Sequence

from openai import OpenAI

from .agents import (
    AgentExecutionError,
    AnalysisAgent,
    FixAgent,
    ReviewAgent,
    build_summary,
)
from .config import AutoOpsSettings
from .models import AgentTurn, Alert, AnalysisResult, RunSummary, Severity
from .slack import SlackAlertClient

LOGGER = logging.getLogger(__name__)


class AlertOrchestrator:
    """Coordinates the alert triage lifecycle across three cooperating agents."""

    def __init__(
        self,
        *,
        settings: AutoOpsSettings,
        slack_client: SlackAlertClient,
        openai_client: OpenAI,
    ) -> None:
        self._settings = settings
        self._slack = slack_client
        self._analysis_agent = AnalysisAgent(
            openai_client,
            settings.model,
            system_prompt="You are a pragmatic on-call engineer triaging production incidents.",
            temperature=0.1,
        )
        self._fix_agent = FixAgent(
            openai_client,
            settings.model,
            system_prompt=(
                "You are a senior production engineer with write access to the CloudPod repo. "
                "Generate precise remediation plans and code patches when possible."
            ),
            temperature=0.2,
            repository_root=str(settings.repository_root),
        )
        self._review_agent = ReviewAgent(
            openai_client,
            settings.model,
            system_prompt=(
                "You lead change management. Approve only changes that are safe, well-validated, and reversible."
            ),
            temperature=0.0,
        )

    @property
    def settings(self) -> AutoOpsSettings:
        return self._settings

    def process_alert(self, alert: Alert) -> RunSummary:
        """Process a single alert and optionally notify Slack with the outcome."""

        LOGGER.info("Processing alert %s", alert.metadata.ts)
        try:
            analysis = self._analysis_agent.analyze(alert)
        except AgentExecutionError:
            LOGGER.exception("Analysis agent failed")
            return self._handle_agent_failure(alert, stage="analysis")

        turns: List[AgentTurn] = []
        for iteration in range(1, self._settings.max_iterations + 1):
            LOGGER.info("Iteration %s for alert %s", iteration, alert.metadata.ts)
            try:
                proposal = self._fix_agent.propose(alert, analysis, turns)
            except AgentExecutionError:
                LOGGER.exception("Fix agent failed")
                return self._handle_agent_failure(alert, stage="fix", analysis=analysis, turns=turns)

            try:
                review = self._review_agent.review(alert, analysis, proposal, turns)
            except AgentExecutionError:
                LOGGER.exception("Review agent failed")
                return self._handle_agent_failure(alert, stage="review", analysis=analysis, turns=turns)

            turn = AgentTurn(proposal=proposal, review=review)
            turns.append(turn)
            if review.approved:
                break

        summary = build_summary(analysis, turns)
        self._post_to_slack(alert, summary)
        return summary

    def process_alerts(self, alerts: Sequence[Alert]) -> List[RunSummary]:
        """Process a batch of alerts sequentially."""

        summaries: List[RunSummary] = []
        for alert in alerts:
            summaries.append(self.process_alert(alert))
        return summaries

    def _post_to_slack(self, alert: Alert, summary: RunSummary) -> None:
        if self._settings.dry_run:
            LOGGER.debug("Dry run enabled; skipping Slack post")
            return
        prefix = f"{self._settings.slack_thread_prefix} " if self._settings.slack_thread_prefix else ""
        text = f"{prefix}Automation result: {summary.final_status}"
        blocks = summary.to_slack_blocks()
        try:
            self._slack.post_reply(alert.metadata.ts, text=text, blocks=blocks)
        except Exception:  # pragma: no cover - defensive logging
            LOGGER.exception("Failed to post automation summary to Slack")

    def _handle_agent_failure(
        self,
        alert: Alert,
        *,
        stage: str,
        analysis: AnalysisResult | None = None,
        turns: Iterable[AgentTurn] | None = None,
    ) -> RunSummary:
        message = f"Automation stalled during the {stage} stage. Human intervention required."
        analysis_result = analysis or AnalysisResult(
            summary="Automation failed before analysis could be completed.",
            suspected_causes=[alert.payload.text[:280] or "Unknown issue"],
            diagnostic_steps=[],
            severity=Severity.HIGH,
            requires_manual_confirmation=True,
        )
        fallback_summary = build_summary(analysis_result, list(turns or []))
        fallback_summary.final_status = message
        self._post_to_slack(alert, fallback_summary)
        return fallback_summary


class StateTracker:
    """Persists the timestamp of the latest processed alert across runs."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._state = {"latest_ts": None}
        self._load()

    @property
    def latest_ts(self) -> str | None:
        return self._state.get("latest_ts")

    def update(self, ts: str) -> None:
        self._state["latest_ts"] = ts
        self._persist()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            self._state = json.loads(self._path.read_text("utf-8"))
        except json.JSONDecodeError:
            LOGGER.warning("State file %s was invalid JSON; resetting", self._path)
            self._state = {"latest_ts": None}

    def _persist(self) -> None:
        if self._path.parent and not self._path.parent.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")


__all__ = ["AlertOrchestrator", "StateTracker"]
