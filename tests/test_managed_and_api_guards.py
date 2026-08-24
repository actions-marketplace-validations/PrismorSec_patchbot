import os

import pytest

from patchbot.agents import api, managed


def test_managed_requires_ids(tmp_path, monkeypatch):
    monkeypatch.delenv("PATCHBOT_MANAGED_AGENT_ID", raising=False)
    monkeypatch.delenv("PATCHBOT_MANAGED_ENVIRONMENT_ID", raising=False)
    monkeypatch.delenv("PATCHBOT_MANAGED_VAULT_ID", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    with pytest.raises(RuntimeError, match="agent_id/environment_id/vault_id"):
        managed.run("prompt", str(tmp_path), config={})


def test_managed_requires_github_token(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
        managed.run("prompt", str(tmp_path), config={
            "agent_id": "a", "environment_id": "e", "vault_id": "v",
        })


def test_api_agent_importable():
    # Just confirms the module loads and exposes run() without needing a
    # live ANTHROPIC_API_KEY: the actual tool loop needs real credentials
    # and is exercised manually (see README verification notes).
    assert callable(api.run)
