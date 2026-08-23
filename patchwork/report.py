"""Report writers and CI exit-code policy."""
from __future__ import annotations

import json
from typing import List

from patchwork.models import Finding, SEVERITY_ORDER, severity_rank, sort_findings

TOOL_NAME = "patchwork"
TOOL_URI = "https://github.com/ar9av/patchwork"


def to_table(findings: List[Finding]) -> str:
    if not findings:
        return "No vulnerabilities found.\n"
    rows = [("SEVERITY", "PACKAGE", "VERSION", "ID", "FIXED IN", "SOURCE")]
    for f in sort_findings(findings):
        rows.append((
            f.severity.upper(),
            f"{f.package.ecosystem}:{f.package.name}",
            f.package.version,
            f.id,
            ", ".join(f.fixed_versions) or "-",
            f.source,
        ))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    lines = []
    for row in rows:
        lines.append("  ".join(cell.ljust(w) for cell, w in zip(row, widths)))
    lines.append(f"\n{len(findings)} finding(s).")
    return "\n".join(lines) + "\n"


def to_json(findings: List[Finding]) -> str:
    return json.dumps([
        {
            "id": f.id,
            "package": {"ecosystem": f.package.ecosystem, "name": f.package.name,
                        "version": f.package.version, "path": f.package.path},
            "fixed_versions": f.fixed_versions,
            "severity": f.severity,
            "summary": f.summary,
            "url": f.url,
            "source": f.source,
        }
        for f in sort_findings(findings)
    ], indent=2)


_SARIF_LEVEL = {"critical": "error", "high": "error", "medium": "warning", "low": "note", "unknown": "note"}


def to_sarif(findings: List[Finding]) -> str:
    rule_index = {}
    rules = []
    results = []
    for f in sort_findings(findings):
        if f.id not in rule_index:
            rule_index[f.id] = len(rules)
            rules.append({
                "id": f.id,
                "shortDescription": {"text": f.summary or f.id},
                "helpUri": f.url,
                "defaultConfiguration": {"level": _SARIF_LEVEL.get(f.severity, "note")},
                "properties": {"severity": f.severity},
            })
        results.append({
            "ruleId": f.id,
            "ruleIndex": rule_index[f.id],
            "level": _SARIF_LEVEL.get(f.severity, "note"),
            "message": {"text": f"{f.package.name}@{f.package.version}: {f.summary or f.id} "
                                 f"(fixed in {', '.join(f.fixed_versions) or 'unknown'})"},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": f.package.path or f.package.name},
                }
            }],
        })
    sarif = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": TOOL_NAME, "informationUri": TOOL_URI, "rules": rules}},
            "results": results,
        }],
    }
    return json.dumps(sarif, indent=2)


FORMATS = {"table": to_table, "json": to_json, "sarif": to_sarif}


def exit_code(findings: List[Finding], fail_on: str) -> int:
    """0 if nothing meets `fail_on` severity or worse; 1 otherwise."""
    if fail_on == "none":
        return 0
    threshold = severity_rank(fail_on)
    return 1 if any(severity_rank(f.severity) <= threshold for f in findings) else 0
