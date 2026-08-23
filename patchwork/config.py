"""patchwork.toml loader. CLI flags always win over file config."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Config:
    paths: List[str] = field(default_factory=lambda: ["."])
    sbom: Optional[str] = None
    feeds: Dict[str, dict] = field(default_factory=lambda: {"osv": {"enabled": True}})
    scanners: Dict[str, dict] = field(default_factory=dict)
    fail_on: str = "high"
    ignore: List[str] = field(default_factory=list)
    agent: str = "claude"
    max_prs: int = 5
    test_cmd: Optional[str] = None

    @classmethod
    def load(cls, path: Optional[str]) -> "Config":
        cfg = cls()
        toml_path = Path(path) if path else Path("patchwork.toml")
        if not toml_path.exists():
            return cfg
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        inventory = data.get("inventory", {})
        if "paths" in inventory:
            cfg.paths = inventory["paths"]
        if "sbom" in inventory:
            cfg.sbom = inventory["sbom"]
        if "feeds" in data:
            cfg.feeds = data["feeds"]
        if "scanners" in data:
            cfg.scanners = data["scanners"]
        report = data.get("report", {})
        cfg.fail_on = report.get("fail_on", cfg.fail_on)
        cfg.ignore = report.get("ignore", cfg.ignore)
        fix = data.get("fix", {})
        cfg.agent = fix.get("agent", cfg.agent)
        cfg.max_prs = fix.get("max_prs", cfg.max_prs)
        cfg.test_cmd = fix.get("test_cmd", cfg.test_cmd)
        return cfg
