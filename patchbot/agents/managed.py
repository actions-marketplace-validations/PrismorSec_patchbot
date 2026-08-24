"""Claude Managed Agents backend: the fix runs in Anthropic's sandbox, not
on the CI runner. The GitHub token never enters the sandbox — repo
clone/push goes through Anthropic's git proxy (`authorization_token`) and
PR creation goes through a vaulted GitHub MCP credential.

Requires `patchbot managed init` to have been run once (see
patchbot/managed_setup.py) and its three IDs supplied via `config`:
`agent_id`, `environment_id`, `vault_id` — normally read from
PATCHBOT_MANAGED_AGENT_ID / _ENVIRONMENT_ID / _VAULT_ID.

The caller (fix.py) is responsible for host-side verification after this
returns — a session's own claim of success is never the fix gate.
"""
from __future__ import annotations

import os
import subprocess
from typing import Optional

TERMINAL_IDLE_REASONS = {"end_turn", "retries_exhausted", "budget_reached"}


def _remote_url(cwd: str) -> str:
    result = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"], cwd=cwd, capture_output=True, text=True,
    )
    return result.stdout.strip()


def run(prompt: str, cwd: str, model: Optional[str] = None, timeout: int = 600,
        config: Optional[dict] = None) -> int:
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "the 'managed' agent needs the anthropic package: pip install patchbot[api]"
        ) from exc

    config = config or {}
    agent_id = config.get("agent_id") or os.environ.get("PATCHBOT_MANAGED_AGENT_ID")
    environment_id = config.get("environment_id") or os.environ.get("PATCHBOT_MANAGED_ENVIRONMENT_ID")
    vault_id = config.get("vault_id") or os.environ.get("PATCHBOT_MANAGED_VAULT_ID")
    github_token = os.environ.get("GITHUB_TOKEN")
    if not (agent_id and environment_id and vault_id):
        raise RuntimeError(
            "agent 'managed' requires agent_id/environment_id/vault_id "
            "(run `patchbot managed init` first) — see README"
        )
    if not github_token:
        raise RuntimeError("agent 'managed' requires GITHUB_TOKEN in the environment")

    branch = config.get("branch")
    repo_url = _remote_url(cwd)
    if not repo_url:
        raise RuntimeError("agent 'managed' requires a GitHub 'origin' remote in this repo")

    client = anthropic.Anthropic()
    session_kwargs = dict(
        agent=agent_id,
        environment_id=environment_id,
        vault_ids=[vault_id],
        resources=[{
            "type": "github_repository",
            "url": repo_url,
            "authorization_token": github_token,
            **({"checkout": {"type": "branch", "name": branch}} if branch else {}),
        }],
        initial_events=[{"type": "user.message", "content": [{"type": "text", "text": prompt}]}],
    )
    if model:
        session_kwargs["agent"] = {"type": "agent_with_overrides", "id": agent_id, "model": model}

    session = client.beta.sessions.create(**session_kwargs)
    print(f"[managed] session {session.id} — https://platform.claude.com/sessions/{session.id}")

    saw_error = False
    stop_reason_type = None
    stream = client.beta.sessions.events.stream(session.id)
    for event in stream:
        if event.type == "session.error":
            saw_error = True
        if event.type == "session.status_terminated":
            break
        if event.type == "session.status_idle":
            stop_reason = getattr(event, "stop_reason", None)
            stop_reason_type = getattr(stop_reason, "type", None)
            if stop_reason_type == "requires_action":
                continue
            break

    # The rescan/test verification that actually gates the PR happens
    # host-side in fix.py — this is only "did the session run cleanly".
    return 1 if saw_error or stop_reason_type == "retries_exhausted" else 0
