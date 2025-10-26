"""Agent implementations powered by the OpenAI API."""

from __future__ import annotations

import json
from typing import Iterable, List

from openai import OpenAI, OpenAIError

from .models import (
    AgentTurn,
    Alert,
    AnalysisResult,
    FixProposal,
    ReviewResult,
    RunSummary,
    Severity,
)


class AgentExecutionError(RuntimeError):
    """Raised when an agent call fails or returns unexpected output."""


class BaseAgent:
    """Common helper functionality for all agents."""

    def __init__(self, client: OpenAI, model: str, system_prompt: str, temperature: float = 0.2) -> None:
        self._client = client
        self._model = model
        self._system_prompt = system_prompt
        self._temperature = temperature

    def _complete(self, user_prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except OpenAIError as exc:
            raise AgentExecutionError("Agent call failed") from exc
        try:
            return response.choices[0].message.content or ""
        except (AttributeError, IndexError) as exc:  # pragma: no cover - defensive
            raise AgentExecutionError("Agent response missing content") from exc

    def _complete_json(self, user_prompt: str) -> dict:
        content = self._complete(user_prompt)
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise AgentExecutionError(f"Agent returned invalid JSON: {content}") from exc


class AnalysisAgent(BaseAgent):
    """Agent responsible for translating alerts into actionable summaries."""

    def analyze(self, alert: Alert) -> AnalysisResult:
        prompt = f"""
You are the site reliability lead. A monitoring alert has fired in Slack.
Return JSON with the following keys: summary, suspected_causes (list of strings), diagnostic_steps (list of strings), severity (one of critical, high, medium, low), requires_manual_confirmation (boolean).

Alert message:
---
{alert.payload.text}
---
Attachments:
{chr(10).join(alert.payload.attachments) if alert.payload.attachments else 'None'}
        """
        payload = self._complete_json(prompt)
        return AnalysisResult(
            summary=payload.get("summary", ""),
            suspected_causes=payload.get("suspected_causes", []),
            diagnostic_steps=payload.get("diagnostic_steps", []),
            severity=Severity(payload.get("severity", "medium")),
            requires_manual_confirmation=bool(payload.get("requires_manual_confirmation", False)),
        )


class FixAgent(BaseAgent):
    """Agent that proposes concrete remediation steps."""

    def __init__(self, *args, repository_root: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._repository_root = repository_root

    def propose(self, alert: Alert, analysis: AnalysisResult, history: Iterable[AgentTurn]) -> FixProposal:
        history_snippets: List[str] = []
        for idx, turn in enumerate(history, start=1):
            status = "approved" if turn.review.approved else "needs revision"
            history_snippets.append(
                f"Iteration {idx}: Fixer confidence {turn.proposal.confidence:.0%}, {status}\n"
                f"Plan: {turn.proposal.plan}\n"
                f"Reviewer feedback: {turn.review.feedback}"
            )
        prompt = """
You are the primary incident responder tasked with implementing a fix.
You must return JSON with the keys plan (string), patch (string or null), validation_steps (list of strings), confidence (float between 0 and 1).
Use patch to share code diffs in unified format if relevant. Keep validation steps actionable and executable in the repo {repo_root}.
""".strip().format(repo_root=self._repository_root)
        prompt += "\n\nAlert summary:\n" + analysis.summary
        if analysis.diagnostic_steps:
            prompt += "\n\nDiagnostics already suggested:\n" + "\n".join(analysis.diagnostic_steps)
        if history_snippets:
            prompt += "\n\nConversation so far:\n" + "\n---\n".join(history_snippets)
        payload = self._complete_json(prompt)
        return FixProposal(
            plan=payload.get("plan", ""),
            patch=payload.get("patch"),
            validation_steps=payload.get("validation_steps", []),
            confidence=float(payload.get("confidence", 0.5)),
        )


class ReviewAgent(BaseAgent):
    """Reviewer that verifies whether the proposed fix is safe to ship."""

    def review(self, alert: Alert, analysis: AnalysisResult, proposal: FixProposal, history: Iterable[AgentTurn]) -> ReviewResult:
        history_snippets = []
        for idx, turn in enumerate(history, start=1):
            history_snippets.append(
                f"Iteration {idx} decision: {'approved' if turn.review.approved else 'rejected'}\n"
                f"Feedback: {turn.review.feedback}"
            )
        prompt = f"""
You are the change management reviewer. Inspect the proposed remediation and decide whether it is safe.
Return JSON with the keys approved (boolean), feedback (string), risks (list of strings).

Alert summary: {analysis.summary}
Fixer confidence: {proposal.confidence}
Fix plan: {proposal.plan}
Suggested validation: {proposal.validation_steps}
Patch:
{proposal.patch or 'No patch provided'}
        """
        if history_snippets:
            prompt += "\nPrevious rounds:\n" + "\n".join(history_snippets)
        payload = self._complete_json(prompt)
        return ReviewResult(
            approved=bool(payload.get("approved", False)),
            feedback=payload.get("feedback", ""),
            risks=payload.get("risks", []),
        )


def build_summary(analysis: AnalysisResult, turns: List[AgentTurn]) -> RunSummary:
    """Create a RunSummary object that encapsulates the automation results."""

    final_status = "Changes approved automatically" if turns and turns[-1].review.approved else "Automation requires human follow-up"
    return RunSummary(analysis=analysis, turns=turns, final_status=final_status)


__all__ = [
    "AgentExecutionError",
    "AnalysisAgent",
    "FixAgent",
    "ReviewAgent",
    "build_summary",
]
