"""Unit tests for the shared launch-plan builder (huligan.launch_plan).

Pure tests — no Chrome, no network. They lock the anti-detect flag contract so
the GUI path (which now delegates to this builder via launch_persistent) cannot
silently drift from the automation path.
"""

import os

import pytest

from huligan.launch_plan import (
    build_launch_plan,
    cdp_mode_from_conf,
    find_free_port,
    read_conf_value,
    update_conf_keys,
)


def _plan(**over):
    base = dict(
        chrome_path="chrome",
        profile_path="p.conf",
        cdp_port=9222,
        user_data_dir="ud",
        base_env={},  # isolate from the real environment
    )
    base.update(over)
    return build_launch_plan(**base)


def test_minimal_no_proxy():
    args, env = _plan()
    assert args[0] == "chrome"
    assert "--no-sandbox" in args
    assert "--remote-debugging-port=9222" in args
    assert "--remote-allow-origins=*" in args
    assert "--user-data-dir=ud" in args
    # No proxy -> no proxy/leak flags at all.
    assert not any(a.startswith("--proxy-server") for a in args)
    assert not any("host-resolver-rules" in a for a in args)
    assert not any("webrtc" in a for a in args)
    assert env["HULIGAN_CONFIG_PATH"] == "p.conf"
    assert "TZ" not in env
    assert "HULIGAN_CDP_MODE" not in env


def test_forwarder_takes_precedence_over_direct_proxy():
    args, _ = _plan(
        forwarder_port=51000,
        proxy_info={"host": "1.2.3.4", "port": 8080, "type": "http"},
    )
    # Forwarder wins: Chrome points at the local no-auth SOCKS5.
    assert "--proxy-server=socks5://127.0.0.1:51000" in args
    assert not any(a == "--proxy-server=http://1.2.3.4:8080" for a in args)
    # ...but the leak flags still key off proxy_info.
    assert "--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1 , EXCLUDE 1.2.3.4" in args


def test_direct_proxy_when_no_forwarder():
    args, _ = _plan(proxy_info={"host": "9.9.9.9", "port": 1080, "type": "socks5"})
    assert "--proxy-server=socks5://9.9.9.9:1080" in args
    assert "EXCLUDE 9.9.9.9" in " ".join(args)


def test_webrtc_disable_flag_only_without_spoof_ip():
    # No spoof IP -> blanket disable flag present.
    args, _ = _plan(proxy_info={"host": "9.9.9.9", "port": 1080, "type": "socks5"})
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in args
    assert "--enforce-webrtc-ip-permission-check" in args

    # Spoof IP set -> blanket disable omitted (binary rewrites at source),
    # but the permission-check flag stays.
    args2, _ = _plan(
        proxy_info={"host": "9.9.9.9", "port": 1080, "type": "socks5"},
        webrtc_spoof_ip="9.9.9.9",
    )
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" not in args2
    assert "--enforce-webrtc-ip-permission-check" in args2


def test_language_flags():
    args, _ = _plan(language="fi-FI,fi,en-US,en")
    assert "--lang=fi" in args
    assert "--accept-lang=fi-FI,fi,en-US,en" in args
    assert "--disable-reduce-accept-language" in args
    # ReduceAcceptLanguage is merged INTO the single --disable-features switch,
    # not emitted as its own switch: Chrome honours only the last
    # --disable-features on the command line, so appending a second one would
    # silently drop the TLS-pin features (JA4 regression). Assert membership in
    # the one switch and that there is exactly one.
    df = [a for a in args if a.startswith("--disable-features=")]
    assert len(df) == 1, f"expected exactly one --disable-features, got {df}"
    feats = df[0].split("=", 1)[1].split(",")
    assert "ReduceAcceptLanguage" in feats
    assert "ReduceAcceptLanguageHTTP" in feats
    # the TLS pins must survive alongside the language features
    assert "TLSTrustAnchorIDs" in feats
    assert "TlsMldsaSignatures" in feats


