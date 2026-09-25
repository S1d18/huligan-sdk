"""Manual timezone in the .conf must survive a direct SDK launch.

Counterpart of LANG-01 (``test_conf_language_mode.py``): a profile with
``timezone_mode=manual`` + ``timezone=...`` launched WITHOUT a ``timezone=``
argument had its zone overwritten by GeoIP (launched .conf + ``TZ`` env), and
``timezone_mode`` flipped to ``auto``. Both launch paths are covered; Chrome is
never started (Popen is faked, probes are stubbed by the shared fixtures).
"""

import pytest

from huligan import persistent
from huligan.launch_plan import read_conf_value, resolve_conf_timezone

from test_conf_language_mode import (  # noqa: F401  (fixture re-export)
    _conf,
    _geo_berlin,
    _resolution,
    _run_browser_start,
    fake_launch,
)

MANUAL_TZ_CONF = (
    "# Huligan\n"
    "platform=Win32\n"
    "timezone_mode=manual\n"
    "timezone=America/Chicago\n"
    "language_mode=auto\n"
    "languages=en-US,en\n"
)


def test_resolve_conf_timezone_rules(tmp_path):
    manual = _conf(tmp_path, MANUAL_TZ_CONF)
    assert resolve_conf_timezone(manual, None) == "America/Chicago"
    assert resolve_conf_timezone(manual, "america/chicago") == "america/chicago"
    with pytest.raises(ValueError, match="timezone"):
        resolve_conf_timezone(manual, "Europe/Berlin")
    auto = tmp_path / "auto.conf"
    auto.write_text("timezone_mode=auto\ntimezone=Asia/Tokyo\n", encoding="utf-8")
    assert resolve_conf_timezone(auto, None) is None
    assert resolve_conf_timezone(auto, "Europe/Paris") == "Europe/Paris"


def _stub_geo(monkeypatch, seen):
    def fake_resolve(proxy_info, *, timezone=None, language=None, geoip=True, resolve_webrtc=True):
        seen["timezone"] = timezone
        return _resolution(language)

    monkeypatch.setattr(persistent, "_resolve_geo", fake_resolve)


@pytest.mark.parametrize("conf_geo", ["copy", "inplace", "off"])
def test_persistent_manual_conf_timezone_beats_geoip(fake_launch, tmp_path, monkeypatch, conf_geo):
    seen = {}
    _stub_geo(monkeypatch, seen)
    conf = _conf(tmp_path, MANUAL_TZ_CONF)
    res = persistent.launch_persistent(
        profile_path=conf, user_data_dir=tmp_path / "ud", conf_geo=conf_geo)
    proc = fake_launch[0]
    assert proc.env.get("TZ") == "America/Chicago"
    launched = proc.env["HULIGAN_CONFIG_PATH"]
    assert read_conf_value(launched, "timezone") == "America/Chicago"
    assert read_conf_value(launched, "timezone_mode") == "manual"
    # GeoIP still runs for the auto fields (language stays GeoIP-driven).
    assert seen["timezone"] is None
    if conf_geo != "off":
        assert read_conf_value(launched, "languages") == "de-DE,de,en-US,en"
    res.stop()


def test_persistent_explicit_timezone_conflicting_with_manual_conf_raises(fake_launch, tmp_path):
    conf = _conf(tmp_path, MANUAL_TZ_CONF)
    with pytest.raises(ValueError, match="timezone"):
        persistent.launch_persistent(
            profile_path=conf, timezone="Europe/Berlin", user_data_dir=tmp_path / "ud",
            geoip=False, conf_geo="off",
        )
    assert not fake_launch


def test_persistent_auto_conf_timezone_still_follows_geoip(fake_launch, tmp_path, monkeypatch):
    _stub_geo(monkeypatch, {})
    conf = _conf(tmp_path, MANUAL_TZ_CONF.replace("timezone_mode=manual", "timezone_mode=auto"))
    res = persistent.launch_persistent(profile_path=conf, user_data_dir=tmp_path / "ud")
    launched = fake_launch[0].env["HULIGAN_CONFIG_PATH"]
    assert read_conf_value(launched, "timezone") == "Europe/Berlin"
    assert read_conf_value(launched, "timezone_mode") == "auto"
    res.stop()


def test_browser_manual_conf_timezone_beats_geoip(fake_launch, tmp_path, monkeypatch):
    conf = _conf(tmp_path, MANUAL_TZ_CONF)
    _run_browser_start(monkeypatch, conf, geo=_geo_berlin())
    assert fake_launch[0].env.get("TZ") == "America/Chicago"
    assert read_conf_value(conf, "timezone") == "America/Chicago"
    assert read_conf_value(conf, "timezone_mode") == "manual"
    # language (auto) is still GeoIP-derived
    assert read_conf_value(conf, "languages").startswith("de-DE")


def test_browser_explicit_timezone_conflicting_with_manual_conf_raises(fake_launch, tmp_path, monkeypatch):
    conf = _conf(tmp_path, MANUAL_TZ_CONF)
    with pytest.raises(ValueError, match="timezone"):
        _run_browser_start(monkeypatch, conf, timezone="Europe/Berlin")
    assert not fake_launch
