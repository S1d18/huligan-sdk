"""Same-version rebuild: the .ok sha must be compared with the expected sha.

The ``.ok`` sentinel records the sha256 a build was verified against
(INST-CONC-01). If the release manifest now lists a DIFFERENT sha for the same
version, the build was republished; the SDK must reinstall it instead of
serving the old tree forever. Unknown shas (legacy sentinel, manifest offline)
and failed reinstalls keep the working cache.
"""
import hashlib
import json
import sys
import zipfile

import pytest

from huligan import __main__ as cli
from huligan import installer

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="installer ships win64 only")

VERSION = "153.0.8000.1"   # deliberately not baked into _KNOWN_SHA256
OLD_SHA = "a" * 64


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HULIGAN_CHROME_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("HULIGAN_RELEASES_REPO", raising=False)
    monkeypatch.delenv("HULIGAN_GH_TOKEN", raising=False)
    monkeypatch.delenv("HULIGAN_CHROME_CHANNEL", raising=False)
    monkeypatch.delenv("HULIGAN_CHROME", raising=False)
    assert VERSION not in installer._KNOWN_SHA256
    return tmp_path / "cache"


def _install_old(cache_dir, sha=OLD_SHA, legacy=False):
    d = cache_dir / VERSION
    d.mkdir(parents=True)
    (d / "chrome.exe").write_bytes(b"old-build")
    ok = cache_dir / f"{VERSION}.ok"
    ok.write_text(VERSION if legacy else json.dumps({"version": VERSION, "sha256": sha}))


def _rebuild(tmp_path, monkeypatch, manifest_ok=True):
    payload = tmp_path / "rebuild.zip"
    with zipfile.ZipFile(payload, "w") as zf:
        zf.writestr("chrome.exe", b"new-build")
    new_sha = hashlib.sha256(payload.read_bytes()).hexdigest()
    manifest = {"latest": VERSION, "versions": {VERSION: {"win64": {"sha256": new_sha}}}}

    def fetch(*a, **k):
        if not manifest_ok:
            raise OSError("offline")
        return manifest
    monkeypatch.setattr(installer, "_fetch_manifest", fetch)
    downloads = []

    def fake_download(url, dest, token=None, progress_callback=None):
        downloads.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload.read_bytes())
    monkeypatch.setattr(installer, "_download", fake_download)
    return new_sha, downloads


def test_republished_version_is_reinstalled(cache_dir, tmp_path, monkeypatch):
    _install_old(cache_dir)
    new_sha, downloads = _rebuild(tmp_path, monkeypatch)
    exe = installer.ensure_chrome(VERSION)
    assert downloads, "same-version rebuild was not downloaded"
    assert exe.read_bytes() == b"new-build"
    assert installer._installed_sha256(VERSION) == new_sha
    assert list(cache_dir.glob(f"{VERSION}.old-*")) == []
    # now current: the next call is a pure cache hit
    downloads.clear()
    installer.ensure_chrome(VERSION)
    assert downloads == []


def test_matching_sha_is_a_cache_hit(cache_dir, tmp_path, monkeypatch):
    new_sha, downloads = _rebuild(tmp_path, monkeypatch)
    _install_old(cache_dir, sha=new_sha.upper())
    installer.ensure_chrome(VERSION)
    assert downloads == []


def test_offline_keeps_cached_build(cache_dir, tmp_path, monkeypatch):
    _install_old(cache_dir)
    _new, downloads = _rebuild(tmp_path, monkeypatch, manifest_ok=False)
    exe = installer.ensure_chrome(VERSION)
    assert downloads == [] and exe.read_bytes() == b"old-build"


def test_legacy_sentinel_without_sha_is_kept(cache_dir, tmp_path, monkeypatch):
    _install_old(cache_dir, legacy=True)
    _new, downloads = _rebuild(tmp_path, monkeypatch)
    assert installer.ensure_chrome(VERSION).read_bytes() == b"old-build"
    assert downloads == []


def test_failed_reinstall_keeps_working_build(cache_dir, tmp_path, monkeypatch):
    _install_old(cache_dir)
    _rebuild(tmp_path, monkeypatch)

    def broken(*a, **k):
        raise OSError("connection reset")
    monkeypatch.setattr(installer, "_download", broken)
    exe = installer.ensure_chrome(VERSION)
    assert exe.read_bytes() == b"old-build"
    assert installer.is_installed(VERSION)
    assert installer._installed_sha256(VERSION) == OLD_SHA


def test_in_use_build_is_not_half_deleted(cache_dir, tmp_path, monkeypatch):
    """A running Chrome locks its tree: the swap must fail cleanly, not rmtree."""
    _install_old(cache_dir)
    _rebuild(tmp_path, monkeypatch)
    real_replace = installer.os.replace
    target = cache_dir / VERSION

    def locked_replace(src, dst):
        if str(src) == str(target):
            raise PermissionError("in use")
        return real_replace(src, dst)
    monkeypatch.setattr(installer.os, "replace", locked_replace)
    exe = installer.ensure_chrome(VERSION)
    assert exe.read_bytes() == b"old-build"
    assert installer.is_installed(VERSION)
    assert installer._installed_sha256(VERSION) == OLD_SHA


def test_find_chrome_reinstalls_republished_build(cache_dir, tmp_path, monkeypatch):
    from huligan import chrome as chrome_mod

    _install_old(cache_dir)
    _new, downloads = _rebuild(tmp_path, monkeypatch)
    installer.set_launch_selection(channel="latest")
    monkeypatch.chdir(tmp_path)
    exe = chrome_mod.find_chrome()
    assert downloads and exe.read_bytes() == b"new-build"


def test_cli_update_check_reports_republished_as_not_installed(cache_dir, tmp_path, monkeypatch, capsys):
    _install_old(cache_dir)
    _rebuild(tmp_path, monkeypatch)
    assert cli.main(["chrome", "update", "--channel", "latest", "--check"]) == 0
    assert "NOT installed" in capsys.readouterr().out
