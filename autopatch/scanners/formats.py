"""Parsers from third-party scanner output formats into Finding lists.

Each parser is deliberately tolerant of missing fields — scanner output
shapes vary across versions, and a partially-populated Finding is better
than a crashed scan.
"""
from __future__ import annotations

import json
from typing import List

from autopatch.models import Finding, Package


def parse_trivy(raw: str) -> List[Finding]:
    data = json.loads(raw)
    findings = []
    for result in data.get("Results") or []:
        for vuln in result.get("Vulnerabilities") or []:
            pkg = Package(
                ecosystem=(result.get("Type") or "unknown"),
                name=vuln.get("PkgName", ""),
                version=vuln.get("InstalledVersion", ""),
                path=result.get("Target", ""),
            )
            fixed = vuln.get("FixedVersion", "")
            findings.append(Finding(
                id=vuln.get("VulnerabilityID", "UNKNOWN"),
                package=pkg,
                fixed_versions=[v.strip() for v in fixed.split(",") if v.strip()],
                severity=(vuln.get("Severity") or "unknown").lower(),
                summary=vuln.get("Title") or vuln.get("Description", "")[:200],
                url=vuln.get("PrimaryURL", ""),
                source="trivy",
            ))
    return findings


def parse_grype(raw: str) -> List[Finding]:
    data = json.loads(raw)
    findings = []
    for match in data.get("matches") or []:
        vuln = match.get("vulnerability") or {}
        artifact = match.get("artifact") or {}
        pkg = Package(
            ecosystem=(artifact.get("type") or "unknown"),
            name=artifact.get("name", ""),
            version=artifact.get("version", ""),
            path=(artifact.get("locations") or [{}])[0].get("path", ""),
        )
        fixed = ((vuln.get("fix") or {}).get("versions")) or []
        findings.append(Finding(
            id=vuln.get("id", "UNKNOWN"),
            package=pkg,
            fixed_versions=list(fixed),
            severity=(vuln.get("severity") or "unknown").lower(),
            summary=vuln.get("description", "")[:200],
            url=(vuln.get("dataSource") or ""),
            source="grype",
        ))
    return findings


def parse_osv_scanner(raw: str) -> List[Finding]:
    data = json.loads(raw)
    findings = []
    for result in data.get("results") or []:
        for pkg_entry in result.get("packages") or []:
            pkg_info = pkg_entry.get("package") or {}
            pkg = Package(
                ecosystem=(pkg_info.get("ecosystem") or "unknown").lower(),
                name=pkg_info.get("name", ""),
                version=pkg_info.get("version", ""),
                path=result.get("source", {}).get("path", ""),
            )
            for vuln in pkg_entry.get("vulnerabilities") or []:
                fixed = []
                for affected in vuln.get("affected") or []:
                    for rng in affected.get("ranges") or []:
                        for event in rng.get("events") or []:
                            if "fixed" in event:
                                fixed.append(event["fixed"])
                findings.append(Finding(
                    id=vuln.get("id", "UNKNOWN"),
                    package=pkg,
                    fixed_versions=sorted(set(fixed)),
                    severity="unknown",
                    summary=vuln.get("summary", ""),
                    url=f"https://osv.dev/vulnerability/{vuln.get('id', '')}",
                    source="osv-scanner",
                ))
    return findings


def parse_sarif(raw: str) -> List[Finding]:
    """Generic SARIF: no package/version info, so Findings carry a placeholder
    Package built from the rule id and the flagged file location."""
    data = json.loads(raw)
    findings = []
    for run in data.get("runs") or []:
        rules_by_id = {r["id"]: r for r in (run.get("tool", {}).get("driver", {}).get("rules") or [])}
        for result in run.get("results") or []:
            rule = rules_by_id.get(result.get("ruleId", ""), {})
            location = (result.get("locations") or [{}])[0]
            path = (location.get("physicalLocation") or {}).get("artifactLocation", {}).get("uri", "")
            level = result.get("level", "warning")
            severity = {"error": "high", "warning": "medium", "note": "low"}.get(level, "unknown")
            findings.append(Finding(
                id=result.get("ruleId", "UNKNOWN"),
                package=Package(ecosystem="unknown", name=path or result.get("ruleId", ""), version="", path=path),
                severity=severity,
                summary=(result.get("message") or {}).get("text", rule.get("shortDescription", {}).get("text", "")),
                url=rule.get("helpUri", ""),
                source="sarif",
            ))
    return findings


PARSERS = {
    "trivy": parse_trivy,
    "grype": parse_grype,
    "osv-scanner": parse_osv_scanner,
    "sarif": parse_sarif,
}
