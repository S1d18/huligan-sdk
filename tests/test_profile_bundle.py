"""Tests for portable profile bundles (huligan.profile_bundle).

Pure zip round-trips need no browser. The page-level export/import are exercised
with a fake Playwright page whose CDP session records/serves cookie calls.
"""

import asyncio
import json
import zipfile

import pytest

from huligan import profile_bundle as pb
from huligan import cookies


CONF_TEXT = "# Huligan\nplatform=Win32\ncanvas_noise_seed=12345\n"
FAKE_COOKIES = [
    {"name": "sid", "value": "abc", "domain": ".facebook.com", "path": "/",
     "secure": True, "httpOnly": True, "expires": 1893456000},
    {"name": "csrf", "value": "xyz", "domain": ".facebook.com", "path": "/",
     "size": 99, "session": True, "expires": -1},  # read-only extras + session
]


# --- fake CDP page --------------------------------------------------------

class _FakeCDP:
    def __init__(self, cookies_to_return):
        self._cookies = cookies_to_return
        self.set_calls = []
        self.cleared = False
        self.detached = False

    async def send(self, method, params=None):
        if method == "Storage.getCookies":
            return {"cookies": self._cookies}
        if method == "Network.clearBrowserCookies":
            self.cleared = True
            return {}
        if method == "Network.setCookies":
            self.set_calls.append(params["cookies"])
            return {}
        raise AssertionError(f"unexpected CDP method {method}")

    async def detach(self):
        self.detached = True


class _FakeContext:
    def __init__(self, cdp):
        self._cdp = cdp

    async def new_cdp_session(self, page):
        return self._cdp


class _FakePage:
    def __init__(self, cdp):
        self.context = _FakeContext(cdp)


# --- pure zip round-trip --------------------------------------------------

def test_write_read_roundtrip(tmp_path):
    bundle = {"schema": "huligan-cookies/1", "cookies": FAKE_COOKIES}
    path = tmp_path / "acc.hbundle"
    pb.write_profile_bundle(path, conf_text=CONF_TEXT, cookie_bundle=bundle, name="acc")

    # it's a real zip with the expected members
    with zipfile.ZipFile(path) as z:
        assert set(z.namelist()) == {"profile.conf", "cookies.json", "bundle.json"}

    data = pb.read_profile_bundle(path)
    assert data["conf_text"] == CONF_TEXT
    assert data["cookie_bundle"]["cookies"] == FAKE_COOKIES
    assert data["meta"]["name"] == "acc"
    assert data["meta"]["cookie_count"] == 2
    assert data["meta"]["has_cookies"] is True


def test_write_without_cookies(tmp_path):
    path = tmp_path / "id-only.hbundle"
    pb.write_profile_bundle(path, conf_text=CONF_TEXT)
    with zipfile.ZipFile(path) as z:
        assert "cookies.json" not in z.namelist()
    data = pb.read_profile_bundle(path)
    assert data["cookie_bundle"] is None
    assert data["meta"]["has_cookies"] is False
    assert pb.bundle_cookies(path) == []


def test_extract_writes_conf_and_cookies(tmp_path):
    bundle = {"schema": "huligan-cookies/1", "cookies": FAKE_COOKIES}
    path = tmp_path / "acc.hbundle"
    pb.write_profile_bundle(path, conf_text=CONF_TEXT, cookie_bundle=bundle, name="acc")

    conf_out = tmp_path / "out" / "acc.conf"
    cookies_out = tmp_path / "out" / "acc.cookies.json"
    info = pb.extract_profile_bundle(path, conf_out, cookies_out=cookies_out)

    assert conf_out.read_text(encoding="utf-8") == CONF_TEXT
    assert info["conf_path"] == str(conf_out)
    assert info["cookies_path"] == str(cookies_out)
    assert json.loads(cookies_out.read_text(encoding="utf-8"))["cookies"] == FAKE_COOKIES


def test_read_rejects_non_bundle(tmp_path):
    bogus = tmp_path / "bogus.zip"
    with zipfile.ZipFile(bogus, "w") as z:
        z.writestr("random.txt", "nope")
    with pytest.raises(ValueError, match="not a huligan profile bundle"):
        pb.read_profile_bundle(bogus)


# --- page-level export/import (fake CDP) ----------------------------------

def test_export_from_page_embeds_conf_and_cookies(tmp_path):
    conf = tmp_path / "acc.conf"
    conf.write_text(CONF_TEXT, encoding="utf-8")
    page = _FakePage(_FakeCDP(FAKE_COOKIES))
    out = tmp_path / "acc.hbundle"

    n = asyncio.run(pb.export_profile_bundle_from_page(page, out, conf_path=conf))
    assert n == 2
    data = pb.read_profile_bundle(out)
    assert data["conf_text"] == CONF_TEXT
    assert data["meta"]["name"] == "acc"           # defaults to conf stem
    assert len(data["cookie_bundle"]["cookies"]) == 2


