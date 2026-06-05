"""Tests for the synchronous persistent-launch API (huligan.persistent).

Chrome is never actually launched: ``subprocess.Popen`` and ``find_chrome`` are
monkeypatched, and ``geoip=False`` skips all network probes. What we verify:

  * the background asyncio loop starts, runs coroutines, and tears down with no
    leaked thread;
  * ``proxy_type`` overrides the parsed default (GUI passes ``http``);
  * an authenticated proxy spins up a forwarder on the background loop and Chrome
    is pointed at the local no-auth SOCKS5 port;
  * ``mutate_conf`` writes resolved timezone/language into the .conf;
  * ``LaunchResult`` honours the Popen-compatible contract a GUI relies on;
  * ``stop()`` is idempotent and tears the forwarder/loop down.
"""

import threading
import time
from pathlib import Path

import pytest

from huligan import persistent


class FakePopen:
    """Minimal Popen stand-in capturing args/env."""

    def __init__(self, args, env=None, **kw):
        self.args = list(args)
        self.env = env
        self.kw = kw
        self.pid = 4321
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


@pytest.fixture
def captured_popen(monkeypatch):
    created = []

    def fake_popen(args, env=None, **kw):
        p = FakePopen(args, env, **kw)
        created.append(p)
        return p

    monkeypatch.setattr(persistent, "find_chrome", lambda explicit_path=None: "chrome")
    monkeypatch.setattr(persistent.subprocess, "Popen", fake_popen)
    return created


def _conf(tmp_path, body="# Huligan\nplatform=Win32\n"):
    p = tmp_path / "p.conf"
    p.write_text(body, encoding="utf-8")
    return p


# --- background loop ------------------------------------------------------

def test_background_loop_runs_and_tears_down_no_leak():
    before = threading.active_count()
    bl = persistent._BackgroundLoop()

    async def answer():
        return 7

    assert bl.run_coro(answer(), timeout=3) == 7
    bl.shutdown(timeout=3)
    time.sleep(0.2)
    assert threading.active_count() <= before


# --- launch_persistent ----------------------------------------------------

def test_proxy_type_override(captured_popen, tmp_path):
    conf = _conf(tmp_path)
    res = persistent.launch_persistent(
        profile_path=conf,
        proxy="1.2.3.4:8080",      # host:port -> parse_proxy_string defaults socks5
        proxy_type="http",          # GUI override
        user_data_dir=tmp_path / "ud",
        geoip=False,
        conf_geo="off",
    )
    args = captured_popen[0].args
    assert "--proxy-server=http://1.2.3.4:8080" in args
    res.stop()


def test_proxy_default_socks5_without_override(captured_popen, tmp_path):
    conf = _conf(tmp_path)
    res = persistent.launch_persistent(
        profile_path=conf,
        proxy="1.2.3.4:8080",
        user_data_dir=tmp_path / "ud",
        geoip=False,
        conf_geo="off",
    )
    assert "--proxy-server=socks5://1.2.3.4:8080" in captured_popen[0].args
    res.stop()


def test_auth_proxy_starts_forwarder(captured_popen, tmp_path):
    conf = _conf(tmp_path)
    res = persistent.launch_persistent(
        profile_path=conf,
        proxy="socks5://user:pw@9.9.9.9:1080",
        user_data_dir=tmp_path / "ud",
        geoip=False,
        conf_geo="off",
    )
    args = captured_popen[0].args
    pserver = [a for a in args if a.startswith("--proxy-server=")]
    assert pserver and pserver[0].startswith("--proxy-server=socks5://127.0.0.1:")
    assert res._forwarder is not None
    assert res._bgloop is not None and res._bgloop.is_alive
    res.stop()
    assert res._forwarder is None
    assert res._bgloop is None


def test_no_proxy_has_no_proxy_flags(captured_popen, tmp_path):
    conf = _conf(tmp_path)
    res = persistent.launch_persistent(
        profile_path=conf,
        user_data_dir=tmp_path / "ud",
        geoip=False,
        conf_geo="off",
    )
    args = captured_popen[0].args
    assert not any(a.startswith("--proxy-server") for a in args)
    assert res._forwarder is None and res._bgloop is None
    res.stop()


def test_cdp_mode_forwarded_from_conf(captured_popen, tmp_path):
    conf = _conf(tmp_path, "# h\ncdp_mode=paranoid\n")
    res = persistent.launch_persistent(
        profile_path=conf,
        user_data_dir=tmp_path / "ud",
        geoip=False,
        conf_geo="off",
    )
    assert captured_popen[0].env.get("HULIGAN_CDP_MODE") == "paranoid"
    res.stop()


