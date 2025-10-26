# Auto-Ops Alert Orchestrator

This document explains how to wire the new cooperative-agent workflow into your infrastructure monitoring stack. The goal is to let one agent triage Slack alerts, loop with a fixer agent that generates candidate remediations, and have a reviewer agent sign off before we attempt deployment. The instructions below assume you already have a Slack channel where alerts are delivered and that you want the new auto-ops service to act on those alerts without human involvement.

## Prerequisites

- Python 3.11+ installed locally or on the host where the orchestrator will run.
- Ability to create/manage Slack apps and tokens in the target workspace.
- An OpenAI API key (or another compatible provider if you adapt the agents).
- Git access to this repository so the orchestrator can inspect and eventually modify code.

When running inside a production environment (e.g., a VM or container), ensure that outbound HTTPS access to Slack and your LLM provider is allowed.

## 1. Create the Slack plumbing

1. Visit <https://api.slack.com/apps> and click **Create New App → From scratch**. Give the app a descriptive name such as `Auto Ops Orchestrator` and select the workspace that receives alerts.
2. Under **OAuth & Permissions**, add the following **Bot Token Scopes**:
   - `channels:history` so the bot can read public-channel alerts.
   - `groups:history` if alerts arrive in private channels.
   - `im:history` and/or `mpim:history` if alerts arrive via DMs or group DMs.
   - `chat:write` so the bot can respond with summaries/fixes.
   - `channels:join` so the bot can automatically join the alert channel if it is public.
3. Click **Install to Workspace** (or **Reinstall to Workspace**) and approve the permissions. Slack will show you the **Bot User OAuth Token** (`xoxb-…`); copy this string because you will use it in the environment configuration.
4. Invite the bot to the alert channel using `/invite @auto-ops` (replace with your bot name). The bot must be a member to read or post messages.
5. Determine the channel ID where alerts arrive. Open the channel in Slack, click the channel name, choose **View channel details → More → Copy channel ID**, or right-click the channel and select **Copy link** then copy the `CXXXXXXXX`/`GXXXXXXXX` segment.
6. (Optional) If you want Slack to notify the orchestrator immediately instead of polling, configure **Event Subscriptions** and expose a webhook endpoint; the supplied code assumes polling, so this step is not required unless you extend the orchestrator.

## 2. Provision model credentials

The orchestrator currently targets OpenAI models. Provide an API key with access to `gpt-4o-mini` or better. Export it as `AUTO_OPS_OPENAI_API_KEY` (see the environment table below). If you prefer a different vendor, swap the OpenAI client inside `backend/auto_ops/agents.py` and keep the JSON outputs the same. You can validate the credential with:

```bash
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $AUTO_OPS_OPENAI_API_KEY"
```

The request should return a JSON payload listing available models; if it returns 401/403, double-check the key and account permissions.

## 3. Configure environment variables

The runner reads all configuration through `backend/auto_ops/config.py`. The most important variables are:

| Variable | Description |
| --- | --- |
| `AUTO_OPS_SLACK_BOT_TOKEN` | Bot token created in step 1. |
| `AUTO_OPS_SLACK_ALERT_CHANNEL` | Channel ID where alerts arrive. |
| `AUTO_OPS_OPENAI_API_KEY` | API key for the model powering the agents. |
| `AUTO_OPS_REPOSITORY_ROOT` | Optional path hint passed to the fixer agent (defaults to the repo root). |
| `AUTO_OPS_MAX_ITERATIONS` | Override the maximum fixer/reviewer back-and-forth (default 3). |
| `AUTO_OPS_DAEMON_MODE` | Set to `true` to keep the runner polling continuously. |
| `AUTO_OPS_POLL_INTERVAL_SECONDS` | How often to poll Slack when daemon mode is on (default 30s). |
| `AUTO_OPS_STATE_FILE` | Path to the JSON file that stores the last processed Slack timestamp. |
| `AUTO_OPS_SLACK_THREAD_PREFIX` | Optional string prepended to Slack replies (e.g. `[auto-ops]`). |
| `AUTO_OPS_DRY_RUN` | Set to `true` to test the agents without posting back to Slack. |

You can drop these values inside the backend `.env` that is already loaded by Pydantic. A starter `.env` section might look like:

