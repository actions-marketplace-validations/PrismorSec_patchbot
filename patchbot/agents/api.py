"""Anthropic API agent: no CLI, no npm/node — just `pip install patchbot[api]`.

Runs a small tool loop (bash + write_file, scoped to cwd) via the Python
SDK's tool runner. Good default for CI: nothing to install but a Python
package, and `ANTHROPIC_API_KEY` is the only secret involved.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

DEFAULT_MODEL = "claude-opus-5"
MAX_TURNS = 30


def run(prompt: str, cwd: str, model: Optional[str] = None, timeout: int = 600,
        config: Optional[dict] = None) -> int:
    try:
        import anthropic
        from anthropic import beta_tool
    except ImportError as exc:
        raise RuntimeError(
            "the 'api' agent needs the anthropic package: pip install patchbot[api]"
        ) from exc

    root = Path(cwd).resolve()

    @beta_tool
    def bash(command: str) -> str:
        """Run a shell command in the repository and return its output.

        Args:
            command: The shell command to run.
        """
        result = subprocess.run(
            command, shell=True, cwd=root, capture_output=True, text=True, timeout=120,
        )
        return f"exit={result.returncode}\n{result.stdout}\n{result.stderr}"[:8000]

    @beta_tool
    def write_file(path: str, content: str) -> str:
        """Write content to a file in the repository.

        Args:
            path: Path relative to the repository root.
            content: The full file content to write.
        """
        target = (root / path).resolve()
        if root not in target.parents and target != root:
            return "error: path escapes the repository root"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return "ok"

    client = anthropic.Anthropic()
    runner = client.beta.messages.tool_runner(
        model=model or DEFAULT_MODEL,
        max_tokens=8000,
        tools=[bash, write_file],
        messages=[{"role": "user", "content": prompt}],
    )

    turns = 0
    for _message in runner:
        turns += 1
        if turns >= MAX_TURNS:
            break
    return 0
