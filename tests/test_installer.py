"""Unit tests for manifest-driven Chrome resolution (huligan.installer).

No real network and no real Chrome: ``urllib.request.urlopen`` and the
``_download`` streamer are monkeypatched, and the cache root is redirected to a
tmp dir via ``HULIGAN_CHROME_DIR``. What we verify:

  * ``pinned`` resolution is fully offline (never touches the manifest);
  * ``stable``/``latest`` resolve version + sha256 from the manifest, with the
    per-channel ``channels`` map preferred over the top-level ``latest``;
  * the manifest cache honours its TTL: fresh -> no network, expired -> refetch,
    offline+stale -> degrade to the stale copy;
  * ``ensure_chrome`` verifies the archive against the manifest sha (mismatch
    raises), so a build absent from ``_KNOWN_SHA256`` still installs safely;
  * ``find_chrome`` tracks ``HULIGAN_CHROME_CHANNEL``;
  * the .conf compatibility gate refuses builds newer than this SDK's schema.
"""

import hashlib
import json
import os
import sys
import time
import urllib.error
import zipfile

import pytest

from huligan import installer
from huligan.installer import IncompatibleBuildError
from huligan.conf_spec import CONF_SCHEMA_VERSION
from huligan.version import CHROME_VERSION

_TOO_NEW = CONF_SCHEMA_VERSION + 1  # a build this SDK cannot generate .conf for


# --- helpers --------------------------------------------------------------


class _FakeResp:
    """Minimal urlopen() context-manager stand-in returning fixed bytes."""

    def __init__(self, body: bytes):
        self._body = body
        self.headers = {}

    def read(self, *a):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _no_network(monkeypatch):
    """Make any urlopen call an assertion failure."""
    def boom(*a, **k):
        raise AssertionError("unexpected network access")
    monkeypatch.setattr(installer.urllib.request, "urlopen", boom)


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HULIGAN_CHROME_DIR", str(tmp_path))
    monkeypatch.delenv("HULIGAN_RELEASES_REPO", raising=False)
    monkeypatch.delenv("HULIGAN_GH_TOKEN", raising=False)
    return tmp_path


# --- pinned is offline ----------------------------------------------------


def test_pinned_resolution_never_hits_network(cache_dir, monkeypatch):
    _no_network(monkeypatch)
    version, sha = installer.resolve_version("pinned")
    assert version == CHROME_VERSION
    assert sha == installer._KNOWN_SHA256[CHROME_VERSION]


def test_default_channel_is_pinned(cache_dir, monkeypatch):
    _no_network(monkeypatch)
    assert installer.resolve_version() == (
        CHROME_VERSION, installer._KNOWN_SHA256[CHROME_VERSION]
    )


def test_explicit_known_version_is_offline(cache_dir, monkeypatch):
    _no_network(monkeypatch)
    known = next(iter(installer._KNOWN_SHA256))
    version, sha = installer._resolve_target(known, None)
    assert (version, sha) == (known, installer._KNOWN_SHA256[known])


# --- channel resolution from manifest -------------------------------------


def test_latest_channel_resolves_from_manifest(cache_dir, monkeypatch):
    manifest = {
        "latest": "151.0.1.2",
        "versions": {"151.0.1.2": {"win64": {"sha256": "deadbeef"}}},
    }
    monkeypatch.setattr(installer, "_fetch_manifest", lambda *a, **k: manifest)
    assert installer.resolve_version("latest") == ("151.0.1.2", "deadbeef")


def test_channels_map_preferred_over_latest(cache_dir, monkeypatch):
    manifest = {
        "latest": "151.0.1.2",
        "channels": {"stable": "150.9.9.9"},
        "versions": {
            "151.0.1.2": {"win64": {"sha256": "newsha"}},
            "150.9.9.9": {"win64": {"sha256": "stablesha"}},
        },
    }
    monkeypatch.setattr(installer, "_fetch_manifest", lambda *a, **k: manifest)
    assert installer.resolve_version("stable") == ("150.9.9.9", "stablesha")
    # a channel absent from the map still falls back to top-level latest
    assert installer.resolve_version("latest") == ("151.0.1.2", "newsha")


def test_channel_without_latest_or_map_raises(cache_dir, monkeypatch):
    monkeypatch.setattr(installer, "_fetch_manifest", lambda *a, **k: {"versions": {}})
    with pytest.raises(RuntimeError, match="no channel"):
        installer.resolve_version("latest")


