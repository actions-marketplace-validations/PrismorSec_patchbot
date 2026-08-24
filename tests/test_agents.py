import os
import subprocess
import sys

import pytest

from patchbot.agents import command


def test_command_agent_substitutes_prompt_and_model(tmp_path):
    out = tmp_path / "out.txt"
    cfg = {"cmd": f"{sys.executable} -c \"import os,sys; open(sys.argv[1],'w').write(os.environ['PATCHBOT_PROMPT']+'|'+sys.argv[2])\" {out} {{model}}"}
    rc = command.run("fix the thing", str(tmp_path), model="claude-opus-5", config=cfg)
    assert rc == 0
    assert out.read_text() == "fix the thing|claude-opus-5"


def test_command_agent_requires_cmd_config(tmp_path):
    with pytest.raises(RuntimeError):
        command.run("prompt", str(tmp_path), config={})