def test_export_domain_filter(tmp_path):
    conf = tmp_path / "acc.conf"
    conf.write_text(CONF_TEXT, encoding="utf-8")
    mixed = FAKE_COOKIES + [{"name": "x", "value": "1", "domain": ".google.com"}]
    page = _FakePage(_FakeCDP(mixed))
    out = tmp_path / "acc.hbundle"

    asyncio.run(pb.export_profile_bundle_from_page(
        page, out, conf_path=conf, domains=["facebook.com"]))
    doms = {c["domain"] for c in pb.bundle_cookies(out)}
    assert doms == {".facebook.com"}


def test_import_cookies_to_page_projects_and_sets(tmp_path):
    bundle = {"schema": "huligan-cookies/1", "cookies": FAKE_COOKIES}
    path = tmp_path / "acc.hbundle"
    pb.write_profile_bundle(path, conf_text=CONF_TEXT, cookie_bundle=bundle)

    cdp = _FakeCDP([])
    page = _FakePage(cdp)
    n = asyncio.run(pb.import_profile_cookies_to_page(page, path, clear_existing=True))

    assert n == 2
    assert cdp.cleared is True
    sent = cdp.set_calls[0]
    # read-only fields stripped; the session cookie's expires==-1 dropped
    assert all("size" not in c and "session" not in c for c in sent)
    csrf = next(c for c in sent if c["name"] == "csrf")
    assert "expires" not in csrf


def test_import_no_cookies_is_noop(tmp_path):
    path = tmp_path / "id-only.hbundle"
    pb.write_profile_bundle(path, conf_text=CONF_TEXT)  # no cookies
    cdp = _FakeCDP([])
    page = _FakePage(cdp)
    n = asyncio.run(pb.import_profile_cookies_to_page(page, path))
    assert n == 0
    assert cdp.set_calls == []


# --- BUNDLE-LIMIT-01: untrusted bundle budgets ------------------------------

def _zip(path, members):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members:
            z.writestr(name, data)
    return path


def _no_decompress(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("member decompressed before the budget check")
    monkeypatch.setattr(zipfile.ZipFile, "open", boom)
    monkeypatch.setattr(zipfile.ZipFile, "read", boom)


@pytest.mark.parametrize("name,size", [
    ("profile.conf", pb.MAX_CONF_BYTES + 1),
    ("cookies.json", pb.MAX_COOKIES_BYTES + 1),
    ("bundle.json", pb.MAX_META_BYTES + 1),
])
def test_oversized_member_rejected_before_decompression(tmp_path, monkeypatch, name, size):
    members = [("profile.conf", CONF_TEXT)] if name != "profile.conf" else []
    members.append((name, b"0" * size))        # compresses to a few KiB: a bomb
    bomb = _zip(tmp_path / "bomb.hbundle", members)
    _no_decompress(monkeypatch)
    with pytest.raises(pb.ProfileBundleError, match="limit"):
        pb.read_profile_bundle(bomb)


def test_unexpected_member_rejected(tmp_path):
    b = _zip(tmp_path / "x.hbundle", [("profile.conf", CONF_TEXT), ("evil.exe", "MZ")])
    with pytest.raises(pb.ProfileBundleError, match="unexpected"):
        pb.read_profile_bundle(b)


def test_too_many_members_rejected(tmp_path, monkeypatch):
    b = tmp_path / "many.hbundle"
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")        # duplicate-name warning
        _zip(b, [("profile.conf", CONF_TEXT)] * 5)
    _no_decompress(monkeypatch)
    with pytest.raises(pb.ProfileBundleError, match="at most"):
        pb.read_profile_bundle(b)


def test_non_zip_is_bundle_error(tmp_path):
    f = tmp_path / "not.hbundle"
    f.write_bytes(b"definitely not a zip")
    with pytest.raises(pb.ProfileBundleError):
        pb.read_profile_bundle(f)


def test_bundle_error_is_value_error_and_exported():
    import huligan
    assert issubclass(pb.ProfileBundleError, ValueError)
    assert huligan.ProfileBundleError is pb.ProfileBundleError


def test_within_budget_bundle_still_reads(tmp_path):
    p = pb.write_profile_bundle(tmp_path / "ok.hbundle", conf_text=CONF_TEXT,
                                cookie_bundle={"cookies": FAKE_COOKIES}, name="acc")
    data = pb.read_profile_bundle(p)
    assert data["conf_text"] == CONF_TEXT and data["meta"]["name"] == "acc"


def test_lying_size_header_is_bundle_error(tmp_path):
    """Declared file_size understated: zipfile stops at it and the CRC fails."""
    b = _zip(tmp_path / "liar.hbundle", [("profile.conf", CONF_TEXT),
                                         ("cookies.json", b"[" + b" " * 100000 + b"]")])
    raw = bytearray(b.read_bytes())
    # Patch the uncompressed size of cookies.json in both headers to 2 bytes.
    with zipfile.ZipFile(b) as z:
        info = z.getinfo("cookies.json")
    real = info.file_size.to_bytes(4, "little")
    assert raw.count(real) >= 2
    raw = raw.replace(real, (2).to_bytes(4, "little"))
    b.write_bytes(bytes(raw))
    with pytest.raises(pb.ProfileBundleError):
        pb.read_profile_bundle(b)