def test_missing_sha_in_manifest_degrades_to_none(cache_dir, monkeypatch):
    manifest = {"latest": "151.0.1.2", "versions": {}}  # version metadata absent
    monkeypatch.setattr(installer, "_fetch_manifest", lambda *a, **k: manifest)
    version, sha = installer.resolve_version("latest")
    assert version == "151.0.1.2"
    assert sha is None


# --- manifest TTL cache ---------------------------------------------------


def test_fresh_cache_short_circuits_without_network(cache_dir, monkeypatch):
    cache = installer._manifest_cache_path()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"latest": "9"}), encoding="utf-8")
    _no_network(monkeypatch)  # would raise if touched
    assert installer._fetch_manifest()["latest"] == "9"


def test_expired_cache_refetches(cache_dir, monkeypatch):
    cache = installer._manifest_cache_path()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"latest": "old"}), encoding="utf-8")
    old = time.time() - installer._MANIFEST_TTL_SECONDS - 100
    os.utime(cache, (old, old))

    body = json.dumps({"latest": "new"}).encode()
    monkeypatch.setattr(
        installer.urllib.request, "urlopen", lambda *a, **k: _FakeResp(body)
    )
    data = installer._fetch_manifest()
    assert data["latest"] == "new"
    # cache was refreshed on disk
    assert json.loads(cache.read_text(encoding="utf-8"))["latest"] == "new"


def test_offline_falls_back_to_stale_cache(cache_dir, monkeypatch):
    cache = installer._manifest_cache_path()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"latest": "stale"}), encoding="utf-8")
    old = time.time() - installer._MANIFEST_TTL_SECONDS - 100
    os.utime(cache, (old, old))

    def offline(*a, **k):
        raise urllib.error.URLError("offline")
    monkeypatch.setattr(installer.urllib.request, "urlopen", offline)
    assert installer._fetch_manifest()["latest"] == "stale"


def test_no_cache_and_offline_raises(cache_dir, monkeypatch):
    def offline(*a, **k):
        raise urllib.error.URLError("offline")
    monkeypatch.setattr(installer.urllib.request, "urlopen", offline)
    with pytest.raises(urllib.error.URLError):
        installer._fetch_manifest()


# --- ensure_chrome end-to-end (mocked download) ---------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="installer ships win64 only")
def test_ensure_chrome_verifies_manifest_sha(cache_dir, monkeypatch):
    # A real zip carrying chrome.exe, whose sha we advertise via the manifest.
    payload = cache_dir / "build.zip"
    with zipfile.ZipFile(payload, "w") as zf:
        zf.writestr("chrome.exe", b"fake-binary")
    good_sha = hashlib.sha256(payload.read_bytes()).hexdigest()

    version = "151.0.7900.1"  # deliberately NOT in _KNOWN_SHA256
    assert version not in installer._KNOWN_SHA256
    manifest = {"latest": version, "versions": {version: {"win64": {"sha256": good_sha}}}}
    monkeypatch.setattr(installer, "_fetch_manifest", lambda *a, **k: manifest)

    def fake_download(url, dest, token=None, progress_callback=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload.read_bytes())
    monkeypatch.setattr(installer, "_download", fake_download)

    path = installer.ensure_chrome(channel="latest")
    assert path.name == "chrome.exe"
    assert path.read_bytes() == b"fake-binary"
    assert installer.is_installed(version)


@pytest.mark.skipif(sys.platform != "win32", reason="installer ships win64 only")
def test_ensure_chrome_rejects_bad_sha(cache_dir, monkeypatch):
    payload = cache_dir / "build.zip"
    with zipfile.ZipFile(payload, "w") as zf:
        zf.writestr("chrome.exe", b"fake-binary")

    version = "151.0.7900.2"
    manifest = {"latest": version, "versions": {version: {"win64": {"sha256": "0" * 64}}}}
    monkeypatch.setattr(installer, "_fetch_manifest", lambda *a, **k: manifest)

    def fake_download(url, dest, token=None, progress_callback=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload.read_bytes())
    monkeypatch.setattr(installer, "_download", fake_download)

    with pytest.raises(RuntimeError, match="SHA256 mismatch"):
        installer.ensure_chrome(channel="latest")
    assert not installer.is_installed(version)


# --- find_chrome channel awareness ----------------------------------------


def test_find_chrome_uses_channel_cache_hit(cache_dir, monkeypatch):
    from huligan import chrome as chrome_mod

    monkeypatch.setenv("HULIGAN_CHROME_CHANNEL", "latest")
    monkeypatch.delenv("HULIGAN_CHROME", raising=False)
    monkeypatch.chdir(cache_dir)  # no ./chrome.exe here

    version = "151.0.7900.3"
    vdir = cache_dir / version
    vdir.mkdir(parents=True)
    (vdir / "chrome.exe").write_text("x")
    (vdir.parent / f"{vdir.name}.ok").write_text(vdir.name)

    monkeypatch.setattr(installer, "resolve_launch_target", lambda: (version, "sha"))
    resolved = chrome_mod.find_chrome()
    assert resolved == (vdir / "chrome.exe").resolve()


