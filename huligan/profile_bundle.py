"""Portable profile bundle: fingerprint (.conf) + cookies in one file.

A ``.hbundle`` is a plain zip carrying:

    profile.conf   the fingerprint identity (read by Chrome at launch)
    cookies.json   the login (huligan-cookies/1 schema), optional
    bundle.json    metadata (schema, timestamp, chrome version, name, count)

Why a bundle and not just a copied ``user_data_dir``: the fingerprint is applied
at LAUNCH (Chrome reads ``HULIGAN_CONFIG_PATH`` on startup), while cookies are
restored into a RUNNING context over CDP. So import is inherently two-phase:

    1. extract_profile_bundle(path, conf_out="acc.conf")   # before launch
    2. Browser(profile_path="acc.conf") -> import cookies   # after launch

Copying a whole ``user_data_dir`` across machines is fragile (absolute paths,
lock files, machine-bound state); a bundle is the portable unit.
"""

from __future__ import annotations

import datetime
import json
import zipfile
from pathlib import Path
from typing import Optional, Sequence

from .version import CHROME_VERSION

SCHEMA = "huligan-profile/1"
_CONF_NAME = "profile.conf"
_COOKIES_NAME = "cookies.json"
_META_NAME = "bundle.json"

# Budgets for reading an untrusted bundle (BUNDLE-LIMIT-01). Checked against the
# declared ZipInfo.file_size BEFORE anything is decompressed, and enforced again
# while reading (zipfile stops at the declared size and CRC-checks it). A real
# .conf is a few KiB and a heavy cookie jar a few MiB; these leave ample margin
# while keeping a zip bomb from ballooning memory.
MAX_CONF_BYTES = 256 * 1024
MAX_COOKIES_BYTES = 32 * 1024 * 1024
MAX_META_BYTES = 64 * 1024
MAX_MEMBERS = 3
_MEMBER_LIMITS = {
    _CONF_NAME: MAX_CONF_BYTES,
    _COOKIES_NAME: MAX_COOKIES_BYTES,
    _META_NAME: MAX_META_BYTES,
}


class ProfileBundleError(ValueError):
    """The file is not a well-formed, within-budget huligan profile bundle."""


