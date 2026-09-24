"""Manual language in the .conf must survive a direct SDK launch.

LANG-01: a profile with ``language_mode=manual`` + ``languages=...`` launched
without a ``language=`` argument emitted no ``--accept-lang``, so HTTP
Accept-Language (Chrome default) disagreed with ``navigator.languages`` (read
from the .conf). An explicit argument that contradicts the manual conf value was
silently accepted too.

Both launch paths are covered: the sync ``launch_persistent`` and the async
``Browser``. Chrome is never started (Popen is faked, probes are stubbed).
"""

import asyncio
from pathlib import Path

import pytest

from huligan import browser as browser_mod
from huligan import persistent
from huligan.geoip import GeoIPResult, _GeoResolution
from huligan.launch_plan import read_conf_value

MANUAL_LANG_CONF = (
    "# Huligan\n"
    "platform=Win32\n"
    "language_mode=manual\n"
    "languages=fr-CA,fr,en-US,en\n"
)


class _FakePopen:
    def __init__(self, args, env=None, **kw):
        self.args = list(args)
        self.env = env
        self.pid = 1111
        self._code = None

    def poll(self):
        return self._code

    def wait(self, timeout=None):
        self._code = 0
        return 0

    def terminate(self):
        self._code = 0

    def kill(self):
        self._code = -9


def _geo_berlin():
    g = GeoIPResult()
    g.ip = "5.6.7.8"
    g.timezone = "Europe/Berlin"
    g.language = "de-DE,de"
    g.country_code = "DE"
    g.latitude = 52.52
    g.longitude = 13.405
    g.accuracy = 100
    return g


def _resolution(language=None):
    return _GeoResolution(
        geo=_geo_berlin(),
        timezone="Europe/Berlin",
        languages=language or "de-DE,de,en-US,en",
        webrtc_spoof_ipv4=None,
        public_ip="5.6.7.8",
    )


@pytest.fixture
def fake_launch(monkeypatch):
    created = []

    def fake_popen(args, env=None, **kw):
        p = _FakePopen(args, env, **kw)
        created.append(p)
        return p

    monkeypatch.setattr(persistent, "find_chrome", lambda explicit_path=None: "chrome")
    monkeypatch.setattr(persistent.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(browser_mod, "find_chrome", lambda explicit_path=None: Path("chrome"))
    monkeypatch.setattr(browser_mod.subprocess, "Popen", fake_popen)
    return created


def _conf(tmp_path, body):
    p = tmp_path / "p.conf"
    p.write_text(body, encoding="utf-8")
    return p


def _accept_lang(args):
    return [a for a in args if a.startswith("--accept-lang=")]


# --- LANG-01: launch_persistent -------------------------------------------

@pytest.mark.parametrize("conf_geo", ["off", "copy", "inplace"])
def test_persistent_manual_conf_language_reaches_accept_lang(fake_launch, tmp_path, conf_geo):
    conf = _conf(tmp_path, MANUAL_LANG_CONF)
    res = persistent.launch_persistent(
        profile_path=conf, user_data_dir=tmp_path / "ud", geoip=False, conf_geo=conf_geo,
    )
    args = fake_launch[0].args
    assert _accept_lang(args) == ["--accept-lang=fr-CA,fr,en-US,en"]
    assert "--lang=fr" in args
    launched = fake_launch[0].env["HULIGAN_CONFIG_PATH"]
    assert read_conf_value(launched, "language_mode") == "manual"
    assert read_conf_value(launched, "languages") == "fr-CA,fr,en-US,en"
    res.stop()


def test_persistent_manual_conf_language_beats_geoip(fake_launch, tmp_path, monkeypatch):
    seen = {}

    def fake_resolve(proxy_info, *, timezone=None, language=None, geoip=True, resolve_webrtc=True):
        seen["language"] = language
        return _resolution(language)

    monkeypatch.setattr(persistent, "_resolve_geo", fake_resolve)
    conf = _conf(tmp_path, MANUAL_LANG_CONF)
    res = persistent.launch_persistent(profile_path=conf, user_data_dir=tmp_path / "ud")
    assert seen["language"] == "fr-CA,fr,en-US,en"
    assert _accept_lang(fake_launch[0].args) == ["--accept-lang=fr-CA,fr,en-US,en"]
    res.stop()


def test_persistent_explicit_language_conflicting_with_manual_conf_raises(fake_launch, tmp_path):
    conf = _conf(tmp_path, MANUAL_LANG_CONF)
    with pytest.raises(ValueError, match="language"):
        persistent.launch_persistent(
            profile_path=conf, language="de-DE,de", user_data_dir=tmp_path / "ud",
            geoip=False, conf_geo="off",
        )
    assert not fake_launch


def test_persistent_explicit_language_matching_manual_conf_is_fine(fake_launch, tmp_path):
    conf = _conf(tmp_path, MANUAL_LANG_CONF)
    res = persistent.launch_persistent(
        profile_path=conf, language=" fr-CA, fr ,en-US,en", user_data_dir=tmp_path / "ud",
        geoip=False, conf_geo="off",
    )
    assert _accept_lang(fake_launch[0].args)
    res.stop()


def test_persistent_auto_conf_language_is_not_forced(fake_launch, tmp_path):
    conf = _conf(tmp_path, "platform=Win32\nlanguage_mode=auto\nlanguages=fr-CA,fr\n")
    res = persistent.launch_persistent(
        profile_path=conf, user_data_dir=tmp_path / "ud", geoip=False, conf_geo="off",
    )
    assert _accept_lang(fake_launch[0].args) == []
    res.stop()


# --- async Browser: same rules ---------------------------------------------

def _run_browser_start(monkeypatch, conf, geo=None, **kw):
    monkeypatch.setattr(
        browser_mod, "detect_local_public_ip",
        lambda timeout=4.0: "5.6.7.8" if geo else None,
    )

    class _Mgr:
        def lookup(self, ip):
            return geo

        def close(self):
            pass

    monkeypatch.setattr(browser_mod, "GeoIPManager", _Mgr)

    async def no_wait(self, timeout=15.0):
        return None

    monkeypatch.setattr(browser_mod.Browser, "_wait_for_cdp", no_wait)
    b = browser_mod.Browser(profile_path=conf, user_data_dir=conf.parent / "ud", **kw)
    asyncio.run(b.start())
    return b


def test_browser_manual_conf_language_reaches_accept_lang(fake_launch, tmp_path, monkeypatch):
    conf = _conf(tmp_path, MANUAL_LANG_CONF)
    _run_browser_start(monkeypatch, conf, geo=_geo_berlin())
    assert _accept_lang(fake_launch[0].args) == ["--accept-lang=fr-CA,fr,en-US,en"]
    assert read_conf_value(conf, "language_mode") == "manual"
    assert read_conf_value(conf, "languages") == "fr-CA,fr,en-US,en"


def test_browser_explicit_language_conflicting_with_manual_conf_raises(fake_launch, tmp_path, monkeypatch):
    conf = _conf(tmp_path, MANUAL_LANG_CONF)
    with pytest.raises(ValueError, match="language"):
        _run_browser_start(monkeypatch, conf, language="de-DE,de")
    assert not fake_launch
