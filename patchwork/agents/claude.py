"""Claude Code CLI agent: `claude -p <prompt>`, non-interactive, edits in place."""
from __future__ import annotations

import subprocess


def run(prompt: str, cwd: str, timeout: int = 600) -> int:
    result = subprocess.run(
        ["claude", "-p", prompt, "--allowedTools", "Edit,Write,Bash",
         "--permission-mode", "acceptEdits"],
        cwd=cwd, timeout=timeout,
    )
    return result.returncode
