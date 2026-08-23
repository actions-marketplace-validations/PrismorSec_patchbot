from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from patchbot.models import Package
from patchbot.inventory import lockfiles, cyclonedx


def collect(paths: List[str], sbom: Optional[str] = None) -> List[Package]:
    packages: List[Package] = []
    for p in paths:
        packages.extend(lockfiles.collect(Path(p)))
    if sbom:
        packages.extend(cyclonedx.collect(Path(sbom)))
    # de-dupe identical (ecosystem, name, version) across multiple paths/sbom.
    seen = set()
    unique = []
    for pkg in packages:
        key = (pkg.ecosystem, pkg.name, pkg.version)
        if key in seen:
            continue
        seen.add(key)
        unique.append(pkg)
    return unique