```
# Slack
AUTO_OPS_SLACK_BOT_TOKEN=xoxb-your-token
AUTO_OPS_SLACK_ALERT_CHANNEL=C01234567

# Models
AUTO_OPS_OPENAI_API_KEY=sk-...

# Runtime
AUTO_OPS_STATE_FILE=/var/lib/auto-ops/state.json
AUTO_OPS_DAEMON_MODE=true
AUTO_OPS_POLL_INTERVAL_SECONDS=60
AUTO_OPS_DRY_RUN=true  # flip to false once confident
```

Ensure the state file directory exists and is writable by the user running the orchestrator; otherwise the runner will fail to persist its progress.

## 4. Install Python dependencies

From the `backend/` directory run:

```bash
pip install -r requirements.txt
```

This pulls in `slack_sdk` (Slack Web API) and `openai`. If you are deploying to a container image, bake this command into your Dockerfile or build script.

## 5. Run the orchestrator

From the repository root:

```bash
python -m backend.auto_ops.run --log-level INFO --once
```

* `--once` processes the backlog one time and exits. Drop the flag (or add `--daemon`) to keep it polling.
* Use `AUTO_OPS_DRY_RUN=true` the first time to verify the workflow without spamming Slack.
* If you run in daemon mode, supervise the process with systemd, supervisord, Docker, or your preferred job scheduler. Example systemd unit:

  ```ini
  [Unit]
  Description=Auto Ops Orchestrator
  After=network.target

  [Service]
  WorkingDirectory=/opt/cloudpod
  EnvironmentFile=/opt/cloudpod/backend/.env
  ExecStart=/usr/bin/python -m backend.auto_ops.run --log-level INFO --daemon
  Restart=always

  [Install]
  WantedBy=multi-user.target
  ```

* To run manually against a single alert, copy the Slack timestamp (e.g., `1718300000.123456`) and invoke `python -m backend.auto_ops.run --since 1718300000.123456 --once`.

## 6. What the agents do

1. **Analysis agent** condenses the alert into a summary, guesses likely causes, and lists diagnostics.
2. **Fix agent** drafts a remediation plan plus optional patches and validation steps.
3. **Review agent** evaluates the fix; if it rejects the proposal, the orchestrator lets them iterate (up to `AUTO_OPS_MAX_ITERATIONS`).
4. Once an iteration is approved (or the loop ends), the orchestrator posts a Slack thread reply summarizing the conversation and whether human follow-up is required.

The architecture is intentionally modular. If you want a deployment agent to ship changes automatically, extend `backend/auto_ops/orchestrator.py` after the reviewer approves and hook it into your existing CI/CD process.

## 7. Operational tips

- Keep the state file (`auto_ops_state.json` by default) in persistent storage when running inside a container or Cloud Run job.
- Add unit tests/mocks before letting the fixer agent push commits automatically.
- Provide the agents with runbooks or service documentation by enriching the prompts in `backend/auto_ops/agents.py`.
- Slack’s rate limits are generous, but the orchestrator already batches requests and sorts results chronologically.
- Periodically rotate the Slack and OpenAI tokens. Restart the orchestrator after updating credentials.
- If the orchestrator fails with `SlackApiError: not_in_channel`, re-run `/invite @auto-ops` in the alert channel.
- Use `AUTO_OPS_SLACK_THREAD_PREFIX` to make automated responses easy to filter during incident post-mortems.

## 8. Dry-run validation checklist

Complete the following steps before allowing the orchestrator to deploy fixes automatically:

1. Run `python -m backend.auto_ops.run --log-level DEBUG --once` while `AUTO_OPS_DRY_RUN=true`. Confirm the log shows:
   - successful authentication to Slack,
   - retrieval of at least one recent alert message,
   - agent analysis/fix/review outputs, and
   - a simulated Slack reply (it will mention "dry run" instead of posting).
2. Review the generated `auto_ops_state.json` (or your custom state file) to verify that the last processed timestamp matches the alert you expected.
3. Manually post a dummy alert message to the channel and re-run the orchestrator to confirm it processes the new message.
4. Flip `AUTO_OPS_DRY_RUN=false`, rerun the orchestrator, and check Slack for the threaded response. Keep the first run supervised to ensure the agents behave as expected.

Once the environment variables are in place and dependencies installed, the orchestrator can autonomously triage alert threads and hand the outcome back into Slack.
