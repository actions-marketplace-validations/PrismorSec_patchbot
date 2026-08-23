"""OSV.dev feed — the default, always-on threat feed.

Batch-query adapted from prismor's supplychain/scoring/osv_lookup.py:
querybatch returns id+modified only, so full details (severity, summary,
fixed versions) are fetched once per distinct vuln ID rather than once
per package. Fails open: network errors yield no findings, never a crash.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List

from patchwork.models import Finding, Package
from patchwork.versions import fixed_versions_for

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_VULN_URL_TEMPLATE = "https://api.osv.dev/v1/vulns/{id}"
_DETAIL_FETCH_CAP = 200

_ECOSYSTEM_MAP = {
    "npm": "npm", "pnpm": "npm", "yarn": "npm", "bun": "npm",
    "pip": "PyPI", "uv": "PyPI",
    "cargo": "crates.io",
    "go": "Go",
    "gem": "RubyGems",
    "maven": "Maven",
}


def _post_json(url: str, body: Dict[str, Any], timeout: int = 10):
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     "User-Agent": "patchwork/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _get_json(url: str, timeout: int = 5):
    try:
        req = urllib.request.Request(
            url, headers={"Accept": "application/json", "User-Agent": "patchwork/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def classify_severity(vuln: Dict[str, Any]) -> str:
    if vuln.get("id", "").startswith("MAL-"):
        return "critical"
    db = vuln.get("database_specific") or {}
    text = str(db.get("severity") or "").lower()
    if text in ("critical", "high", "medium", "low"):
        return text
    for sev in vuln.get("severity") or []:
        vector = str(sev.get("score") or "")
        if "CVSS" not in vector:
            continue
        n_high_impact = vector.count(":H")
        network = "AV:N" in vector
        if network and n_high_impact >= 3:
            return "critical"
        if network and n_high_impact >= 1:
            return "high"
        if n_high_impact >= 1:
            return "medium"
        return "low"
    return "medium"


def summary_of(vuln: Dict[str, Any]) -> str:
    summary = (vuln.get("summary") or "").strip()
    if not summary:
        details = (vuln.get("details") or "").strip().splitlines()
        summary = details[0] if details else ""
    return summary


def url_for(vuln: Dict[str, Any]) -> str:
    for ref in vuln.get("references") or []:
        if ref.get("type") == "ADVISORY":
            return ref.get("url", "")
    return f"https://osv.dev/vulnerability/{vuln.get('id', '')}"


def match(packages: List[Package], config: dict) -> List[Finding]:
    """Query OSV for every package and return Findings with fixed_versions."""
    by_key = {}  # (name, patchwork_ecosystem, version) -> Package
    to_query = []  # (name, patchwork_ecosystem, version, osv_ecosystem)
    for pkg in packages:
        osv_eco = _ECOSYSTEM_MAP.get(pkg.ecosystem)
        if not osv_eco:
            continue
        key = (pkg.name, pkg.ecosystem, pkg.version)
        by_key[key] = pkg
        to_query.append((*key, osv_eco))

    if not to_query:
        return []

    id_map: Dict[tuple, List[str]] = {}
    all_ids: set = set()
    chunk_size = 100
    for start in range(0, len(to_query), chunk_size):
        chunk = to_query[start:start + chunk_size]
        body = {"queries": [{"package": {"name": n, "ecosystem": e}, "version": v} for n, _eco, v, e in chunk]}
        data = _post_json(OSV_BATCH_URL, body)
        results = (data or {}).get("results") or []
        for (n, eco, v, _e), result in zip(chunk, results):
            ids = [vv["id"] for vv in (result or {}).get("vulns") or [] if vv.get("id")]
            id_map[(n, eco, v)] = ids
            all_ids.update(ids)
        if not data:
            for (n, eco, v, _e) in chunk:
                id_map.setdefault((n, eco, v), [])

    detail_cache: Dict[str, Any] = {}
    for vid in sorted(all_ids)[:_DETAIL_FETCH_CAP]:
        detail_cache[vid] = _get_json(OSV_VULN_URL_TEMPLATE.format(id=vid))

    findings: List[Finding] = []
    for key, ids in id_map.items():
        pkg = by_key[key]
        _name, _eco, version = key
        for vid in ids:
            vuln = detail_cache.get(vid)
            if not vuln or vuln.get("withdrawn"):
                continue
            fixed = []
            for affected in vuln.get("affected") or []:
                fixed.extend(fixed_versions_for(version, affected))
            findings.append(Finding(
                id=vid,
                package=pkg,
                fixed_versions=sorted(set(fixed)),
                severity=classify_severity(vuln),
                summary=summary_of(vuln),
                url=url_for(vuln),
                source="osv",
            ))
    return findings
