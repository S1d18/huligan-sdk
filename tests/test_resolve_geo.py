"""Tests for huligan.geoip.resolve_launch_geo (launch geo preview).

The preview must predict exactly what launch_persistent applies (both now share
geoip._resolve_geo). Network + GeoIP are monkeypatched; verifies the proxy vs
direct source-IP choice, explicit-override precedence, and the output shape.
"""

import pytest

from huligan import geoip as g
from huligan.geoip import GeoIPResult, resolve_launch_geo


def _geo():
    r = GeoIPResult()
    r.timezone = "Europe/Berlin"
    r.language = "de-DE,de"
    r.latitude = 52.52
    r.longitude = 13.405
    r.accuracy = 50000
    r.source = "online"
    return r


class _Mgr:
    def __init__(self, res):
        self._res = res

    def lookup(self, ip):
        self._res.ip = ip
        return self._res

    def close(self):
        pass


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(g, "GeoIPManager", lambda *a, **k: _Mgr(_geo()))
    monkeypatch.setattr(g, "detect_local_public_ip", lambda timeout=4.0: "5.5.5.5")
    monkeypatch.setattr(g, "detect_exit_ip", lambda info, timeout=4.0: "8.8.8.8")


def test_proxy_uses_exit_ip_for_webrtc(patched):
    out = resolve_launch_geo("socks5://u:p@1.2.3.4:1080")
    assert out["timezone"] == "Europe/Berlin"
    assert out["languages"] == "de-DE,de,en-US,en"   # en fallbacks appended
    assert out["geolocation"] == {
        "latitude": 52.52,
        "longitude": 13.405,
        "accuracy": 50000,
    }
    assert out["webrtc_spoof_ipv4"] == "8.8.8.8"   # proxy EXIT IP, not host
    assert out["geoip_source"] == "online"


def test_direct_connection_uses_local_public_ip(patched):
    out = resolve_launch_geo(None)
    # no proxy -> geo source is the local public IP; webrtc is that same IP
    assert out["timezone"] == "Europe/Berlin"
    assert out["webrtc_spoof_ipv4"] == "5.5.5.5"


def test_explicit_timezone_suppresses_geo(patched):
    out = resolve_launch_geo("socks5://1.2.3.4:1080", timezone="America/New_York")
    assert out["timezone"] == "America/New_York"
    assert out["geolocation"] is None    # explicit tz skips the GeoIP lookup
    assert out["languages"] is None
    assert out["webrtc_spoof_ipv4"] == "8.8.8.8"  # webrtc probe still runs


def test_explicit_language_overrides_geo(patched):
    out = resolve_launch_geo("socks5://1.2.3.4:1080", language="fr-FR,fr")
    assert out["languages"] == "fr-FR,fr"
    assert out["timezone"] == "Europe/Berlin"   # tz still from GeoIP


def test_geoip_appends_en_fallbacks(patched, monkeypatch):
    geo = _geo()
    geo.language = "ru-RU,ru"
    monkeypatch.setattr(g, "GeoIPManager", lambda *a, **k: _Mgr(geo))
    out = resolve_launch_geo("socks5://1.2.3.4:1080")
    assert out["languages"] == "ru-RU,ru,en-US,en"
