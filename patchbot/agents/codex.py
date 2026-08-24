"""Codex CLI agent: `codex exec --full-auto <prompt>`, non-interactive, edits in place."""
from __future__ import annotations

import subprocess
from typing import Optional


def run(prompt: str, cwd: str, model: Optional[str] = None, timeout: int = 600,
        config: Optional[dict] = None) -> int:
    cmd = ["codex", "exec", "--full-auto", prompt]
    if model:
        cmd += ["-m", model]
    result = subprocess.run(cmd, cwd=cwd, timeout=timeout)
    return result.returncode
