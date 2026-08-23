from pathlib import Path

from patchbot.scanners import formats

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_trivy():
    findings = formats.parse_trivy((FIXTURES / "trivy.json").read_text())
    assert len(findings) == 1
    f = findings[0]
    assert f.id == "CVE-2021-1234"
    assert f.package.name == "lodash"
    assert f.package.version == "4.17.20"
    assert f.fixed_versions == ["4.17.21"]
    assert f.severity == "high"


def test_parse_grype():
    findings = formats.parse_grype((FIXTURES / "grype.json").read_text())
    assert len(findings) == 1
    f = findings[0]
    assert f.id == "CVE-2021-1234"
    assert f.package.name == "lodash"
    assert f.fixed_versions == ["4.17.21"]
    assert f.severity == "high"


def test_parse_sarif():
    findings = formats.parse_sarif((FIXTURES / "sarif.json").read_text())
    assert len(findings) == 1
    f = findings[0]
    assert f.id == "RULE-1"
    assert f.severity == "high"
    assert "lodash" in f.summary
