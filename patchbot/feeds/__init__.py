from __future__ import annotations

from typing import List

from patchbot.models import Finding, Package, dedupe
from patchbot.registry import load_plugins
from patchbot.feeds import osv, file as file_feed

BUILTIN = {"osv": osv, "file": file_feed, "url": file_feed}


def match_all(packages: List[Package], feeds_config: dict) -> List[Finding]:
    """Run every configured feed and return the deduplicated union of findings."""
    plugins = load_plugins("patchbot.feeds", BUILTIN)
    findings: List[Finding] = []
    for name, cfg in feeds_config.items():
        cfg = dict(cfg or {})
        if not cfg.pop("enabled", True):
            continue
        feed_type = cfg.pop("type", name)
        module = plugins.get(feed_type)
        if module is None:
            raise ValueError(f"unknown feed type: {feed_type!r} (feed {name!r})")
        cfg.setdefault("name", name)
        findings.extend(module.match(packages, cfg))
    return dedupe(findings)
