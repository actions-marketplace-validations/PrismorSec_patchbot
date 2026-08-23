# patchbot

Bring-your-own-scanner, bring-your-own-feed vulnerability scanning, with
Claude Code / Codex opening the fix PR.

```
inventory ──► feeds (match pkg@ver) ──┐
                                      ├──► findings ──► report (table/json/sarif)
scanners (trivy/grype/osv-scanner/sarif/any cmd) ──┘        └──► fix (agent → branch → PR)
```

- **Inventory**: built-in npm/pnpm/yarn/pip/go/cargo manifest+lockfile parsers, plus any CycloneDX SBOM (`syft`, `cdxgen`, or your own).
- **Feeds**: OSV.dev by default. Bring your own threat feed as an OSV-schema JSON file or URL — no custom format to write.
- **Scanners**: bring your own scanner. Built-in wrappers for `trivy`, `grype`, `osv-scanner`, or point `command` at any tool that emits trivy/grype/osv-scanner/SARIF JSON.
- **Fix**: `claude` or `codex` CLI bumps the vulnerable package, re-scans to confirm the advisory is gone, and opens a PR per package.

## Install

```
pip install -e .
```

(Not yet published to PyPI — install from a local clone or a git URL for now.)

## Quickstart

```
patchbot scan                          # table report, uses OSV by default
patchbot scan --format sarif -o out.sarif
patchbot fix --agent claude --dry-run  # print the fix prompt, make no changes
patchbot fix --agent claude --pr       # open PRs for real (needs `claude` + `gh` on PATH)
```

## Config (`patchbot.toml`)

```toml
[inventory]
paths = ["."]
# sbom = "sbom.cdx.json"

[feeds.osv]
enabled = true

[feeds.internal]
type = "url"          # or "file" with `path = "..."`
url = "https://intel.example.com/osv-feed.json"

[scanners.trivy]
enabled = true

[scanners.mine]
type = "command"
cmd = "./scan.sh"
format = "sarif"       # or trivy | grype | osv-scanner

[report]
fail_on = "high"        # critical | high | medium | low | none
ignore = ["GHSA-xxxx-xxxx-xxxx"]

[fix]
agent = "claude"        # or "codex"
max_prs = 5
test_cmd = "npm test"
```

CLI flags override the config file.

## Bring your own scanner

Any command that emits trivy, grype, osv-scanner, or SARIF JSON on stdout works:

```toml
[scanners.custom]
type = "command"
cmd = "my-scanner --json"
format = "sarif"
```

`cmd` runs via the shell using your config, so only point it at commands you trust.

## Bring your own threat feed

Any URL or file serving OSV schema JSON (a bare array of vuln records, or
`{"vulns": [...]}`):

```toml
[feeds.mine]
type = "file"
path = "./our-advisories.json"
```

## Writing a plugin

Register a scanner, feed, or agent from your own pip package via entry points —
no fork of patchbot required:

```toml
# your_package/pyproject.toml
[project.entry-points."patchbot.scanners"]
mytool = "your_package.scanner:run"          # def run(cwd: str, config: dict) -> list[Finding]

[project.entry-points."patchbot.feeds"]
myfeed = "your_package.feed"                 # module with match(packages, config) -> list[Finding]

[project.entry-points."patchbot.agents"]
myagent = "your_package.agent"               # module with run(prompt: str, cwd: str) -> int
```

`patchbot plugins` lists everything currently registered.

## GitHub Actions

```yaml
- uses: ./  # or a published action ref once this is published
  with:
    fail-on: high
    fix: false
```

See [`action.yml`](./action.yml) for all inputs, including `fix: true` to open
auto-fix PRs (requires `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`, and
`permissions: { contents: write, pull-requests: write }`).
