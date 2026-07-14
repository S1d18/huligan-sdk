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
  * ``find_chrome`` tracks ``HULIGAN_CHROME_CHANNEL``.
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
from huligan.version import CHROME_VERSION


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

    monkeypatch.setattr(installer, "resolve_version", lambda channel: (version, "sha"))
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

    _no_network(monkeypatch)  # pinned must not resolve via manifest
    resolved = chrome_mod.find_chrome()
    assert resolved == (vdir / "chrome.exe").resolve()
