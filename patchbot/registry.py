"""Plugin registry: builtin modules + third-party entry points.

`pip install`-able extension point, mirroring the pattern prismor uses for
its transcript adapters: a dict of builtins, merged with anything a
third-party package registers under the matching entry-point group in its
own pyproject.toml, e.g.:

    [project.entry-points."patchbot.scanners"]
    mytool = "patchbot_mytool:scanner_module"
"""
from __future__ import annotations

from importlib.metadata import entry_points
from typing import Dict


def load_plugins(group: str, builtins: Dict[str, object]) -> Dict[str, object]:
    plugins = dict(builtins)
    for ep in entry_points(group=group):
        plugins[ep.name] = ep.load()
    return plugins
