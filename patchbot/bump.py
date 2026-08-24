"""Tier 0 of the fix loop: a deterministic version bump, no agent involved.

Most vulnerable-package fixes are exactly this: rewrite the pin, regenerate
the lockfile, done. The agent tiers in fix.py only run when this fails
(major bump breaks the build, tests fail, or the package isn't a direct
dependency this module knows how to edit).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _bump_npm(cwd: Path, name: str, version: str) -> bool:
    manifest = cwd / "package.json"
    if not manifest.exists():
        return False
    text = manifest.read_text(encoding="utf-8")
    escaped = re.escape(name)
    pattern = re.compile(rf'("{escaped}"\s*:\s*")[^"]*(")')
    new_text, count = pattern.subn(rf"\g<1>^{version}\g<2>", text)
    if count == 0:
        return False  # not a direct dependency: let the agent tier handle it
    _write(manifest, new_text)

    if shutil.which("npm") and (cwd / "package-lock.json").exists():
        result = subprocess.run(["npm", "install", "--package-lock-only"], cwd=cwd, capture_output=True)
        return result.returncode == 0
    if shutil.which("pnpm") and (cwd / "pnpm-lock.yaml").exists():
        result = subprocess.run(["pnpm", "install", "--lockfile-only"], cwd=cwd, capture_output=True)
        return result.returncode == 0
    if shutil.which("yarn") and (cwd / "yarn.lock").exists():
        result = subprocess.run(["yarn", "install", "--mode", "update-lockfile"], cwd=cwd, capture_output=True)
        return result.returncode == 0
    return False  # no lockfile tool available to regenerate: don't leave it stale


def _bump_pip(cwd: Path, name: str, version: str) -> bool:
    bumped = False
    for manifest in cwd.glob("requirements*.txt"):
        text = manifest.read_text(encoding="utf-8")
        pattern = re.compile(rf'(?im)^({re.escape(name)}\s*==\s*)[\w.\-]+')
        new_text, count = pattern.subn(rf"\g<1>{version}", text)
        if count:
            _write(manifest, new_text)
            bumped = True
    pyproject = cwd / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8")
        pattern = re.compile(rf'(?im)^(\s*["\']{re.escape(name)}\s*==\s*)[\w.\-]+')
        new_text, count = pattern.subn(rf"\g<1>{version}", text)
        if count:
            _write(pyproject, new_text)
            bumped = True
    return bumped  # pip has no standard lockfile to regenerate


def _bump_go(cwd: Path, name: str, version: str) -> bool:
    manifest = cwd / "go.mod"
    if not manifest.exists():
        return False
    text = manifest.read_text(encoding="utf-8")
    pattern = re.compile(rf'(?m)^(\s*{re.escape(name)}\s+)v?[\w.\-+]+')
    new_text, count = pattern.subn(rf"\g<1>v{version}", text)
    if count == 0:
        return False
    _write(manifest, new_text)
    if shutil.which("go"):
        result = subprocess.run(["go", "mod", "tidy"], cwd=cwd, capture_output=True)
        return result.returncode == 0
    return False


def _bump_cargo(cwd: Path, name: str, version: str) -> bool:
    manifest = cwd / "Cargo.toml"
    if not manifest.exists():
        return False
    text = manifest.read_text(encoding="utf-8")
    pattern = re.compile(rf'(?m)^(\s*{re.escape(name)}\s*=\s*)"[^"]*"')
    new_text, count = pattern.subn(rf'\g<1>"{version}"', text)
    if count == 0:
        return False
    _write(manifest, new_text)
    if shutil.which("cargo") and (cwd / "Cargo.lock").exists():
        result = subprocess.run(
            ["cargo", "update", "-p", name, "--precise", version], cwd=cwd, capture_output=True,
        )
        return result.returncode == 0
    return True  # no lockfile yet: the manifest edit alone is the fix


_BUMPERS = {
    "npm": _bump_npm,
    "pip": _bump_pip,
    "go": _bump_go,
    "cargo": _bump_cargo,
}


def try_bump(cwd: str, ecosystem: str, name: str, target_version: str) -> bool:
    """Attempt the deterministic fix. Returns True if the manifest (and
    lockfile, where applicable) were rewritten successfully. False means
    "give up cleanly": the caller escalates to the agent tier."""
    bumper = _BUMPERS.get(ecosystem)
    if bumper is None:
        return False
    return bumper(Path(cwd), name, target_version)
