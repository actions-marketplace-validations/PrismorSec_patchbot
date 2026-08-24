"""Tiered fix loop: one branch + one PR per vulnerable package.

Tier 0 (patchbot.bump) tries a deterministic version bump + lockfile
regen first — no agent involved, mirrors what Dependabot already does well.
Only when that fails to clear the advisory (or fails a configured
test_cmd) does the configured agent get a turn, with the failure itself as
its brief rather than the original vague "go fix this" task.

Sequential by design (`--max` caps how many packages get a PR per run) —
concurrent agents editing the same working tree would race on git state.
"""
from __future__ import annotations

import subprocess
from collections import defaultdict
from pathlib import Path
from typing import List, Optional

from patchbot import agents, bump, inventory
from patchbot.models import Finding
from patchbot.versions import version_gte

# Files an agent is allowed to have touched. Anything outside this stays
# clean — a CI-hosted agent has a shell, and a diff that reaches outside
# the dependency surface (CI config, dotfiles, .git internals) is rejected
# rather than shipped in a PR.
_DISALLOWED_PREFIXES = (".github/", ".git/", ".gitlab-ci", ".circleci/")


def _git(args: List[str], cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def _current_branch(cwd: str) -> str:
    return _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd).stdout.strip()


def group_by_package(findings: List[Finding]):
    groups = defaultdict(list)
    for f in findings:
        groups[(f.package.ecosystem, f.package.name)].append(f)
    return groups


def pick_target_version(group: List[Finding]) -> Optional[str]:
    """The lowest version that resolves every advisory in the group: for
    each finding take its lowest offered fix, then the highest of those
    across findings (a version has to clear every advisory at once)."""
    per_finding_min = []
    for f in group:
        if not f.fixed_versions:
            continue
        lowest = f.fixed_versions[0]
        for v in f.fixed_versions[1:]:
            if not version_gte(lowest, v):
                lowest = v
        per_finding_min.append(lowest)
    if not per_finding_min:
        return None
    target = per_finding_min[0]
    for v in per_finding_min[1:]:
        if version_gte(v, target):
            target = v
    return target


def build_bump_prompt(ecosystem: str, name: str, group: List[Finding], target_version: Optional[str]) -> str:
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
        f"Bump the package to {target_version or 'the lowest version that resolves all of the above'} "
        "in every manifest and lockfile that references it, then update the "
        "lockfile using the project's package manager so it stays in sync. "
        "Do not modify unrelated files or unrelated dependencies.",
    ]
    return "\n".join(lines)


def build_escalation_prompt(ecosystem: str, name: str, target_version: Optional[str], failure_detail: str) -> str:
    return (
        f"A deterministic bump of the {ecosystem} package '{name}' to "
        f"{target_version or 'a patched version'} did not fully fix things. Detail:\n\n"
        f"{failure_detail}\n\n"
        "Fix the code so the tests pass and the advisory no longer reproduces. "
        f"Do not downgrade '{name}' below {target_version or 'the version already applied'}. "
        "Do not modify unrelated files or unrelated dependencies."
    )


def _rescan_version(cwd: str, ecosystem: str, name: str) -> Optional[str]:
    for pkg in inventory.collect([cwd]):
        if pkg.ecosystem == ecosystem and pkg.name == name:
            return pkg.version
    return None


def _diff_allowed(cwd: str) -> bool:
    changed = _git(["diff", "--name-only", "HEAD"], cwd).stdout.splitlines()
    changed += _git(["ls-files", "--others", "--exclude-standard"], cwd).stdout.splitlines()
    return not any(path.startswith(_DISALLOWED_PREFIXES) for path in changed)


def _verify(cwd: str, ecosystem: str, name: str, target_version: Optional[str],
            original_version: str, test_cmd: Optional[str]) -> tuple:
    """Returns (ok, detail) — detail is empty on success, or a failure
    summary suitable for handing to the next tier as its prompt."""
    new_version = _rescan_version(cwd, ecosystem, name)
    if target_version:
        fixed = bool(new_version) and version_gte(new_version, target_version)
    else:
        fixed = bool(new_version) and new_version != original_version
    if not fixed:
        return False, f"advisory still reproduces after the bump (installed version: {new_version or 'unknown'})"

    if not _diff_allowed(cwd):
        return False, "the change touched files outside manifests/lockfiles/source (CI config or dotfiles)"

    if test_cmd:
        result = subprocess.run(test_cmd, shell=True, cwd=cwd)
        if result.returncode != 0:
            tail = "\n".join((result.stdout or "").splitlines()[-80:]) if result.stdout else ""
            return False, f"test_cmd failed (exit {result.returncode}):\n{tail}"

    return True, ""