def test_conf_inplace_writes_manual_geo(captured_popen, tmp_path):
    conf = _conf(tmp_path)
    res = persistent.launch_persistent(
        profile_path=conf,
        timezone="Europe/Berlin",
        language="de-DE,de",
        user_data_dir=tmp_path / "ud",
        geoip=False,
        conf_geo="inplace",
    )
    text = conf.read_text(encoding="utf-8")
    assert "timezone=Europe/Berlin" in text
    assert "timezone_mode=manual" in text   # explicit override -> manual
    assert "languages=de-DE,de" in text
    assert "language_mode=manual" in text
    # The launched conf is the saved file itself.
    assert captured_popen[0].env.get("HULIGAN_CONFIG_PATH") == str(conf)
    assert "--accept-lang=de-DE,de" in captured_popen[0].args
    assert captured_popen[0].env.get("TZ") == "Europe/Berlin"
    res.stop()


def test_conf_copy_default_never_mutates_saved(captured_popen, tmp_path):
    body = "# Huligan\nplatform=Win32\n"
    conf = _conf(tmp_path, body)
    res = persistent.launch_persistent(
        profile_path=conf,
        timezone="Europe/Berlin",
        language="de-DE,de",
        user_data_dir=tmp_path / "ud",
        geoip=False,
        # conf_geo defaults to "copy"
    )
    # Saved profile is byte-for-byte untouched.
    assert conf.read_text(encoding="utf-8") == body
    # The binary reads a temp COPY (not the saved file) that carries the geo.
    launched = captured_popen[0].env.get("HULIGAN_CONFIG_PATH")
    assert launched != str(conf)
    assert res.temp_conf is not None and Path(launched) == res.temp_conf
    copy_text = res.temp_conf.read_text(encoding="utf-8")
    assert "timezone=Europe/Berlin" in copy_text and "languages=de-DE,de" in copy_text
    # Flags/env still reflect the resolved values.
    assert "--accept-lang=de-DE,de" in captured_popen[0].args
    assert captured_popen[0].env.get("TZ") == "Europe/Berlin"
    # stop() deletes the temp copy.
    res.stop()
    assert res.temp_conf is None


def test_conf_off_leaves_conf_untouched_and_no_temp(captured_popen, tmp_path):
    body = "# Huligan\nplatform=Win32\n"
    conf = _conf(tmp_path, body)
    res = persistent.launch_persistent(
        profile_path=conf,
        timezone="Europe/Berlin",
        user_data_dir=tmp_path / "ud",
        geoip=False,
        conf_geo="off",
    )
    assert conf.read_text(encoding="utf-8") == body
    assert res.temp_conf is None
    assert captured_popen[0].env.get("HULIGAN_CONFIG_PATH") == str(conf)
    res.stop()


def test_conf_geo_invalid_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(persistent, "find_chrome", lambda explicit_path=None: "chrome")
    conf = _conf(tmp_path)
    with pytest.raises(ValueError):
        persistent.launch_persistent(profile_path=conf, conf_geo="bogus", geoip=False)


def test_url_is_last_arg(captured_popen, tmp_path):
    conf = _conf(tmp_path)
    res = persistent.launch_persistent(
        profile_path=conf,
        url="https://browserscan.net",
        user_data_dir=tmp_path / "ud",
        geoip=False,
        conf_geo="off",
    )
    assert captured_popen[0].args[-1] == "https://browserscan.net"
    res.stop()


def test_missing_profile_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(persistent, "find_chrome", lambda explicit_path=None: "chrome")
    with pytest.raises(FileNotFoundError):
        persistent.launch_persistent(profile_path=tmp_path / "nope.conf", geoip=False)


def test_popen_kwargs_forwarded(captured_popen, tmp_path):
    conf = _conf(tmp_path)
    res = persistent.launch_persistent(
        profile_path=conf,
        user_data_dir=tmp_path / "ud",
        geoip=False,
        conf_geo="off",
        popen_kwargs={"creationflags": 0x08000000},  # CREATE_NO_WINDOW
    )
    assert captured_popen[0].kw.get("creationflags") == 0x08000000
    res.stop()


# --- LaunchResult contract ------------------------------------------------

def test_launchresult_popen_contract():
    fp = FakePopen(["chrome"])
    r = persistent.LaunchResult(
        process=fp,
        cdp_port=9222,
        profile_path=Path("p.conf"),
        user_data_dir=Path("ud"),
    )
    assert r.pid == 4321
    assert r.poll() is None
    assert r.cdp_url == "http://127.0.0.1:9222"
    # GUI attaches a log handle freely.
    r._log_handle = None
    r.stop()
    r.stop()  # idempotent
    assert fp.poll() == 0
