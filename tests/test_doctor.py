"""Tests for ``huligan doctor`` / ``huligan info`` (huligan/doctor.py)."""
import json

import pytest

from huligan import doctor

_VALID = {"ok", "warn", "fail", "skipped"}


def test_run_checks_quick_shape():
    report = doctor.run_checks(quick=True)
    assert report.quick is True
    assert report.checks, "expected at least one check"
    assert all(c.status in _VALID for c in report.checks)
    by_key = {c.key: c for c in report.checks}
    # --quick must skip the launch smoke-test and the network manifest check.
    assert by_key["launch"].status == "skipped"
    assert by_key["manifest"].status == "skipped"
    # Core local checks always run.
    assert {"sdk_version", "binary", "fonts", "platform"} <= set(by_key)
    assert report.overall in _VALID


def test_render_json_parses():
    report = doctor.run_checks(quick=True)
    obj = json.loads(doctor.render_json(report))
    assert set(obj) >= {"huligan", "overall", "summary", "quick", "checks"}
    assert obj["quick"] is True
    assert isinstance(obj["checks"], list) and obj["checks"]
    for c in obj["checks"]:
        assert set(c) == {"key", "label", "status", "detail", "data", "hint"}
        assert c["status"] in _VALID
    # summary counts add up to the number of checks
    assert sum(obj["summary"].values()) == len(obj["checks"])


def test_overall_is_worst_status():
    r = doctor.DoctorReport(
        checks=[
            doctor.CheckResult("a", "A", "ok"),
            doctor.CheckResult("b", "B", "skipped"),
            doctor.CheckResult("c", "C", "warn"),
        ],
        quick=False, header={},
    )
    assert r.overall == "warn"          # skipped ignored, warn > ok
    r.checks.append(doctor.CheckResult("d", "D", "fail"))
    assert r.overall == "fail"


def test_missing_binary_is_fail(monkeypatch):
    import huligan.chrome as chrome_mod

    def _raise(*a, **k):
        raise FileNotFoundError("no chrome")

    monkeypatch.setattr(chrome_mod, "find_chrome", _raise)
    r = doctor._check_binary()
    assert r.status == "fail"


def test_missing_extra_is_warn_never_fail(monkeypatch):
    monkeypatch.setattr(doctor, "_dep_ok", lambda mods: False)
    deps = doctor._check_deps()
    assert deps
    assert all(c.status == "warn" for c in deps)  # optional extras never FAIL


def test_present_extra_is_ok(monkeypatch):
    monkeypatch.setattr(doctor, "_dep_ok", lambda mods: True)
    deps = doctor._check_deps()
    assert all(c.status == "ok" for c in deps)


def test_quick_never_launches(monkeypatch):
    """--quick must not spawn Chrome (launch_persistent must not be called)."""
    import huligan.persistent as persistent_mod

    def _boom(*a, **k):
        raise AssertionError("launch_persistent must not run under --quick")

    monkeypatch.setattr(persistent_mod, "launch_persistent", _boom)
    report = doctor.run_checks(quick=True)  # must not raise
    assert {c.key for c in report.checks} >= {"binary", "fonts", "platform"}


def test_launch_refuses_system_path_chrome():
    """A PATH-resolved (non-Huligan) binary must not be launched."""
    binr = doctor.CheckResult("binary", "Chrome binary", "warn",
                              "somechrome", {"path": "/usr/bin/chrome", "source": "path"})
    r = doctor._check_launch(binr)
    assert r.status == "warn"
    assert "system" in r.detail.lower() or "refus" in r.detail.lower()


def test_collect_info_shape():
    info = doctor.collect_info()
    assert set(info) >= {
        "sdk_version", "sdk_version_attr", "build_number", "chrome_version",
        "channel", "conf_schema", "platform", "extras",
    }
    assert isinstance(info["extras"], dict) and info["extras"]
