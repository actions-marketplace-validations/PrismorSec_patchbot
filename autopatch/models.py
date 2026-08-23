"""Core data types shared by every plugin seam."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

SEVERITY_ORDER = ["critical", "high", "medium", "low", "unknown"]


@dataclass(frozen=True)
class Package:
    ecosystem: str  # npm, pip, cargo, go, gem, maven
    name: str
    version: str
    path: str = ""  # manifest/lockfile this came from, for reporting


@dataclass
class Finding:
    id: str  # advisory id, e.g. GHSA-xxxx or CVE-xxxx
    package: Package
    fixed_versions: list = field(default_factory=list)
    severity: str = "unknown"
    summary: str = ""
    url: str = ""
    source: str = ""  # which feed/scanner produced this

    @property
    def dedupe_key(self):
        return (self.package.ecosystem, self.package.name, self.package.version, self.id)


def dedupe(findings: list) -> list:
    seen = {}
    for f in findings:
        existing = seen.get(f.dedupe_key)
        if existing is None:
            seen[f.dedupe_key] = f
        else:
            # keep the one with more info (fixed_versions, url)
            if not existing.fixed_versions and f.fixed_versions:
                seen[f.dedupe_key] = f
    return list(seen.values())


def severity_rank(sev: str) -> int:
    sev = (sev or "unknown").lower()
    return SEVERITY_ORDER.index(sev) if sev in SEVERITY_ORDER else len(SEVERITY_ORDER)


def sort_findings(findings: list) -> list:
    return sorted(findings, key=lambda f: (severity_rank(f.severity), f.package.name, f.id))
