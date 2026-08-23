"""Codex CLI agent: `codex exec --full-auto <prompt>`, non-interactive, edits in place."""
from __future__ import annotations

import subprocess


def run(prompt: str, cwd: str, timeout: int = 600) -> int:
    result = subprocess.run(
        ["codex", "exec", "--full-auto", prompt],
        cwd=cwd, timeout=timeout,
    )
    return result.returncode