def test_find_chrome_pinned_ignores_manifest(cache_dir, monkeypatch):
    from huligan import chrome as chrome_mod

    monkeypatch.setenv("HULIGAN_CHROME_CHANNEL", "pinned")
    monkeypatch.delenv("HULIGAN_CHROME", raising=False)
    monkeypatch.chdir(cache_dir)

    vdir = cache_dir / CHROME_VERSION
    vdir.mkdir(parents=True)
    (vdir / "chrome.exe").write_text("x")
    (vdir.parent / f"{vdir.name}.ok").write_text(vdir.name)

    _no_network(monkeypatch)  # pinned must not resolve via manifest
    resolved = chrome_mod.find_chrome()
    assert resolved == (vdir / "chrome.exe").resolve()


# --- .conf compatibility gate ---------------------------------------------


def test_channel_refuses_build_needing_newer_schema(cache_dir, monkeypatch):
    version = "160.0.0.1"
    manifest = {
        "latest": version,
        "versions": {version: {"min_conf_schema": _TOO_NEW,
                               "win64": {"sha256": "x"}}},
    }
    monkeypatch.setattr(installer, "_fetch_manifest", lambda *a, **k: manifest)
    with pytest.raises(IncompatibleBuildError, match="schema"):
        installer.resolve_version("latest")


def test_channel_accepts_build_at_current_schema(cache_dir, monkeypatch):
    version = "160.0.0.2"
    manifest = {
        "latest": version,
        "versions": {version: {"min_conf_schema": CONF_SCHEMA_VERSION,
                               "win64": {"sha256": "ok"}}},
    }
    monkeypatch.setattr(installer, "_fetch_manifest", lambda *a, **k: manifest)
    assert installer.resolve_version("latest") == (version, "ok")


def test_manifest_without_min_conf_schema_is_not_gated(cache_dir, monkeypatch):
    # Older manifests omit the field entirely -> must not gate (backward compat).
    version = "160.0.0.3"
    manifest = {"latest": version, "versions": {version: {"win64": {"sha256": "ok"}}}}
    monkeypatch.setattr(installer, "_fetch_manifest", lambda *a, **k: manifest)
    assert installer.resolve_version("latest") == (version, "ok")


def test_explicit_unknown_version_is_gated(cache_dir, monkeypatch):
    version = "160.0.0.4"
    assert version not in installer._KNOWN_SHA256
    manifest = {
        "versions": {version: {"min_conf_schema": _TOO_NEW,
                               "win64": {"sha256": "x"}}},
    }
    monkeypatch.setattr(installer, "_fetch_manifest", lambda *a, **k: manifest)
    with pytest.raises(IncompatibleBuildError):
        installer._resolve_target(version, None)


def test_known_version_bypasses_gate_offline(cache_dir, monkeypatch):
    # A build baked into this SDK is compatible by construction: resolve it with
    # no network even if a (hostile) manifest would claim it needs a newer schema.
    _no_network(monkeypatch)
    known = next(iter(installer._KNOWN_SHA256))
    version, sha = installer._resolve_target(known, None)
    assert (version, sha) == (known, installer._KNOWN_SHA256[known])


def test_pinned_is_never_gated(cache_dir, monkeypatch):
    _no_network(monkeypatch)  # pinned resolves offline, gate never consulted
    version, sha = installer.resolve_version("pinned")
    assert version == CHROME_VERSION


@pytest.mark.skipif(sys.platform != "win32", reason="installer ships win64 only")
def test_ensure_chrome_refuses_incompatible_before_download(cache_dir, monkeypatch):
    version = "160.0.0.5"
    manifest = {
        "latest": version,
        "versions": {version: {"min_conf_schema": _TOO_NEW,
                               "win64": {"sha256": "x"}}},
    }
    monkeypatch.setattr(installer, "_fetch_manifest", lambda *a, **k: manifest)

    def no_download(*a, **k):
        raise AssertionError("download attempted for an incompatible build")
    monkeypatch.setattr(installer, "_download", no_download)

    with pytest.raises(IncompatibleBuildError):
        installer.ensure_chrome(channel="latest")


