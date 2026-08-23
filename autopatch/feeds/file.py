"""Bring-your-own threat feed: an OSV-schema JSON file or URL.

Accepts either a bare list of OSV vuln records or `{"vulns": [...]}`
(OSV's own bulk export shape), so a user's private feed needs no custom
parser — just OSV-format JSON.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import List

from autopatch.models import Finding, Package
from autopatch.versions import fixed_versions_for, in_range
from autopatch.feeds.osv import classify_severity, summary_of, url_for, _ECOSYSTEM_MAP


def _load(source: str) -> list:
    if source.startswith("http://") or source.startswith("https://"):
        with urllib.request.urlopen(source, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    else:
        data = json.loads(Path(source).read_text(encoding="utf-8"))
    return data.get("vulns", data) if isinstance(data, dict) else data


def match(packages: List[Package], config: dict) -> List[Finding]:
    source = config.get("url") or config.get("path")
    if not source:
        return []
    vulns = _load(source)

    findings: List[Finding] = []
    for pkg in packages:
        osv_eco = _ECOSYSTEM_MAP.get(pkg.ecosystem)
        if not osv_eco:
            continue
        for vuln in vulns:
            for affected in vuln.get("affected") or []:
                if affected.get("package", {}).get("ecosystem") != osv_eco:
                    continue
                if affected.get("package", {}).get("name") != pkg.name:
                    continue
                if not in_range(pkg.version, affected):
                    continue
                findings.append(Finding(
                    id=vuln.get("id", "UNKNOWN"),
                    package=pkg,
                    fixed_versions=sorted(set(fixed_versions_for(pkg.version, affected))),
                    severity=classify_severity(vuln),
                    summary=summary_of(vuln),
                    url=url_for(vuln),
                    source=config.get("name", "file"),
                ))
    return findings
