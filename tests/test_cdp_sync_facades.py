"""Tests for the synchronous CDP facades (cookies + profile_bundle).

The async originals (Playwright over CDP) are monkeypatched with trivial
coroutines, so we verify the worker-thread event-loop wrapper returns the right
value/type, propagates exceptions, and leaves no thread behind.
"""

import threading
import time
from pathlib import Path

import pytest

from huligan import cookies
from huligan import profile_bundle as pb


def test_export_cookies_sync_returns_count_no_leak(monkeypatch):
    async def fake_export(cdp_port, path, **kw):
        assert cdp_port == 9222
        assert kw.get("domains") == ["a.com"]
        return 7

    monkeypatch.setattr(cookies, "export_cookies_to_file", fake_export)

    before = threading.active_count()
    n = cookies.export_cookies_to_file_sync(9222, "x.json", domains=["a.com"])
    assert n == 7
    time.sleep(0.2)
    assert threading.active_count() <= before   # worker thread joined, no leak


def test_import_cookies_sync_returns_count(monkeypatch):
    async def fake_import(cdp_port, path, **kw):
        assert kw.get("clear_existing") is True
        return 3

    monkeypatch.setattr(cookies, "import_cookies_from_file", fake_import)
    assert cookies.import_cookies_from_file_sync(9222, "x.json", clear_existing=True) == 3


def test_sync_facade_propagates_exception(monkeypatch):
    async def boom(cdp_port, path, **kw):
        raise RuntimeError("cdp down")

    monkeypatch.setattr(cookies, "export_cookies_to_file", boom)
    with pytest.raises(RuntimeError, match="cdp down"):
        cookies.export_cookies_to_file_sync(9222, "x.json")


def test_export_bundle_sync_returns_path(monkeypatch, tmp_path):
    captured = {}

    async def fake_bundle(cdp_port, path, *, conf_path, name=None, **kw):
        captured["conf_path"] = conf_path
        captured["name"] = name
        return 5  # cookie count (discarded by the sync facade)

    monkeypatch.setattr(pb, "export_profile_bundle_to_file", fake_bundle)

    out = tmp_path / "acc.hbundle"
    res = pb.export_profile_bundle_to_file_sync(9222, out, conf_path="acc.conf", name="acc")
    assert isinstance(res, Path)
    assert res == Path(out)
    assert captured["conf_path"] == "acc.conf"
    assert captured["name"] == "acc"
