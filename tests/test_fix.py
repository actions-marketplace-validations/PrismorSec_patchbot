import json
import subprocess
import sys
import types

from autopatch.models import Finding, Package
from autopatch import fix


def _git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo)
    lock = repo / "package-lock.json"
    lock.write_text(json.dumps({
        "packages": {"node_modules/lodash": {"version": "4.17.20"}}
    }))
    subprocess.run(["git", "add", "-A"], cwd=repo)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo)
    subprocess.run(["git", "branch", "-M", "main"], cwd=repo)
    return repo


def _finding(version="4.17.20"):
    return Finding(
        id="GHSA-test", package=Package("npm", "lodash", version),
        fixed_versions=["4.17.21"], severity="high",
    )


def test_dry_run_returns_prompt_without_touching_repo(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path)
    results = fix.run([_finding()], str(repo), agent_name="claude", max_prs=5,
                       open_pr=False, dry_run=True)
    assert len(results) == 1
    assert results[0]["status"] == "dry-run"
    assert "lodash" in results[0]["detail"]


def test_successful_fix_commits_on_new_branch(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path)

    def fake_agent_run(prompt, cwd, timeout=600):
        lock = (repo / "package-lock.json")
        lock.write_text(json.dumps({
            "packages": {"node_modules/lodash": {"version": "4.17.21"}}
        }))
        return 0

    fake_module = types.SimpleNamespace(run=fake_agent_run)
    monkeypatch.setattr(fix.agents, "get", lambda name: fake_module)

    results = fix.run([_finding()], str(repo), agent_name="claude", max_prs=5, open_pr=False)
    assert results[0]["status"] == "committed"

    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=repo, capture_output=True, text=True)
    assert "lodash" in log.stdout

    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo,
                             capture_output=True, text=True).stdout.strip()
    assert branch == "autopatch-npm-lodash"


def test_failed_fix_resets_to_base_branch(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path)

    def noop_agent_run(prompt, cwd, timeout=600):
        return 0  # doesn't touch the lockfile -> version stays vulnerable

    fake_module = types.SimpleNamespace(run=noop_agent_run)
    monkeypatch.setattr(fix.agents, "get", lambda name: fake_module)

    results = fix.run([_finding()], str(repo), agent_name="claude", max_prs=5, open_pr=False)
    assert results[0]["status"] == "failed"

    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo,
                             capture_output=True, text=True).stdout.strip()
    assert branch == "main"
