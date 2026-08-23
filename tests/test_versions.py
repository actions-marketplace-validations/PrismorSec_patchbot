from patchbot.versions import parse_version, version_lt, version_gte, in_range, fixed_versions_for


def test_parse_version_basic():
    assert parse_version("1.2.3") == (1, 2, 3)
    assert parse_version("1.2.3-rc.1") == (1, 2, 3)
    assert parse_version("") == ()


def test_version_lt_gte():
    assert version_lt("1.2.3", "1.2.4")
    assert not version_lt("1.2.4", "1.2.3")
    assert version_gte("1.2.4", "1.2.3")
    assert version_gte("1.2.3", "1.2.3")


def test_in_range_exact_versions():
    affected = {"versions": ["4.17.19", "4.17.20"]}
    assert in_range("4.17.20", affected)
    assert not in_range("4.17.21", affected)


def test_in_range_with_fixed_event():
    affected = {"ranges": [{"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": "4.17.21"}]}]}
    assert in_range("4.17.20", affected)
    assert not in_range("4.17.21", affected)


def test_in_range_open_ended():
    affected = {"ranges": [{"type": "SEMVER", "events": [{"introduced": "1.0.0"}]}]}
    assert in_range("5.0.0", affected)
    assert not in_range("0.9.0", affected)


def test_fixed_versions_for():
    affected = {"ranges": [{"events": [{"introduced": "0"}, {"fixed": "4.17.21"}]}]}
    assert fixed_versions_for("4.17.20", affected) == ["4.17.21"]
    assert fixed_versions_for("5.0.0", affected) == []