def _read_member(z: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    limit = _MEMBER_LIMITS[info.filename]
    if info.file_size > limit:
        raise ProfileBundleError(
            f"bundle member {info.filename} is {info.file_size} bytes "
            f"(limit {limit})")
    try:
        with z.open(info) as fh:
            data = fh.read(limit + 1)
    except zipfile.BadZipFile as e:   # e.g. CRC / size header that lies
        raise ProfileBundleError(f"bundle member {info.filename} is corrupt ({e})") from e
    if len(data) > limit:
        raise ProfileBundleError(f"bundle member {info.filename} exceeds {limit} bytes")
    return data


# --- pure (no browser) ----------------------------------------------------

def write_profile_bundle(
    path,
    *,
    conf_text: str,
    cookie_bundle: Optional[dict] = None,
    name: Optional[str] = None,
) -> Path:
    """Write a bundle from raw parts. ``cookie_bundle`` is a huligan-cookies dict."""
    cookies = (cookie_bundle or {}).get("cookies", []) if cookie_bundle else []
    meta = {
        "schema": SCHEMA,
        "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "chrome_version": CHROME_VERSION,
        "name": name,
        "has_cookies": bool(cookies),
        "cookie_count": len(cookies),
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(_CONF_NAME, conf_text)
        if cookie_bundle is not None:
            z.writestr(_COOKIES_NAME, json.dumps(cookie_bundle, indent=2, ensure_ascii=False))
        z.writestr(_META_NAME, json.dumps(meta, indent=2, ensure_ascii=False))
    return p


def read_profile_bundle(path) -> dict:
    """Read a bundle into ``{conf_text, cookie_bundle, meta}`` (no extraction).

    The bundle is untrusted input: raises :class:`ProfileBundleError` (a
    ``ValueError``) for a non-zip file, a missing ``profile.conf``, more than
    ``MAX_MEMBERS`` entries, duplicate or unexpected entries, or a member over
    its size budget (``MAX_CONF_BYTES`` / ``MAX_COOKIES_BYTES`` /
    ``MAX_META_BYTES``) - all checked before decompressing anything.
    """
    try:
        z = zipfile.ZipFile(Path(path))
    except zipfile.BadZipFile as e:
        raise ProfileBundleError(f"{path} is not a huligan profile bundle ({e})") from e
    with z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        if _CONF_NAME not in names:
            raise ProfileBundleError(
                f"{path} is not a huligan profile bundle (no {_CONF_NAME})")
        if len(infos) > MAX_MEMBERS:
            raise ProfileBundleError(
                f"{path}: {len(infos)} entries, a profile bundle has at most {MAX_MEMBERS}")
        unexpected = sorted(set(names) - set(_MEMBER_LIMITS))
        if unexpected:
            raise ProfileBundleError(f"{path}: unexpected bundle entries {unexpected}")
        if len(set(names)) != len(names):
            raise ProfileBundleError(f"{path}: duplicate bundle entries")
        by_name = {i.filename: i for i in infos}
        for info in infos:                       # budget check before any read
            if info.file_size > _MEMBER_LIMITS[info.filename]:
                raise ProfileBundleError(
                    f"bundle member {info.filename} is {info.file_size} bytes "
                    f"(limit {_MEMBER_LIMITS[info.filename]})")
        conf_text = _read_member(z, by_name[_CONF_NAME]).decode("utf-8")
        cookie_bundle = (
            json.loads(_read_member(z, by_name[_COOKIES_NAME]).decode("utf-8"))
            if _COOKIES_NAME in by_name else None
        )
        meta = (json.loads(_read_member(z, by_name[_META_NAME]).decode("utf-8"))
                if _META_NAME in by_name else {})
    return {"conf_text": conf_text, "cookie_bundle": cookie_bundle, "meta": meta}


def extract_profile_bundle(path, conf_out, *, cookies_out=None) -> dict:
    """Unpack the fingerprint (and optionally cookies) to files before launch.

    Writes the ``.conf`` to ``conf_out`` so it can drive ``Browser(profile_path=...)``.
    Returns the bundle metadata plus ``conf_path`` (and ``cookies_path`` if written).
    """
    data = read_profile_bundle(path)
    conf_path = Path(conf_out)
    conf_path.parent.mkdir(parents=True, exist_ok=True)
    conf_path.write_text(data["conf_text"], encoding="utf-8")

    info = {**data["meta"], "conf_path": str(conf_path)}
    if cookies_out and data["cookie_bundle"] is not None:
        cp = Path(cookies_out)
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text(
            json.dumps(data["cookie_bundle"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        info["cookies_path"] = str(cp)
    return info


def bundle_cookies(path) -> list:
    """The cookie list inside a bundle (empty if the bundle carries none)."""
    cb = read_profile_bundle(path)["cookie_bundle"]
    return (cb or {}).get("cookies", []) if cb else []


# --- page-level (browser running) -----------------------------------------

async def export_profile_bundle_from_page(
    page,
    path,
    *,
    conf_path,
    domains: Optional[Sequence[str]] = None,
    name: Optional[str] = None,
) -> int:
    """Export the current fingerprint + cookies to a bundle. Returns cookie count."""
    from . import cookies as _cookies

    conf_text = Path(conf_path).read_text(encoding="utf-8")
    cookie_bundle = await _cookies.build_cookie_bundle(page, domains=domains)
    if name is None:
        name = Path(conf_path).stem
    write_profile_bundle(path, conf_text=conf_text, cookie_bundle=cookie_bundle, name=name)
    return len(cookie_bundle["cookies"])


async def import_profile_cookies_to_page(page, path, *, clear_existing: bool = False) -> int:
    """Restore a bundle's cookies into a running page. Returns the count loaded.

    The fingerprint must already be in force (extracted before launch); this call
    only handles the login half. Call BEFORE navigating to the target site.
    """
    from . import cookies as _cookies

    cookies = bundle_cookies(path)
    if not cookies:
        return 0
    return await _cookies.set_cookies_on_page(page, cookies, clear_existing=clear_existing)


# --- attach-by-port (persistent/GUI launch, CDP port only) ----------------

async def export_profile_bundle_to_file(
    cdp_port: int,
    path,
    *,
    conf_path,
    domains: Optional[Sequence[str]] = None,
    name: Optional[str] = None,
    attempts: int = 30,
    interval: float = 0.5,
) -> int:
    """Export a running session (by CDP port) to a bundle, detaching without closing."""
    from playwright.async_api import async_playwright
    from . import cookies as _cookies

    async with async_playwright() as pw:
        _browser, page = await _cookies._attach_page_over_cdp(
            pw, cdp_port, attempts=attempts, interval=interval
        )
        return await export_profile_bundle_from_page(
            page, path, conf_path=conf_path, domains=domains, name=name
        )


async def import_profile_bundle_from_file(
    cdp_port: int,
    path,
    *,
    clear_existing: bool = False,
    attempts: int = 30,
    interval: float = 0.5,
) -> int:
    """Import a bundle's cookies into a running session (by CDP port).

    Only restores cookies — the fingerprint had to be extracted and used at
    launch. Detaches without closing the user's browser.
    """
    from playwright.async_api import async_playwright
    from . import cookies as _cookies

    async with async_playwright() as pw:
        _browser, page = await _cookies._attach_page_over_cdp(
            pw, cdp_port, attempts=attempts, interval=interval
        )
        return await import_profile_cookies_to_page(page, path, clear_existing=clear_existing)


# --- synchronous facade ----------------------------------------------------


def export_profile_bundle_to_file_sync(
    cdp_port: int,
    path,
    *,
    conf_path,
    name: Optional[str] = None,
) -> Path:
    """Blocking wrapper around :func:`export_profile_bundle_to_file`.

    Runs the async bundle export on a private worker-thread event loop (mirroring
    the ``_BackgroundLoop`` pattern in huligan.persistent) and returns the path of
    the written ``.hbundle``. ``conf_path`` is the fingerprint .conf embedded in
    the bundle; ``name`` defaults to the conf's stem.
    """
    from .persistent import _BackgroundLoop

    bl = _BackgroundLoop()
    try:
        bl.run_coro(
            export_profile_bundle_to_file(cdp_port, path, conf_path=conf_path, name=name)
        )
    finally:
        bl.shutdown()
    return Path(path)