def test_find_chrome_degrades_to_pinned_on_incompatible(cache_dir, monkeypatch):
    from huligan import chrome as chrome_mod

    monkeypatch.setenv("HULIGAN_CHROME_CHANNEL", "latest")
    monkeypatch.delenv("HULIGAN_CHROME", raising=False)
    monkeypatch.chdir(cache_dir)

    # pinned build is present in the cache as the safe fallback
    vdir = cache_dir / CHROME_VERSION
    vdir.mkdir(parents=True)
    (vdir / "chrome.exe").write_text("x")
    (vdir.parent / f"{vdir.name}.ok").write_text(vdir.name)

    def incompatible():
        raise IncompatibleBuildError("needs newer schema")
    monkeypatch.setattr(installer, "resolve_launch_target", incompatible)

    # must not raise — degrades to the pinned cached build
    resolved = chrome_mod.find_chrome()
    assert resolved == (vdir / "chrome.exe").resolve()


# --- SYS-04: never resolve a vanilla / half-extracted Chrome ---------------


def test_find_chrome_ignores_cwd_and_path(cache_dir, monkeypatch, tmp_path):
    from huligan import chrome as chrome_mod

    monkeypatch.setenv("HULIGAN_CHROME_CHANNEL", "pinned")
    monkeypatch.delenv("HULIGAN_CHROME", raising=False)
    stock = tmp_path / "stock"
    stock.mkdir()
    (stock / "chrome.exe").write_text("stock")
    monkeypatch.chdir(stock)                       # ./chrome.exe is stock
    monkeypatch.setenv("PATH", str(stock))         # so is chrome on PATH
    _no_network(monkeypatch)

    with pytest.raises(FileNotFoundError):
        chrome_mod.find_chrome(auto_install=False)


def test_find_chrome_rejects_cache_without_ok_marker(cache_dir, monkeypatch):
    from huligan import chrome as chrome_mod

    monkeypatch.setenv("HULIGAN_CHROME_CHANNEL", "pinned")
    monkeypatch.delenv("HULIGAN_CHROME", raising=False)
    monkeypatch.chdir(cache_dir)
    vdir = cache_dir / CHROME_VERSION
    vdir.mkdir(parents=True)
    (vdir / "chrome.exe").write_text("x")          # interrupted extraction: no .ok
    _no_network(monkeypatch)

    with pytest.raises(FileNotFoundError):
        chrome_mod.find_chrome(auto_install=False)


# --- SEC-03: never extract an archive we cannot verify ---------------------


def _zip_with_chrome(cache_dir):
    payload = cache_dir / "build.zip"
    with zipfile.ZipFile(payload, "w") as zf:
        zf.writestr("chrome.exe", b"unverified-binary")
    return payload


@pytest.mark.skipif(sys.platform != "win32", reason="installer ships win64 only")
def test_ensure_chrome_refuses_version_missing_from_manifest(cache_dir, monkeypatch):
    payload = _zip_with_chrome(cache_dir)
    version = "151.0.7900.3"
    assert version not in installer._KNOWN_SHA256
    manifest = {"latest": version, "versions": {}}   # no sha for this build
    monkeypatch.setattr(installer, "_fetch_manifest", lambda *a, **k: manifest)
    downloads = []

    def fake_download(url, dest, token=None, progress_callback=None):
        downloads.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload.read_bytes())
    monkeypatch.setattr(installer, "_download", fake_download)

    with pytest.raises(RuntimeError, match="sha256"):
        installer.ensure_chrome(channel="latest")
    assert downloads == []
    assert not installer.is_installed(version)
    assert not (cache_dir / version).exists()


@pytest.mark.skipif(sys.platform != "win32", reason="installer ships win64 only")
def test_ensure_chrome_refuses_unknown_version_when_manifest_offline(cache_dir, monkeypatch):
    payload = _zip_with_chrome(cache_dir)
    version = "151.0.7900.4"

    def offline(*a, **k):
        raise urllib.error.URLError("offline")
    monkeypatch.setattr(installer, "_fetch_manifest", offline)
    downloads = []

    def fake_download(url, dest, token=None, progress_callback=None):
        downloads.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload.read_bytes())
    monkeypatch.setattr(installer, "_download", fake_download)

    with pytest.raises(RuntimeError, match="sha256"):
        installer.ensure_chrome(version)
    assert downloads == []
    assert not installer.is_installed(version)


# --- INST-CONC-01: locked, staged, atomic install --------------------------


def _manifest_for(payload, version):
    sha = hashlib.sha256(payload.read_bytes()).hexdigest()
    return sha, {"latest": version, "versions": {version: {"win64": {"sha256": sha}}}}


