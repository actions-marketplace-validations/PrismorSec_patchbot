<div align="center">

# patchbot

**Vulnerability scanning with your scanners, your threat feeds, and a coding agent that opens the fix PR.**

[![PyPI](https://img.shields.io/pypi/v/patchbot?color=blue)](https://pypi.org/project/patchbot/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://pypi.org/project/patchbot/)
[![CI](https://github.com/PrismorSec/patchbot/actions/workflows/ci.yml/badge.svg)](https://github.com/PrismorSec/patchbot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![GitHub Action](https://img.shields.io/badge/GitHub-Action-2088FF?logo=githubactions&logoColor=white)](#github-actions)

<img src="docs/img/scan.png" alt="patchbot scan output" width="800">

</div>

---

patchbot is a modular dependency-vulnerability pipeline. It inventories the packages in a repository, matches them against any threat feed, accepts findings from any scanner, and fixes what it finds — deterministically when a version bump is enough, with a coding agent when it is not. Every fix is re-scanned before a pull request is opened.

It runs as a CLI, as a GitHub Action, or as a scheduled [Claude Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview) deployment that needs no CI at all.

## Why patchbot

| | Dependabot / Renovate | Trivy / Grype alone | **patchbot** |
|---|---|---|---|
| Bring your own threat feed (private advisories, OSV-format) | — | — | ✅ |
| Bring your own scanner (any tool that emits SARIF / Trivy / Grype JSON) | — | n/a | ✅ |
| Deterministic version bump + lockfile regen | ✅ | — | ✅ |
| Fixes that need **code changes** (breaking major bump, failing tests) | — | — | ✅ agent tier |
| Re-scan gates every PR | — | — | ✅ |
| Agent runs **off** the CI runner, secrets never enter the sandbox | — | — | ✅ Managed Agents |
| Works without CI (scheduled, any git host) | — | — | ✅ |

## Installation

```bash
pip install patchbot            # scan + deterministic fixes
pip install "patchbot[api]"     # + Anthropic-backed agent tiers (api, managed)
```

Requires Python 3.11+. No other runtime dependencies.

## Quick start

```bash
patchbot scan                    # inventory → OSV.dev → table report
patchbot fix --dry-run           # preview the fix plan, change nothing
patchbot fix --pr                # bump / fix, verify, open one PR per package
```

<img src="docs/img/fix-dry-run.png" alt="patchbot fix --dry-run" width="800">

## How it works

```
                 ┌─ feeds ───────────── OSV.dev · your OSV-format file / URL
inventory ───────┤                                            │
 (lockfiles,     └─ scanners ────────── trivy · grype · osv-scanner · any cmd
  CycloneDX SBOM)                                             │
                                                              ▼
                                                   findings (deduplicated)
                                                              │
                                             ┌────────────────┴────────────────┐
                                             ▼                                 ▼
                                      report                                 fix
                              table · json · SARIF              bump → verify → agent → verify → PR
```

**Inventory.** Built-in parsers for npm / pnpm / yarn lockfiles, `requirements*.txt`, `pyproject.toml`, `go.mod`, and `Cargo.toml`, plus any CycloneDX SBOM (`syft`, `cdxgen`, or your own) for ecosystems without a native parser.

**Feeds.** OSV.dev is on by default. A private feed is any file or URL serving OSV-schema JSON — no custom format to maintain.

**Scanners.** Wrappers for `trivy`, `grype`, and `osv-scanner`, or point the `command` scanner at any tool that writes SARIF, Trivy, Grype, or osv-scanner JSON to stdout.

**Fix.** A tiered loop, one branch per vulnerable package:

1. **Deterministic bump** — rewrite the pin to the lowest version that clears every advisory, regenerate the lockfile with the ecosystem's own tool. No model involved.
2. **Verify** — re-scan, run `test_cmd`, and reject any diff that reaches outside the dependency surface (CI config, dotfiles).
3. **Agent escalation** — only if step 2 fails. The agent's brief is the *failure* ("bumped `lodash` to 4.18.0; tests fail with …"), not the original task.
4. **Verify again**, then commit and open the PR with the advisory table in the body.

`--agent none` turns off step 3 for a pure deterministic mode.

## Commands

| Command | What it does |
|---|---|
| `patchbot scan [paths…]` | Run the pipeline and print a report. Exits non-zero when any finding meets `--fail-on` (default `high`). |
| `patchbot fix [paths…]` | Tiered fix loop. `--dry-run` previews, `--pr` pushes and opens pull requests via `gh`. |
| `patchbot plugins` | List every registered feed, scanner, and agent — built-in and third-party. |
| `patchbot managed …` | One-time setup (`init`) and scheduling (`deploy`, `list`, `pause`, `unpause`) for the Managed Agents backend. |

<details>
<summary><code>patchbot scan --format json</code></summary>
<br>
<img src="docs/img/scan-json.png" alt="patchbot scan --format json" width="800">
</details>

<details>
<summary><code>patchbot plugins</code></summary>
<br>
<img src="docs/img/plugins.png" alt="patchbot plugins" width="800">
</details>

## Configuration

`patchbot.toml` in the repository root. Every CLI flag overrides its config-file counterpart.

```toml
[inventory]
paths = ["."]
# sbom = "sbom.cdx.json"

[feeds.osv]
enabled = true

[feeds.internal]                # bring your own threat feed
type = "url"                    # or "file" with path = "…"
url  = "https://intel.example.com/advisories.json"

[scanners.trivy]
enabled = true

[scanners.custom]               # bring your own scanner
type   = "command"
cmd    = "./scan.sh"
format = "sarif"                # sarif | trivy | grype | osv-scanner

[report]
fail_on = "high"                # critical | high | medium | low | none
ignore  = ["GHSA-xxxx-xxxx-xxxx"]

[fix]
agent    = "claude"             # claude | codex | api | command | managed | none
model    = "claude-opus-5"      # optional; forwarded to the agent
max_prs  = 5
test_cmd = "npm test"
# cmd = "aider --yes --message {prompt}"     # agent = "command" only

[fix.managed]                   # agent = "managed" only — from `patchbot managed init`
agent_id       = "agent_…"
environment_id = "env_…"
vault_id       = "vlt_…"
```

## Choosing an agent backend

| Backend | Runs where | Needs | Best for |
|---|---|---|---|
| `claude` / `codex` | Your machine or runner, via the CLI on `PATH` | The CLI, already authenticated | Local development |
| `api` | Your runner, in-process | `pip install patchbot[api]`, `ANTHROPIC_API_KEY` | CI without Node |
| `command` | Wherever your tool runs | Any agent that takes a prompt (`aider`, `opencode`, …) | Non-Anthropic models |
| `managed` | **Anthropic's sandbox** — never your runner | `patchbot managed init` once, three IDs as secrets | CI where the agent must not see repo secrets |

### Managed Agents — the recommended CI backend

An agent with a shell on your CI runner sits next to your repository secrets. The `managed` backend moves it out: the session runs in a [Claude Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview) sandbox, `git push` is authenticated through Anthropic's git proxy, and the pull request is created through a vaulted GitHub MCP credential. The GitHub token never enters the sandbox. patchbot still re-scans the pushed branch host-side — a session's own success report is never the gate.

```bash
pip install "patchbot[api]"
patchbot managed init --github-mcp-token "$GITHUB_MCP_TOKEN"
# → agent_id, environment_id, vault_id  →  store as repo secrets
patchbot fix --agent managed --pr
```

## GitHub Actions

**Scan and publish to the Security tab**

```yaml
permissions:
  security-events: write
steps:
  - uses: actions/checkout@v4
  - uses: PrismorSec/patchbot@v0
    with:
      fail-on: high
```

<img src="docs/img/code-scanning.jpg" alt="Code scanning alerts detected by patchbot" width="800">

**Auto-fix with Managed Agents** (no Node, no agent on the runner)

```yaml
permissions:
  contents: write
  pull-requests: write
steps:
  - uses: actions/checkout@v4
  - uses: PrismorSec/patchbot@v0
    with:
      fix: "true"
      agent: managed
      managed-agent-id: ${{ secrets.PATCHBOT_AGENT_ID }}
      managed-environment-id: ${{ secrets.PATCHBOT_ENVIRONMENT_ID }}
      managed-vault-id: ${{ secrets.PATCHBOT_VAULT_ID }}
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Auto-fix with the in-runner `api` backend**

```yaml
permissions:
  contents: write
  pull-requests: write
  security-events: write
steps:
  - uses: actions/checkout@v4
  - uses: PrismorSec/patchbot@v0
    with:
      fix: "true"
      agent: api
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

**Weekly, against a private feed**

```yaml
on:
  schedule:
    - cron: "0 6 * * 1"
steps:
  - uses: actions/checkout@v4
  - uses: PrismorSec/patchbot@v0
    with:
      config: patchbot.toml    # [feeds.internal] url = …
```

All inputs are documented in [`action.yml`](./action.yml); a complete workflow lives in [`.github/workflows/patchbot-fix-example.yml`](.github/workflows/patchbot-fix-example.yml).

A pull request opened by `patchbot fix --pr`:

<img src="docs/img/fix-pr.jpg" alt="A pull request opened by patchbot" width="800">

## Scheduled deployments (no CI)

`patchbot managed deploy` creates a cron-scheduled Managed Agents session that clones a list of repositories, scans, fixes, and opens pull requests on its own. Nothing here is GitHub-Actions-specific, so it works for GitLab and Bitbucket too.

```bash
patchbot managed deploy \
  --repos owner/api,owner/web \
  --cron "0 6 * * *" --tz UTC \
  --agent-id agent_… --environment-id env_… --vault-id vlt_… \
  --run-now                       # fire one session immediately to test
```

Manage it afterward with `patchbot managed list | pause | unpause`. Scheduled runs are jittered by up to nine minutes, and 1–3 AM local wall-clock times can skip or double-fire on DST transitions — schedule outside that window or use UTC when it matters.

## Extending patchbot

Register a scanner, feed, or agent from your own package through entry points — no fork required.

```toml
# your_package/pyproject.toml
[project.entry-points."patchbot.scanners"]
mytool = "your_package.scanner:run"      # run(cwd: str, config: dict) -> list[Finding]

[project.entry-points."patchbot.feeds"]
myfeed = "your_package.feed"             # match(packages, config) -> list[Finding]

[project.entry-points."patchbot.agents"]
myagent = "your_package.agent"           # run(prompt, cwd, model=None, timeout=600, config=None) -> int
```

Without writing Python, `[scanners.*] type = "command"` and `[feeds.*] type = "url" | "file"` cover most cases. `cmd` values run through the shell — point them only at tools you trust.

## FAQ

**Why did a fix report `failed`?** The reason is printed: the advisory still reproduces after the bump or agent run, `test_cmd` failed (with the log tail), or the change touched files outside the dependency surface. The branch is discarded; nothing partial is committed.

**What sets the exit code?** `scan` exits 1 when any finding meets `--fail-on` or worse (`none` always exits 0). `fix` exits 1 if any package could not be fixed.

**How do I suppress one advisory?** `[report] ignore = ["GHSA-…"]`.

**Do I need Node in CI?** Only for `--agent claude` or `codex`. The `api` and `managed` backends need Python alone.

**Which ecosystems get transitive dependencies?** npm, pnpm, and yarn via their lockfiles. For Python, Go, and Rust, feed patchbot a CycloneDX SBOM (`[inventory] sbom = …`) to include the full resolved tree.

## Development

```bash
git clone https://github.com/PrismorSec/patchbot && cd patchbot
python -m venv .venv && .venv/bin/pip install -e ".[dev,yaml,api]"
.venv/bin/pytest
docs/screenshots.sh              # regenerate docs/img (needs charmbracelet/freeze)
```

`examples/demo-npm` is deliberately vulnerable; the repository's own CI scans it so the Security tab always shows live findings.

## License

MIT
