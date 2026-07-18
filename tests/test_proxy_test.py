"""Tests for huligan.proxy.test_proxy (composite reachability + GeoIP).

No real proxy or network: ``detect_exit_ip`` and ``GeoIPManager`` are
monkeypatched. Verifies the happy path fills the geo fields, a dead proxy folds
into ``{ok: False}`` (never raises), an unparseable string is reported not
raised, and a reachable proxy whose GeoIP lookup fails stays ``ok: True``.
"""

from huligan import proxy
from huligan import geoip as geoip_mod
from huligan.geoip import GeoIPResult


def _fake_geo():
    g = GeoIPResult()
    g.ip = "5.6.7.8"
    g.country_code = "DE"
    g.country_name = "Germany"
    g.city = "Berlin"
    g.timezone = "Europe/Berlin"
    g.latitude = 52.52
    g.longitude = 13.405
    g.language = "de-DE,de"
    g.source = "local"
    return g


class _FakeMgr:
    def __init__(self, result):
        self._result = result
        self.closed = False

    def lookup(self, ip):
        return self._result

    def close(self):
        self.closed = True


def test_working_proxy_geolocated(monkeypatch):
    monkeypatch.setattr(proxy, "detect_exit_ip", lambda info, timeout=4.0: "5.6.7.8")
    monkeypatch.setattr(geoip_mod, "GeoIPManager", lambda *a, **k: _FakeMgr(_fake_geo()))

    r = proxy.test_proxy("socks5://user:pw@1.2.3.4:1080")
    assert r["ok"] is True
    assert r["ip"] == "5.6.7.8"
    assert r["country_code"] == "DE"
    assert r["city"] == "Berlin"
    assert r["timezone"] == "Europe/Berlin"
    assert r["language"] == "de-DE,de"
    assert r["latitude"] == 52.52
    assert r["longitude"] == 13.405
    assert r["geoip_source"] == "local"
    assert r["latency_ms"] is not None
    assert r["error"] is None


def test_dead_proxy_folds_to_not_ok(monkeypatch):
    def _no_lookup(*a, **k):
        raise AssertionError("GeoIP must not run for an unreachable proxy")

    monkeypatch.setattr(proxy, "detect_exit_ip", lambda info, timeout=4.0: None)
    monkeypatch.setattr(geoip_mod, "GeoIPManager", _no_lookup)

    r = proxy.test_proxy("1.2.3.4:1080")
    assert r["ok"] is False
    assert r["ip"] is None
    assert "unreachable" in r["error"]
    assert r["latency_ms"] is not None


def test_unparseable_string_never_raises():
    r = proxy.test_proxy("not-a-valid-proxy")
    assert r["ok"] is False
    assert "invalid proxy string" in r["error"]
    assert r["ip"] is None


def test_reachable_proxy_but_geoip_error(monkeypatch):
    g = GeoIPResult()
    g.error = "private range"
    monkeypatch.setattr(proxy, "detect_exit_ip", lambda info, timeout=4.0: "9.9.9.9")
    monkeypatch.setattr(geoip_mod, "GeoIPManager", lambda *a, **k: _FakeMgr(g))

    r = proxy.test_proxy("socks5://1.2.3.4:1080")
    assert r["ok"] is True          # the proxy tunnels; only GeoIP failed
    assert r["ip"] == "9.9.9.9"
    assert r["country_code"] is None
    assert r["timezone"] is None
    assert "geoip" in r["error"]
