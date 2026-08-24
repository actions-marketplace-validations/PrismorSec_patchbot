import json
import subprocess

from patchbot import bump


def test_bump_npm_direct_dependency_rewrites_manifest_and_lockfile(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "demo", "dependencies": {"lodash": "^4.17.20"},
    }))
    (tmp_path / "package-lock.json").write_text(json.dumps({
        "name": "demo", "lockfileVersion": 3,
        "packages": {"": {"name": "demo"}, "node_modules/lodash": {"version": "4.17.20"}},
    }))

    npm_available = subprocess.run(["which", "npm"], capture_output=True).returncode == 0
    ok = bump.try_bump(str(tmp_path), "npm", "lodash", "4.17.21")

    manifest = json.loads((tmp_path / "package.json").read_text())
    assert manifest["dependencies"]["lodash"] == "^4.17.21"
    if npm_available:
        from patchbot.versions import version_gte
        assert ok
        lock = json.loads((tmp_path / "package-lock.json").read_text())
        # "^4.17.21" lets npm resolve to any newer non-major release.
        assert version_gte(lock["packages"]["node_modules/lodash"]["version"], "4.17.21")


def test_bump_npm_transitive_only_returns_false(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"name": "demo", "dependencies": {}}))
    assert bump.try_bump(str(tmp_path), "npm", "lodash", "4.17.21") is False


def test_bump_pip_rewrites_requirements(tmp_path):
    (tmp_path / "requirements.txt").write_text("flask==2.0.0\nrequests==2.28.0\n")
    ok = bump.try_bump(str(tmp_path), "pip", "flask", "2.0.3")
    assert ok
    text = (tmp_path / "requirements.txt").read_text()
    assert "flask==2.0.3" in text
    assert "requests==2.28.0" in text


def test_bump_unknown_ecosystem_returns_false(tmp_path):
    assert bump.try_bump(str(tmp_path), "maven", "org.example", "1.0.0") is False
