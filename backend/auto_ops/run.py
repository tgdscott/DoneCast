"""Command line entrypoint for the auto-ops orchestrator."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import Optional

from openai import OpenAI

from .config import AutoOpsSettings
from .orchestrator import AlertOrchestrator, StateTracker
from .slack import SlackAlertClient


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the CloudPod repo auto-ops orchestrator")
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run continuously regardless of the AUTO_OPS_DAEMON_MODE setting.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process the backlog once and exit, even if AUTO_OPS_DAEMON_MODE is enabled.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level (default: INFO)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    settings = AutoOpsSettings()
    slack_client = SlackAlertClient(settings.slack_bot_token, settings.slack_alert_channel)
    
    # Create OpenAI client with optional custom base_url for GitHub Models
    openai_kwargs = {"api_key": settings.openai_api_key}
    if settings.api_base_url:
        openai_kwargs["base_url"] = settings.api_base_url
    openai_client = OpenAI(**openai_kwargs)
    
    orchestrator = AlertOrchestrator(settings=settings, slack_client=slack_client, openai_client=openai_client)
    tracker = StateTracker(settings.state_file)

    daemon_enabled = args.daemon or (settings.daemon_mode and not args.once)

    while True:
        alerts = slack_client.fetch_alerts(oldest=tracker.latest_ts)
        if tracker.latest_ts is not None:
            alerts = [alert for alert in alerts if float(alert.metadata.ts) > float(tracker.latest_ts)]
        if alerts:
            orchestrator.process_alerts(alerts)
            tracker.update(alerts[-1].metadata.ts)
        if not daemon_enabled:
            break
        time.sleep(settings.poll_interval_seconds)

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
