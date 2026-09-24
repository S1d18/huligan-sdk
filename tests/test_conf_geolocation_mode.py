"""Manual geolocation in the .conf must survive a direct SDK launch.

GeoIP-derived latitude/longitude used to overwrite a ``geolocation_mode=manual``
position in both launch paths (``launch_persistent`` and the async
``Browser``). Chrome is never started (Popen is faked, probes are stubbed).
"""

import pytest

from huligan import persistent
from huligan.launch_plan import read_conf_value

from test_conf_language_mode import (  # shared fakes
    _conf,
    _geo_berlin,
    _resolution,
    _run_browser_start,
    fake_launch,  # noqa: F401  (pytest fixture)
)

MANUAL_GEO_CONF = (
    "# Huligan\n"
    "platform=Win32\n"
    "geolocation_mode=manual\n"
    "geolocation_latitude=48.8566\n"
    "geolocation_longitude=2.3522\n"
    "geolocation_accuracy=25\n"
)


# --- launch_persistent -----------------------------------------------------

@pytest.mark.parametrize("conf_geo", ["copy", "inplace"])
def test_persistent_manual_geolocation_not_overwritten(fake_launch, tmp_path, monkeypatch, conf_geo):
    monkeypatch.setattr(persistent, "_resolve_geo", lambda *a, **k: _resolution())
    conf = _conf(tmp_path, MANUAL_GEO_CONF)
    res = persistent.launch_persistent(
        profile_path=conf, user_data_dir=tmp_path / "ud", conf_geo=conf_geo,
    )
    launched = fake_launch[0].env["HULIGAN_CONFIG_PATH"]
    assert read_conf_value(launched, "geolocation_mode") == "manual"
    assert read_conf_value(launched, "geolocation_latitude") == "48.8566"
    assert read_conf_value(launched, "geolocation_longitude") == "2.3522"
    assert read_conf_value(launched, "geolocation_accuracy") == "25"
    # Timezone (auto) still follows GeoIP.
    assert read_conf_value(launched, "timezone") == "Europe/Berlin"
    res.stop()


def test_persistent_auto_geolocation_still_follows_geoip(fake_launch, tmp_path, monkeypatch):
    monkeypatch.setattr(persistent, "_resolve_geo", lambda *a, **k: _resolution())
    conf = _conf(tmp_path, "platform=Win32\ngeolocation_mode=auto\n")
    res = persistent.launch_persistent(profile_path=conf, user_data_dir=tmp_path / "ud")
    launched = fake_launch[0].env["HULIGAN_CONFIG_PATH"]
    assert read_conf_value(launched, "geolocation_latitude") == "52.52"
    res.stop()


# --- async Browser ---------------------------------------------------------

def test_browser_manual_geolocation_not_overwritten(fake_launch, tmp_path, monkeypatch):
    conf = _conf(tmp_path, MANUAL_GEO_CONF)
    _run_browser_start(monkeypatch, conf, geo=_geo_berlin())
    assert read_conf_value(conf, "geolocation_mode") == "manual"
    assert read_conf_value(conf, "geolocation_latitude") == "48.8566"
    assert read_conf_value(conf, "geolocation_longitude") == "2.3522"
    assert read_conf_value(conf, "timezone") == "Europe/Berlin"
