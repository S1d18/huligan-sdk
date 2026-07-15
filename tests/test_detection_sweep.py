"""Tests for the detection-sweep harness (T1.5) - the deterministic normalization logic.

Live-site adapters cannot be unit-tested here (they need real detectors + an operator's
visual read); these lock the schema, allowlist, counter, and JSON behaviour.
"""
import json

from huligan.testing.detection_sweep import (
    SiteVerdict,
    apply_allowlist,
    render_summary,
    to_json,
)


def test_apply_allowlist_downgrades_known_false_positive():
    still, downgraded = apply_allowlist("deviceandbrowserinfo", ["connectionRTT", "somethingReal"])
    assert downgraded == ["connectionRTT"]
    assert still == ["somethingReal"]


def test_apply_allowlist_unknown_site_passes_through():
    still, downgraded = apply_allowlist("nope", ["x"])
    assert still == ["x"] and downgraded == []


def test_counts_and_summary_render():
    results = [
        SiteVerdict("a", "u", "pass"),
        SiteVerdict("b", "u", "warn", allowlisted=["connectionRTT"]),
        SiteVerdict("c", "u", "fail", notes=["bad"]),
        SiteVerdict("d", "u", "error"),
    ]
    txt = render_summary(results)
    assert "PASS 1 - WARN 1 - FAIL 1 - ERROR 1" in txt
    assert "allowlisted: connectionRTT" in txt
    assert "authoritative" in txt          # the caveat is always printed


def test_to_json_parses_and_retains_raw():
    results = [SiteVerdict("creepjs", "u", "pass", raw={"lies": 0}, notes=["lies 0"])]
    obj = json.loads(to_json(results))
    assert obj["summary"]["pass"] == 1
    assert obj["sites"][0]["raw"] == {"lies": 0}
    assert obj["sites"][0]["verdict"] == "pass"


def test_error_is_distinct_from_pass():
    # A scrape miss (error) must never be counted as a pass.
    obj = json.loads(to_json([SiteVerdict("x", "u", "error")]))
    assert obj["summary"]["error"] == 1 and obj["summary"]["pass"] == 0


def test_exports():
    import huligan.testing as t
    for n in ("run_sweep", "render_summary", "to_json", "apply_allowlist",
              "SiteVerdict", "Adapter", "ALLOWLIST"):
        assert hasattr(t, n), n
