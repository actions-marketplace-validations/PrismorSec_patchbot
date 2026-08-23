from pathlib import Path

from patchwork.models import Package
from patchwork.feeds import file as file_feed

FIXTURE = str(Path(__file__).parent / "fixtures" / "feed.json")


def test_file_feed_matches_vulnerable_version():
    packages = [Package("npm", "lodash", "4.17.20")]
    findings = file_feed.match(packages, {"path": FIXTURE, "name": "internal"})
    assert len(findings) == 1
    assert findings[0].id == "GHSA-test-lodash"
    assert findings[0].fixed_versions == ["4.17.21"]
    assert findings[0].source == "internal"


def test_file_feed_skips_patched_version():
    packages = [Package("npm", "lodash", "4.17.21")]
    findings = file_feed.match(packages, {"path": FIXTURE})
    assert findings == []


def test_file_feed_skips_unrelated_package():
    packages = [Package("pip", "lodash", "4.17.20")]
    findings = file_feed.match(packages, {"path": FIXTURE})
    assert findings == []
