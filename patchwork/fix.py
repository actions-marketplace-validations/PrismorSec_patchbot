"""Agent-driven fix loop: one branch + one PR per vulnerable package.

Sequential by design (`--max` caps how many packages get a PR per run) —
concurrent agents editing the same working tree would race on git state.
"""
from __future__ import annotations

import subprocess
from collections import defaultdict
from pathlib import Path
from typing import List, Optional

from patchwork import agents, inventory
from patchwork.models import Finding
from patchwork.versions import version_gte


def _git(args: List[str], cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def _current_branch(cwd: str) -> str:
    return _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd).stdout.strip()


def group_by_package(findings: List[Finding]):
    groups = defaultdict(list)
    for f in findings:
        groups[(f.package.ecosystem, f.package.name)].append(f)
    return groups


def build_prompt(ecosystem: str, name: str, group: List[Finding]) -> str:
    lines = [
        f"Fix the following security advisories affecting {ecosystem} package "
        f"'{name}' (currently {group[0].package.version}) in this repository.",
        "",
    ]
    for f in group:
        fixed = ", ".join(f.fixed_versions) or "a patched release"
        lines.append(f"- {f.id} ({f.severity}): {f.summary or 'see ' + f.url}. Fixed in: {fixed}.")
    lines += [
        "",
        "Bump the package to the lowest version that resolves all of the above "
        "in every manifest and lockfile that references it, then update the "
        "lockfile using the project's package manager so it stays in sync. "
        "Do not modify unrelated files or unrelated dependencies.",
    ]
    return "\n".join(lines)


def _rescan_version(cwd: str, ecosystem: str, name: str) -> Optional[str]:
    for pkg in inventory.collect([cwd]):
        if pkg.ecosystem == ecosystem and pkg.name == name:
            return pkg.version
    return None


def run(
    findings: List[Finding],
    cwd: str,
    agent_name: str,
    max_prs: int,
    open_pr: bool,
    test_cmd: Optional[str] = None,
    dry_run: bool = False,
) -> List[dict]:
    """Fix up to `max_prs` vulnerable packages. Returns a report list of
    {package, branch, status, detail} dicts, one per attempted package."""
    agent = agents.get(agent_name)
    base_branch = _current_branch(cwd)
    groups = group_by_package(findings)
    results = []

    for (ecosystem, name), group in list(groups.items())[:max_prs]:
        prompt = build_prompt(ecosystem, name, group)

        if dry_run:
            results.append({"package": f"{ecosystem}:{name}", "status": "dry-run", "detail": prompt})
            continue

        branch = f"patchwork/{ecosystem}-{name}".replace("/", "-")
        _git(["switch", "-c", branch], cwd)

        agent.run(prompt, cwd)

        new_version = _rescan_version(cwd, ecosystem, name)
        fixed_versions = {v for f in group for v in f.fixed_versions}
        if fixed_versions:
            fixed_ok = bool(new_version) and any(version_gte(new_version, v) for v in fixed_versions)
        else:
            fixed_ok = bool(new_version) and new_version != group[0].package.version

        test_ok = True
        if fixed_ok and test_cmd:
            test_ok = subprocess.run(test_cmd, shell=True, cwd=cwd).returncode == 0

        if fixed_ok and test_ok:
            _git(["add", "-A"], cwd)
            _git(["commit", "-m", f"fix({ecosystem}): patch {name} ({', '.join(f.id for f in group)})"], cwd)
            status = "unpatched"
            if open_pr:
                _git(["push", "-u", "origin", branch], cwd)
                pr = subprocess.run(
                    ["gh", "pr", "create", "--title", f"fix({ecosystem}): patch {name}",
                     "--body", prompt, "--head", branch, "--base", base_branch],
                    cwd=cwd, capture_output=True, text=True,
                )
                status = "pr-opened" if pr.returncode == 0 else "commit-only"
            else:
                status = "committed"
            results.append({"package": f"{ecosystem}:{name}", "status": status, "detail": branch})
        else:
            _git(["reset", "--hard"], cwd)
            _git(["switch", base_branch], cwd)
            _git(["branch", "-D", branch], cwd)
            reason = "tests failed" if fixed_ok else "advisory still reproduces after agent run"
            results.append({"package": f"{ecosystem}:{name}", "status": "failed", "detail": reason})

    return results
