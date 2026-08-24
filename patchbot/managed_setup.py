"""One-time setup and scheduling for the `managed` (Claude Managed Agents)
fix backend. Not part of the per-fix hot path: `patchbot managed init`
creates the Agent/Environment/Vault once; `patchbot managed deploy` sets up
a cron-scheduled session that scans + fixes without any CI at all.
"""
from __future__ import annotations

import os

SYSTEM_PROMPT = (
    "You are a security-fix coding agent. You are given a specific CVE/GHSA "
    "advisory, a package, and a target version. Make the minimal code and "
    "dependency changes needed to resolve it, run the project's tests if "
    "asked to, and commit your work. Do not touch files unrelated to the fix."
)

DEPLOY_PROMPT_TEMPLATE = (
    "In this repository: install patchbot (`pip install patchbot`), run "
    "`patchbot scan`, and for every finding either bump the package "
    "deterministically or fix the code so it passes, then push a branch "
    "per package and open a pull request for each one via the GitHub tools."
)


def _client():
    import anthropic
    return anthropic.Anthropic()


def cmd_init(args) -> int:
    client = _client()

    agent = client.beta.agents.create(
        name="patchbot-fixer",
        model="claude-opus-5",
        system=SYSTEM_PROMPT,
        mcp_servers=[{"type": "url", "name": "github", "url": "https://api.githubcopilot.com/mcp/"}],
        tools=[
            {"type": "agent_toolset_20260401"},
            {"type": "mcp_toolset", "mcp_server_name": "github"},
        ],
    )
    environment = client.beta.environments.create(
        name=f"patchbot-env-{agent.id}",
        config={
            "type": "cloud",
            "networking": {"type": "limited", "allow_package_managers": True, "allow_mcp_servers": True},
        },
    )
    vault = client.beta.vaults.create(name=f"patchbot-vault-{agent.id}")
    token = args.github_mcp_token or os.environ.get("GITHUB_MCP_TOKEN")
    if token:
        client.beta.vaults.credentials.create(
            vault.id,
            display_name="GitHub MCP",
            auth={
                "type": "mcp_oauth",
                "mcp_server_url": "https://api.githubcopilot.com/mcp/",
                "access_token": token,
            },
        )
    else:
        print("warning: no --github-mcp-token given; add a GitHub MCP credential to the vault before using it.")

    print(f"agent_id       = {agent.id}")
    print(f"environment_id = {environment.id}")
    print(f"vault_id       = {vault.id}")
    print()
    print("Set these as repo secrets, or in patchbot.toml under [fix.managed], "
          "or as PATCHBOT_MANAGED_AGENT_ID / _ENVIRONMENT_ID / _VAULT_ID.")
    return 0


def cmd_deploy(args) -> int:
    client = _client()
    repos = [r.strip() for r in args.repos.split(",") if r.strip()]
    session_kwargs = dict(
        agent=args.agent_id,
        environment_id=args.environment_id,
        vault_ids=[args.vault_id],
        initial_events=[{"type": "user.message", "content": [{"type": "text", "text": DEPLOY_PROMPT_TEMPLATE}]}],
        schedule={"type": "cron", "expression": args.cron, "timezone": args.tz},
    )
    if repos:
        session_kwargs["resources"] = [
            {
                "type": "github_repository",
                "url": f"https://github.com/{repo}",
                "authorization_token": os.environ.get("GITHUB_TOKEN", ""),
            }
            for repo in repos
        ]
    deployment = client.beta.deployments.create(name=f"patchbot-{'-'.join(repos) or 'deploy'}", **session_kwargs)
    print(f"deployment_id = {deployment.id}")
    print(f"next runs: {deployment.schedule.upcoming_runs_at}")
    if args.run_now:
        run = client.beta.deployments.run(deployment.id)
        print(f"manual run: {run.id}")
    return 0


def cmd_list(args) -> int:
    client = _client()
    for d in client.beta.deployments.list():
        print(d.id, d.status, d.schedule.expression if d.schedule else "-")
    return 0


def cmd_pause(args) -> int:
    _client().beta.deployments.pause(args.deployment_id)
    return 0


def cmd_unpause(args) -> int:
    _client().beta.deployments.unpause(args.deployment_id)
    return 0


def add_subparser(sub) -> None:
    managed = sub.add_parser("managed", help="set up and manage the Claude Managed Agents fix backend")
    managed_sub = managed.add_subparsers(dest="managed_command", required=True)

    init_p = managed_sub.add_parser("init", help="create the agent/environment/vault once")
    init_p.add_argument("--github-mcp-token", help="GitHub MCP OAuth access token for the vault")
    init_p.set_defaults(func=cmd_init)

    deploy_p = managed_sub.add_parser("deploy", help="schedule a recurring scan+fix session (no CI needed)")
    deploy_p.add_argument("--repos", required=True, help="comma-separated owner/repo list")
    deploy_p.add_argument("--cron", required=True, help='cron expression, e.g. "0 6 * * *"')
    deploy_p.add_argument("--tz", default="UTC", help="IANA timezone (default UTC)")
    deploy_p.add_argument("--agent-id", required=True)
    deploy_p.add_argument("--environment-id", required=True)
    deploy_p.add_argument("--vault-id", required=True)
    deploy_p.add_argument("--run-now", action="store_true", help="also trigger one run immediately")
    deploy_p.set_defaults(func=cmd_deploy)

    list_p = managed_sub.add_parser("list", help="list deployments")
    list_p.set_defaults(func=cmd_list)

    pause_p = managed_sub.add_parser("pause", help="pause a deployment's schedule")
    pause_p.add_argument("deployment_id")
    pause_p.set_defaults(func=cmd_pause)

    unpause_p = managed_sub.add_parser("unpause", help="resume a paused deployment")
    unpause_p.add_argument("deployment_id")
    unpause_p.set_defaults(func=cmd_unpause)
