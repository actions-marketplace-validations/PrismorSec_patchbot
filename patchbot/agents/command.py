"""Bring-your-own-agent: run any command that can edit files given a prompt.

Configure with `[fix] agent = "command"` and a `cmd` template, e.g.:

    [fix]
    agent = "command"
    cmd = "aider --yes --message {prompt}"

`{prompt}` and `{model}` are substituted into the command string. The
prompt is also exported as the PATCHBOT_PROMPT environment variable so a
command can read it without fighting shell quoting.
"""
from __future__ import annotations

import os
import subprocess
from typing import Optional


def run(prompt: str, cwd: str, model: Optional[str] = None, timeout: int = 600,
        config: Optional[dict] = None) -> int:
    cmd_template = (config or {}).get("cmd")
    if not cmd_template:
        raise RuntimeError("agent 'command' requires [fix] cmd = \"...\" in patchbot.toml")
    cmd = cmd_template.format(prompt=prompt, model=model or "")
    env = dict(os.environ, PATCHBOT_PROMPT=prompt)
    result = subprocess.run(cmd, shell=True, cwd=cwd, env=env, timeout=timeout)
    return result.returncode