def test_no_language_no_lang_flags():
    args, _ = _plan()
    assert not any(a.startswith("--lang=") for a in args)
    assert not any(a.startswith("--accept-lang=") for a in args)
    # The TLS pins are unconditional; the language features must be absent.
    df = [a for a in args if a.startswith("--disable-features=")]
    assert len(df) == 1
    feats = df[0].split("=", 1)[1].split(",")
    assert "TLSTrustAnchorIDs" in feats and "TlsMldsaSignatures" in feats
    assert "ReduceAcceptLanguage" not in feats


def test_env_timezone_and_cdp_mode():
    _, env = _plan(timezone="Europe/Helsinki", cdp_mode="paranoid")
    assert env["TZ"] == "Europe/Helsinki"
    assert env["HULIGAN_CDP_MODE"] == "paranoid"


def test_cdp_mode_not_overridden_when_already_in_env():
    _, env = _plan(cdp_mode="paranoid", base_env={"HULIGAN_CDP_MODE": "isolated"})
    # Operator-set env wins.
    assert env["HULIGAN_CDP_MODE"] == "isolated"


def test_headless_and_extra_args_and_url_order():
    args, _ = _plan(headless=True, extra_args=["--mute-audio"], url="https://example.com")
    assert "--headless=new" in args
    assert "--mute-audio" in args
    # URL is the last positional argument.
    assert args[-1] == "https://example.com"
    # extra_args come before the url.
    assert args.index("--mute-audio") < args.index("https://example.com")


def test_browser_path_emits_no_url_by_default():
    # The async Browser passes url=None -> nothing appended.
    args, _ = _plan()
    assert not any(a.startswith("http") for a in args)


# --- conf helpers ---------------------------------------------------------

def test_cdp_mode_from_conf(tmp_path):
    p = tmp_path / "a.conf"
    p.write_text("# c\nplatform=Win32\ncdp_mode=isolated\n", encoding="utf-8")
    assert cdp_mode_from_conf(p) == "isolated"

    p.write_text("cdp_mode=bogus\n", encoding="utf-8")
    assert cdp_mode_from_conf(p) is None

    p.write_text("platform=Win32\n", encoding="utf-8")
    assert cdp_mode_from_conf(p) is None

    assert cdp_mode_from_conf(None) is None
    assert cdp_mode_from_conf(tmp_path / "missing.conf") is None


def test_read_conf_value(tmp_path):
    p = tmp_path / "a.conf"
    p.write_text("# h\nwebrtc_local_ipv4=5.6.7.8\nplatform=Win32\n", encoding="utf-8")
    assert read_conf_value(p, "webrtc_local_ipv4") == "5.6.7.8"
    assert read_conf_value(p, "platform") == "Win32"
    assert read_conf_value(p, "missing") is None


def test_update_conf_keys_replaces_and_appends_and_preserves(tmp_path):
    p = tmp_path / "a.conf"
    p.write_text(
        "# Huligan Profile\nplatform=Win32\ntimezone=UTC\n\n# tail comment\n",
        encoding="utf-8",
    )
    update_conf_keys(p, {"timezone": "Europe/Berlin", "languages": "de-DE,de"})
    text = p.read_text(encoding="utf-8")
    # Replaced in place.
    assert "timezone=Europe/Berlin" in text
    assert "timezone=UTC" not in text
    # Appended (was absent).
    assert "languages=de-DE,de" in text
    # Comments + untouched keys preserved.
    assert "# Huligan Profile" in text
    assert "# tail comment" in text
    assert "platform=Win32" in text


def test_update_conf_keys_noop_on_empty(tmp_path):
    p = tmp_path / "a.conf"
    p.write_text("platform=Win32\n", encoding="utf-8")
    update_conf_keys(p, {})
    assert p.read_text(encoding="utf-8") == "platform=Win32\n"


def test_find_free_port_returns_bindable_port():
    port = find_free_port()
    assert isinstance(port, int)
    assert 0 < port < 65536