@pytest.mark.skipif(sys.platform != "win32", reason="installer ships win64 only")
def test_concurrent_installs_of_one_version_download_once(cache_dir, monkeypatch):
    import threading

    payload = _zip_with_chrome(cache_dir)
    version = "151.0.7900.5"
    _sha, manifest = _manifest_for(payload, version)
    monkeypatch.setattr(installer, "_fetch_manifest", lambda *a, **k: manifest)
    downloads = []

    def slow_download(url, dest, token=None, progress_callback=None):
        downloads.append(url)
        time.sleep(0.5)        # hold the window open for the other installer
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload.read_bytes())
    monkeypatch.setattr(installer, "_download", slow_download)

    results, errors = [], []

    def worker():
        try:
            results.append(installer.ensure_chrome(version))
        except Exception as e:  # pragma: no cover - reported below
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert errors == []
    assert len(results) == 3 and len(set(results)) == 1
    assert len(downloads) == 1
    assert installer.is_installed(version)
    assert not list(cache_dir.glob(f"{version}.tmp-*"))


@pytest.mark.skipif(sys.platform != "win32", reason="installer ships win64 only")
def test_interrupted_repair_is_not_reported_installed(cache_dir, monkeypatch):
    payload = _zip_with_chrome(cache_dir)
    version = "151.0.7900.6"
    _sha, manifest = _manifest_for(payload, version)
    monkeypatch.setattr(installer, "_fetch_manifest", lambda *a, **k: manifest)

    def fake_download(url, dest, token=None, progress_callback=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload.read_bytes())
    monkeypatch.setattr(installer, "_download", fake_download)

    # A damaged install: the .ok survived but chrome.exe is gone -> repair.
    vdir = cache_dir / version
    vdir.mkdir()
    (vdir / "old.dll").write_text("old")
    (cache_dir / f"{version}.ok").write_text(version)

    # The repair's extraction dies half-way, after chrome.exe hit the disk.
    def crash_midway(self, path=None, members=None, pwd=None):
        from pathlib import Path as _P
        _P(path, "chrome.exe").write_bytes(b"half")
        raise OSError("disk full")
    monkeypatch.setattr(installer.zipfile.ZipFile, "extractall", crash_midway)

    with pytest.raises(OSError, match="disk full"):
        installer.ensure_chrome(version)
    assert not installer.is_installed(version)
    assert version not in installer.installed_versions()
    assert not list(cache_dir.glob(f"{version}.tmp-*"))


@pytest.mark.skipif(sys.platform != "win32", reason="installer ships win64 only")
def test_repair_replaces_dir_atomically_and_records_sha(cache_dir, monkeypatch):
    payload = _zip_with_chrome(cache_dir)
    version = "151.0.7900.7"
    sha, manifest = _manifest_for(payload, version)
    monkeypatch.setattr(installer, "_fetch_manifest", lambda *a, **k: manifest)

    def fake_download(url, dest, token=None, progress_callback=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload.read_bytes())
    monkeypatch.setattr(installer, "_download", fake_download)

    vdir = cache_dir / version
    vdir.mkdir()
    (vdir / "stale.dll").write_text("old")          # no chrome.exe -> reinstall
    path = installer.ensure_chrome(version)
    assert path.read_bytes() == b"unverified-binary"
    assert not (vdir / "stale.dll").exists()         # old tree fully replaced
    assert sha in (cache_dir / f"{version}.ok").read_text()
    assert installer._installed_sha256(version) == sha


def test_legacy_ok_sentinel_still_counts_as_installed(cache_dir):
    version = "150.0.7871.101"
    (cache_dir / version).mkdir()
    (cache_dir / version / "chrome.exe").write_text("x")
    (cache_dir / f"{version}.ok").write_text(version)   # old format: version only
    assert installer.is_installed(version)
    assert installer.installed_versions() == [version]
    assert installer._installed_sha256(version) is None


def test_install_lock_is_exclusive_across_handles(cache_dir):
    import threading

    order = []
    with installer._install_lock(cache_dir, "150.0.7871.101"):
        def other():
            with installer._install_lock(cache_dir, "150.0.7871.101", poll=0.05):
                order.append("second")
        t = threading.Thread(target=other)
        t.start()
        time.sleep(0.3)
        order.append("first-release")
    t.join(5)
    assert order == ["first-release", "second"]


def test_install_lock_times_out(cache_dir):
    import threading

    with installer._install_lock(cache_dir, "150.0.7871.101"):
        errs = []

        def other():
            try:
                with installer._install_lock(cache_dir, "150.0.7871.101", timeout=0.3, poll=0.05):
                    pass
            except TimeoutError as e:
                errs.append(e)
        t = threading.Thread(target=other)
        t.start()
        t.join(5)
    assert errs
