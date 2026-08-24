"""Claude Code CLI agent: `claude -p <prompt>`, non-interactive, edits in place."""
from __future__ import annotations

import subprocess
from typing import Optional


def run(prompt: str, cwd: str, model: Optional[str] = None, timeout: int = 600,
        config: Optional[dict] = None) -> int:
    cmd = ["claude", "-p", prompt, "--allowedTools", "Edit,Write,Bash",
           "--permission-mode", "acceptEdits"]
    if model:
        cmd += ["--model", model]
    result = subprocess.run(cmd, cwd=cwd, timeout=timeout)
    return result.returncode
