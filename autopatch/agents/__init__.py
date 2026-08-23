from __future__ import annotations

from autopatch.registry import load_plugins
from autopatch.agents import claude, codex

BUILTIN = {"claude": claude, "codex": codex}


def get(name: str):
    plugins = load_plugins("autopatch.agents", BUILTIN)
    module = plugins.get(name)
    if module is None:
        raise ValueError(f"unknown agent: {name!r} (available: {sorted(plugins)})")
    return module
