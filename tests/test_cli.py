"""Unit tests for the huligan CLI (huligan.__main__) and config/prune helpers.

No network, no real Chrome: the manifest fetch is monkeypatched and the cache
root is redirected to a tmp dir via HULIGAN_CHROME_DIR. Cached "builds" are just
directories with a chrome.exe file + .ok sentinel.
"""

import json

import pytest

from huligan import __main__ as cli
from huligan import installer
from huligan.version import CHROME_VERSION


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HULIGAN_CHROME_DIR", str(tmp_path))
    monkeypatch.delenv("HULIGAN_CHROME_CHANNEL", raising=False)
    monkeypatch.delenv("HULIGAN_GH_TOKEN", raising=False)
    return tmp_path


def _install_fake(cache_dir, version):
    d = cache_dir / version
    d.mkdir(parents=True, exist_ok=True)
    (d / "chrome.exe").write_text("x")
    (cache_dir / f"{version}.ok").write_text(version)


# --- config + resolution --------------------------------------------------

def test_config_roundtrip(cache_dir):
    installer._save_config({"channel": "latest", "pinned_version": "1.2.3.4"})
    assert installer._load_config() == {"channel": "latest", "pinned_version": "1.2.3.4"}


def test_effective_channel_precedence(cache_dir, monkeypatch):
    # default
    assert installer.effective_channel() == ("pinned", "default")
    # config
    installer._save_config({"channel": "stable"})
    assert installer.effective_channel() == ("stable", "config")
    # env overrides config
    monkeypatch.setenv("HULIGAN_CHROME_CHANNEL", "latest")
    assert installer.effective_channel() == ("latest", "env")


def test_resolve_launch_target_config_pin_offline(cache_dir, monkeypatch):
    # An exact config pin of a baked-in version resolves with no network.
    known = next(iter(installer._KNOWN_SHA256))
    installer._save_config({"channel": "pinned", "pinned_version": known})

    def boom(*a, **k):
        raise AssertionError("network")
    monkeypatch.setattr(installer.urllib.request, "urlopen", boom)

    assert installer.resolve_launch_target() == (known, installer._KNOWN_SHA256[known])


def test_env_channel_ignores_config_pin(cache_dir, monkeypatch):
    installer._save_config({"channel": "pinned", "pinned_version": "9.9.9.9"})
    monkeypatch.setenv("HULIGAN_CHROME_CHANNEL", "pinned")
    # env "pinned" carries no exact version -> falls back to CHROME_VERSION
    version, _ = installer.resolve_launch_target()
    assert version == CHROME_VERSION


def test_installed_versions_sorted_newest_first(cache_dir):
    _install_fake(cache_dir, "149.0.7827.54")
    _install_fake(cache_dir, "150.0.7871.101")
    _install_fake(cache_dir, "148.0.7778.97")
    # a half-installed dir (no sentinel) is ignored
    (cache_dir / "151.0.0.0").mkdir()
    (cache_dir / "151.0.0.0" / "chrome.exe").write_text("x")
    assert installer.installed_versions() == [
        "150.0.7871.101", "149.0.7827.54", "148.0.7778.97"
    ]


# --- CLI: pin -------------------------------------------------------------

def test_cli_pin_writes_config(cache_dir, capsys):
    assert cli.main(["chrome", "pin", "150.0.7871.101"]) == 0
    cfg = installer._load_config()
    assert cfg["channel"] == "pinned"
    assert cfg["pinned_version"] == "150.0.7871.101"


def test_cli_pin_clear_removes_config(cache_dir, capsys):
    installer._save_config({"channel": "pinned", "pinned_version": "1.2.3.4"})
    assert cli.main(["chrome", "pin", "--clear"]) == 0
    cfg = installer._load_config()
    assert "pinned_version" not in cfg
    assert "channel" not in cfg


# --- CLI: update ----------------------------------------------------------

def test_cli_update_check_reports_without_download(cache_dir, monkeypatch, capsys):
    version = "150.0.7871.101"
    manifest = {"latest": version,
                "versions": {version: {"min_conf_schema": 1, "win64": {"sha256": "s"}}}}
    monkeypatch.setattr(installer, "_fetch_manifest", lambda *a, **k: manifest)

    def no_download(*a, **k):
        raise AssertionError("download during --check")
    monkeypatch.setattr(installer, "_download", no_download)

    rc = cli.main(["chrome", "update", "--channel", "latest", "--check"])
    assert rc == 0
    out = capsys.readouterr().out
    assert version in out
    # --check must NOT persist the channel
    assert installer._load_config() == {}


def test_cli_update_switches_channel_and_skips_if_installed(cache_dir, monkeypatch, capsys):
    version = "150.0.7871.101"
    _install_fake(cache_dir, version)
    manifest = {"latest": version,
                "versions": {version: {"min_conf_schema": 1, "win64": {"sha256": "s"}}}}
    monkeypatch.setattr(installer, "_fetch_manifest", lambda *a, **k: manifest)

    rc = cli.main(["chrome", "update", "--channel", "latest"])
    assert rc == 0
    assert installer._load_config()["channel"] == "latest"
    assert "already installed" in capsys.readouterr().out


def test_cli_update_refuses_incompatible(cache_dir, monkeypatch, capsys):
    version = "160.0.0.1"
    manifest = {"latest": version,
                "versions": {version: {"min_conf_schema": 999, "win64": {"sha256": "s"}}}}
    monkeypatch.setattr(installer, "_fetch_manifest", lambda *a, **k: manifest)
    rc = cli.main(["chrome", "update", "--channel", "latest", "--check"])
    assert rc == 2  # IncompatibleBuildError path


# --- CLI: prune -----------------------------------------------------------

def test_cli_prune_keeps_recent_and_protects_pinned(cache_dir, monkeypatch, capsys):
    for v in ["147.0.7727.56", "148.0.7778.97", "149.0.7827.54", CHROME_VERSION]:
        _install_fake(cache_dir, v)
    # offline: resolve_launch_target -> pinned CHROME_VERSION (protected anyway)
    monkeypatch.setattr(installer.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(OSError()))

    rc = cli.main(["chrome", "prune", "--keep", "1"])
    assert rc == 0
    remaining = set(installer.installed_versions())
    # CHROME_VERSION always protected; --keep 1 keeps one more recent build (149)
    assert CHROME_VERSION in remaining
    assert "149.0.7827.54" in remaining
    assert "147.0.7727.56" not in remaining


def test_cli_prune_nothing_to_do(cache_dir, capsys):
    _install_fake(cache_dir, CHROME_VERSION)
    rc = cli.main(["chrome", "prune", "--keep", "2"])
    assert rc == 0
    assert "Nothing to prune" in capsys.readouterr().out


# --- CLI: list / version smoke -------------------------------------------

def test_cli_list_runs(cache_dir, monkeypatch, capsys):
    _install_fake(cache_dir, CHROME_VERSION)
    monkeypatch.setattr(installer, "_safe_fetch_manifest",
                        lambda *a, **k: {"latest": CHROME_VERSION,
                                         "versions": {CHROME_VERSION: {}}})
    assert cli.main(["chrome", "list"]) == 0
    out = capsys.readouterr().out
    assert CHROME_VERSION in out
    assert "schema" in out.lower()


def test_cli_version_runs(cache_dir, capsys):
    assert cli.main(["version"]) == 0
    assert "Chrome" in capsys.readouterr().out
