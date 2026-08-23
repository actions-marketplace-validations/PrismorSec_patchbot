"""Manifest and lockfile parsers.

Ported from prismor's prismor/runtime/deps.py — trimmed to pure functions
that return Package objects instead of dicts, since patchwork has no
policy-feed correlation step of its own.
"""
from __future__ import annotations

import json
import os
import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Dict, Iterator, List

from patchwork.models import Package

_SKIP_DIR_NAMES = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", "bower_components", "vendor",
    ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".tox",
    ".next", ".nuxt", ".cache", ".terraform",
    "dist", "build",
    ".claude", ".codex", ".cursor",
})


def _iter_files(workspace: Path, *patterns: str) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(workspace, followlinks=False):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIR_NAMES)
        for name in sorted(filenames):
            if any(fnmatch(name, pattern) for pattern in patterns):
                yield here / name


_PNPM_KEY_RE = re.compile(r'^/?(?P<name>(?:@[^/@\s]+/)?[^@/\s][^@\s]*)@(?P<version>[0-9][^\s(]*)')
_YARN_V1_VERSION_RE = re.compile(r'^\s+version\s+"?([^"\s]+)"?\s*$')
_YARN_V1_HEADER_RE = re.compile(r'^"?(?P<name>(?:@[^/@\s]+/)?[^@\s"]+)@')


def read_npm_lockfile_full(workspace: Path) -> Dict[str, str]:
    """package-lock.json (v2/v3) -> {name: version}, including transitive deps."""
    pins: Dict[str, str] = {}
    for lock in _iter_files(workspace, "package-lock.json"):
        try:
            data = json.loads(lock.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        packages = data.get("packages") or {}
        if not isinstance(packages, dict):
            continue
        for path, meta in packages.items():
            if not path.startswith("node_modules/") or not isinstance(meta, dict):
                continue
            name = path.rsplit("node_modules/", 1)[-1]
            version = meta.get("version")
            if name and isinstance(version, str):
                pins[name] = version
    return pins


def read_pnpm_lockfile_full(workspace: Path) -> Dict[str, str]:
    """pnpm-lock.yaml -> {name: version}, flattened resolved tree."""
    pins: Dict[str, str] = {}
    try:
        import yaml
    except ImportError:
        return pins
    for lock in _iter_files(workspace, "pnpm-lock.yaml"):
        try:
            data = yaml.safe_load(lock.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        packages = data.get("packages") or {}
        if not isinstance(packages, dict):
            continue
        for key, meta in packages.items():
            match = _PNPM_KEY_RE.match(str(key))
            if not match:
                continue
            version = match.group("version")
            if isinstance(meta, dict) and isinstance(meta.get("version"), str):
                version = meta["version"]
            pins[match.group("name")] = version
    return pins


def read_yarn_lockfile_full(workspace: Path) -> Dict[str, str]:
    """yarn.lock -> {name: version}. Handles classic v1 and Berry (YAML)."""
    pins: Dict[str, str] = {}
    for lock in _iter_files(workspace, "yarn.lock"):
        try:
            text = lock.read_text(encoding="utf-8")
        except OSError:
            continue

        if "__metadata" in text:
            try:
                import yaml
                data = yaml.safe_load(text)
            except Exception:
                data = None
            if isinstance(data, dict):
                for key, meta in data.items():
                    if key == "__metadata" or not isinstance(meta, dict):
                        continue
                    version = meta.get("version")
                    header = _YARN_V1_HEADER_RE.match(str(key).split(",")[0].strip())
                    if header and isinstance(version, str):
                        pins[header.group("name")] = version
                continue

        current = None
        for line in text.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if not line[0].isspace():
                header = _YARN_V1_HEADER_RE.match(line.split(",")[0].strip())
                current = header.group("name") if header else None
                continue
            if current:
                version_match = _YARN_V1_VERSION_RE.match(line)
                if version_match:
                    pins[current] = version_match.group(1)
                    current = None
    return pins


def _parse_requirements_txt(text: str) -> List[Package]:
    deps = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        match = re.match(r'^([A-Za-z0-9_.-]+)\s*==\s*([\d][\w.\-]*)', line)
        if match:
            deps.append(Package("pip", match.group(1), match.group(2), "requirements.txt"))
    return deps


def _parse_pyproject_toml(text: str) -> List[Package]:
    deps = []
    in_deps = False
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r'^dependencies\s*=\s*\[', stripped):
            in_deps = True
            continue
        if in_deps:
            if stripped.startswith("]"):
                in_deps = False
                continue
            match = re.match(r'^["\']([A-Za-z0-9_.-]+)\s*==\s*([\d][\w.\-]*)', stripped)
            if match:
                deps.append(Package("pip", match.group(1), match.group(2), "pyproject.toml"))
    return deps


def _parse_go_mod(text: str) -> List[Package]:
    deps = []
    in_require = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("require ("):
            in_require = True
            continue
        if in_require:
            if stripped == ")":
                in_require = False
                continue
            parts = stripped.split()
            if len(parts) >= 2:
                deps.append(Package("go", parts[0], parts[1].lstrip("v"), "go.mod"))
        elif stripped.startswith("require "):
            parts = stripped.split()
            if len(parts) >= 3:
                deps.append(Package("go", parts[1], parts[2].lstrip("v"), "go.mod"))
    return deps


def _parse_cargo_toml(text: str) -> List[Package]:
    deps = []
    in_deps = False
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r'^\[dependencies\]', stripped, re.IGNORECASE):
            in_deps = True
            continue
        if in_deps:
            if stripped.startswith("["):
                in_deps = False
                continue
            if not stripped or stripped.startswith("#"):
                continue
            match = re.match(r'^([A-Za-z0-9_-]+)\s*=\s*"([^"]*)"', stripped)
            if not match:
                match = re.match(r'^([A-Za-z0-9_-]+)\s*=\s*\{.*version\s*=\s*"([^"]*)"', stripped)
            if match:
                deps.append(Package("cargo", match.group(1), match.group(2), "Cargo.toml"))
    return deps


def collect(workspace: Path) -> List[Package]:
    """Walk `workspace` and return every Package we can pin an exact version for.

    JS ecosystems resolve through lockfiles (npm/pnpm/yarn all merge into
    one flat name->version map, unioned since they're all the "npm" OSV
    ecosystem). Other ecosystems are read straight off the manifest since
    patchwork doesn't parse poetry.lock/Cargo.lock/go.sum — see README for
    the CycloneDX SBOM path if you need transitive deps there.
    """
    packages: List[Package] = []

    js_pins: Dict[str, str] = {}
    js_pins.update(read_npm_lockfile_full(workspace))
    js_pins.update(read_pnpm_lockfile_full(workspace))
    js_pins.update(read_yarn_lockfile_full(workspace))
    for name, version in js_pins.items():
        packages.append(Package("npm", name, version, "lockfile"))

    for manifest in _iter_files(workspace, "requirements.txt", "requirements-*.txt"):
        packages.extend(_parse_requirements_txt(manifest.read_text(encoding="utf-8", errors="ignore")))
    for manifest in _iter_files(workspace, "pyproject.toml"):
        packages.extend(_parse_pyproject_toml(manifest.read_text(encoding="utf-8", errors="ignore")))
    for manifest in _iter_files(workspace, "go.mod"):
        packages.extend(_parse_go_mod(manifest.read_text(encoding="utf-8", errors="ignore")))
    for manifest in _iter_files(workspace, "Cargo.toml"):
        packages.extend(_parse_cargo_toml(manifest.read_text(encoding="utf-8", errors="ignore")))

    return packages
