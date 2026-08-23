"""CycloneDX SBOM -> Package list.

Lets any tool that can emit an SBOM (syft, cdxgen, a vendor scanner) feed
autopatch's inventory, covering ecosystems autopatch has no native lockfile
parser for.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List

from autopatch.models import Package

# purl type -> OSV/autopatch ecosystem name.
_PURL_ECOSYSTEM = {
    "npm": "npm",
    "pypi": "pip",
    "cargo": "cargo",
    "golang": "go",
    "gem": "gem",
    "maven": "maven",
}

_PURL_RE = re.compile(r"^pkg:(?P<type>[^/]+)/(?P<rest>.+)$")


def _from_purl(purl: str):
    match = _PURL_RE.match(purl)
    if not match:
        return None
    eco = _PURL_ECOSYSTEM.get(match.group("type").lower())
    if not eco:
        return None
    rest = match.group("rest").split("?", 1)[0]
    if "@" not in rest:
        return None
    name, version = rest.rsplit("@", 1)
    name = name.split("/", 1)[-1] if match.group("type").lower() != "npm" else name
    return eco, name, version


def collect(sbom_path: Path) -> List[Package]:
    data = json.loads(sbom_path.read_text(encoding="utf-8"))
    packages: List[Package] = []
    for component in data.get("components") or []:
        purl = component.get("purl")
        if not purl:
            continue
        parsed = _from_purl(purl)
        if not parsed:
            continue
        eco, name, version = parsed
        packages.append(Package(eco, name, version, str(sbom_path)))
    return packages