def run(
    findings: List[Finding],
    cwd: str,
    agent_name: str,
    max_prs: int,
    open_pr: bool,
    test_cmd: Optional[str] = None,
    dry_run: bool = False,
    model: Optional[str] = None,
    agent_config: Optional[dict] = None,
) -> List[dict]:
    """Fix up to `max_prs` vulnerable packages. Returns a report list of
    {package, status, detail} dicts, one per attempted package."""
    base_branch = _current_branch(cwd)
    groups = group_by_package(findings)
    results = []
    agent = None if agent_name == "none" else agents.get(agent_name)

    for (ecosystem, name), group in list(groups.items())[:max_prs]:
        target_version = pick_target_version(group)
        original_version = group[0].package.version
        bump_prompt = build_bump_prompt(ecosystem, name, group, target_version)

        if dry_run:
            results.append({"package": f"{ecosystem}:{name}", "status": "dry-run", "detail": bump_prompt})
            continue

        branch = f"patchbot/{ecosystem}-{name}".replace("/", "-")
        _git(["switch", "-c", branch], cwd)

        # Tier 0: deterministic bump, no agent.
        tier = "bump"
        bumped = bool(target_version) and bump.try_bump(cwd, ecosystem, name, target_version)
        ok, detail = (False, "no deterministic bumper for this ecosystem, or not a direct dependency")
        if bumped:
            ok, detail = _verify(cwd, ecosystem, name, target_version, original_version, test_cmd)

        # Tier 1: agent escalation, only on tier-0 failure.
        if not ok and agent is not None:
            tier = "agent"
            prompt = (
                build_escalation_prompt(ecosystem, name, target_version, detail)
                if bumped else bump_prompt
            )
            if agent_name == "managed":
                # The session edits a remote clone, not `cwd` — push what we
                # have so far so it exists to check out, then pull its result
                # back before verifying locally.
                _git(["add", "-A"], cwd)
                _git(["commit", "--allow-empty", "-m", "wip: patchbot handoff"], cwd)
                _git(["push", "-u", "origin", branch], cwd)
                prompt += (
                    f"\n\nWork on the '{branch}' branch (already checked out). "
                    "Commit and push your fix to that same branch when done."
                )
                agent.run(prompt, cwd, model=model,
                          config={**(agent_config or {}), "branch": branch})
                _git(["fetch", "origin", branch], cwd)
                _git(["reset", "--hard", f"origin/{branch}"], cwd)
            else:
                agent.run(prompt, cwd, model=model, config=agent_config)
            ok, detail = _verify(cwd, ecosystem, name, target_version, original_version, test_cmd)

        if ok:
            _git(["add", "-A"], cwd)
            _git(["commit", "-m", f"fix({ecosystem}): patch {name} ({', '.join(f.id for f in group)})"], cwd)
            status = "committed"
            if open_pr:
                _git(["push", "-u", "origin", branch], cwd)
                pr = subprocess.run(
                    ["gh", "pr", "create", "--title", f"fix({ecosystem}): patch {name}",
                     "--body", f"{bump_prompt}\n\n_Fixed by: {tier} tier._",
                     "--head", branch, "--base", base_branch],
                    cwd=cwd, capture_output=True, text=True,
                )
                status = "pr-opened" if pr.returncode == 0 else "commit-only"
            results.append({"package": f"{ecosystem}:{name}", "status": status, "detail": f"{branch} ({tier})"})
        else:
            _git(["reset", "--hard"], cwd)
            _git(["switch", base_branch], cwd)
            _git(["branch", "-D", branch], cwd)
            results.append({"package": f"{ecosystem}:{name}", "status": "failed", "detail": detail})

    return results
