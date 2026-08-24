"""Minimal, dependency-free version comparison for OSV range matching.

Not a full semver/PEP440 implementation: just enough to order the
numeric-dot-separated versions real-world ecosystems publish, which is
what OSV's SEMVER/ECOSYSTEM ranges need. Falls back to string comparison
when a version doesn't parse, so an unusual version never crashes a scan.
"""
from __future__ import annotations

import re

_NUM_RE = re.compile(r"\d+")


def parse_version(v: str) -> tuple:
    """'1.2.3-rc.1' -> (1, 2, 3) for comparison purposes.

    Pre-release/build suffixes are dropped rather than modeled: this is
    a "good enough to order releases" comparator, not a spec-compliant one.
    """
    if not v:
        return ()
    head = re.split(r"[-+]", v, maxsplit=1)[0]
    return tuple(int(n) for n in _NUM_RE.findall(head)) or (0,)


def version_lt(a: str, b: str) -> bool:
    return parse_version(a) < parse_version(b)


def version_gte(a: str, b: str) -> bool:
    return parse_version(a) >= parse_version(b)


def in_range(version: str, affected: dict) -> bool:
    """Does `version` fall inside an OSV `affected[]` entry?

    Checks the explicit `versions` list first (exact matches, cheap and
    unambiguous), then falls back to `ranges[].events` introduced/fixed
    pairs. A range with no "fixed" event is treated as open-ended (still
    affected at every version >= introduced).
    """
    if version in (affected.get("versions") or []):
        return True

    for rng in affected.get("ranges") or []:
        if rng.get("type") not in ("SEMVER", "ECOSYSTEM"):
            continue
        introduced = None
        fixed = None
        for event in rng.get("events") or []:
            if "introduced" in event:
                introduced = event["introduced"]
            elif "fixed" in event:
                fixed = event["fixed"]
        if introduced == "0" or introduced is None:
            lower_ok = True
        else:
            lower_ok = version_gte(version, introduced)
        upper_ok = fixed is None or version_lt(version, fixed)
        if lower_ok and upper_ok:
            return True
    return False


def fixed_versions_for(version: str, affected: dict) -> list:
    """Extract candidate fixed versions >= the vulnerable one from ranges."""
    out = []
    for rng in affected.get("ranges") or []:
        for event in rng.get("events") or []:
            fixed = event.get("fixed")
            if fixed and version_gte(fixed, version):
                out.append(fixed)
    return out
