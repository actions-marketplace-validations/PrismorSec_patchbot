from __future__ import annotations

from typing import List

from patchwork.models import Finding, dedupe
from patchwork.registry import load_plugins
from patchwork.scanners import builtin

BUILTIN = {
    "trivy": builtin.trivy,
    "grype": builtin.grype,
    "osv-scanner": builtin.osv_scanner,
    "command": builtin.command,
}


def run_all(cwd: str, scanners_config: dict) -> List[Finding]:
    plugins = load_plugins("patchwork.scanners", BUILTIN)
    findings: List[Finding] = []
    for name, cfg in scanners_config.items():
        cfg = dict(cfg or {})
        if not cfg.pop("enabled", True):
            continue
        scanner_type = cfg.pop("type", name)
        fn = plugins.get(scanner_type)
        if fn is None:
            raise ValueError(f"unknown scanner type: {scanner_type!r} (scanner {name!r})")
        findings.extend(fn(cwd, cfg))
    return dedupe(findings)
