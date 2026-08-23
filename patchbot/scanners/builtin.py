"""Built-in scanner wrappers: shell out to a CLI, parse its JSON output.

Each expects its tool to already be installed (trivy, grype, osv-scanner) —
patchbot doesn't manage tool installs; the GitHub Action or the user's own
environment does. `command` is the generic BYO-scanner escape hatch: run
any command and parse its stdout with one of the known formats.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import List

from patchbot.models import Finding
from patchbot.scanners import formats


def _run(cmd: List[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return result.stdout


def trivy(cwd: str, config: dict) -> List[Finding]:
    if shutil.which("trivy") is None:
        return []
    out = _run(["trivy", "fs", "--format", "json", "--scanners", "vuln", "--quiet", cwd])
    return formats.parse_trivy(out) if out.strip() else []


def grype(cwd: str, config: dict) -> List[Finding]:
    if shutil.which("grype") is None:
        return []
    out = _run(["grype", cwd, "-o", "json"])
    return formats.parse_grype(out) if out.strip() else []


def osv_scanner(cwd: str, config: dict) -> List[Finding]:
    if shutil.which("osv-scanner") is None:
        return []
    result = subprocess.run(
        ["osv-scanner", "--format", "json", "-r", cwd],
        capture_output=True, text=True, timeout=300,
    )
    # osv-scanner exits non-zero when it finds vulns; stdout is still valid JSON.
    return formats.parse_osv_scanner(result.stdout) if result.stdout.strip() else []


def command(cwd: str, config: dict) -> List[Finding]:
    cmd = config.get("cmd")
    fmt = config.get("format", "sarif")
    if not cmd:
        raise ValueError("scanner type 'command' requires a 'cmd'")
    parser = formats.PARSERS.get(fmt)
    if parser is None:
        raise ValueError(f"unknown scanner output format: {fmt!r}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=600)
    return parser(result.stdout) if result.stdout.strip() else []
