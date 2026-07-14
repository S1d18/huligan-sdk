"""Portable cookie export / import over CDP.

Evaluate-free (patch 05_cdp_stealth blocks ``page.evaluate``) and captures
``httpOnly`` cookies that ``document.cookie`` cannot see. Cookies are written
to a single portable JSON bundle so a login can be handed between machines.

See ``docs/COOKIES.md`` for the full rationale and edge-case notes.
"""
from __future__ import annotations

import json
import datetime
from pathlib import Path
from typing import Optional, Sequence

from .version import CHROME_VERSION

SCHEMA = "huligan-cookies/1"

# Fields accepted by Network.setCookies (CookieParam). Storage.getCookies /
# Network.getAllCookies return extra read-only fields (size, session) that
# setCookies rejects, so we project onto this allow-list on import.
_SET_FIELDS = (
    "name", "value", "domain", "path", "secure", "httpOnly", "sameSite",
    "expires", "priority", "sameParty", "sourceScheme", "sourcePort",
    "partitionKey",
)


async def _new_cdp(page):
    """A CDP session bound to the page's context (works over connect_over_cdp)."""
    return await page.context.new_cdp_session(page)


async def _get_all_cookies(cdp) -> list[dict]:
    # Storage.getCookies returns every cookie in the browser context (all
    # domains, incl. httpOnly + partitionKey). Fall back to the older
    # Network.getAllCookies if the page session rejects the Storage domain.
    try:
        result = await cdp.send("Storage.getCookies")
    except Exception:
        result = await cdp.send("Network.getAllCookies")
    return result.get("cookies", [])


def _clean_for_set(cookie: dict) -> dict:
    out = {k: cookie[k] for k in _SET_FIELDS if cookie.get(k) is not None}
    # CDP marks a session cookie with expires == -1; omit it so it is
    # restored as a session cookie rather than an already-expired one.
    if out.get("expires", 0) == -1:
        out.pop("expires", None)
    return out


async def build_cookie_bundle(page, *, domains: Optional[Sequence[str]] = None) -> dict:
    """Collect all cookies into a bundle dict (schema ``huligan-cookies/1``).

    Shared by :func:`export_cookies_from_page` (writes it to a file) and the
    profile-bundle exporter (embeds it in the zip). No file I/O here.
    """
    cdp = await _new_cdp(page)
    try:
        cookies = await _get_all_cookies(cdp)
    finally:
        try:
            await cdp.detach()
        except Exception:
            pass

    if domains:
        wanted = tuple(d.lstrip(".").lower() for d in domains)
        cookies = [
            c for c in cookies
            if c.get("domain", "").lstrip(".").lower().endswith(wanted)
        ]

    return {
        "schema": SCHEMA,
        "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "chrome_version": CHROME_VERSION,
        "cookies": cookies,
    }


async def export_cookies_from_page(page, path, *, domains: Optional[Sequence[str]] = None) -> int:
    """Dump all cookies to a JSON bundle. Returns the number written."""
    bundle = await build_cookie_bundle(page, domains=domains)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(bundle["cookies"])


def load_cookie_bundle(path) -> list[dict]:
    """Read a bundle (or a bare cookie array) and return the cookie list."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("cookies", [])
    return data  # bare array (Cookie-Editor / EditThisCookie export)


async def set_cookies_on_page(page, cookies, *, clear_existing: bool = False) -> int:
    """Load a list of cookie dicts into the page's context over CDP.

    Shared by :func:`import_cookies_to_page` (reads from a file) and the
    profile-bundle importer (reads from the zip). Call BEFORE navigating.
    """
    cdp = await _new_cdp(page)
    try:
        if clear_existing:
            await cdp.send("Network.clearBrowserCookies")
        params = [_clean_for_set(c) for c in cookies]
        if params:
            await cdp.send("Network.setCookies", {"cookies": params})
    finally:
        try:
            await cdp.detach()
        except Exception:
            pass
    return len(cookies)


async def import_cookies_to_page(page, path, *, clear_existing: bool = False) -> int:
    """Restore cookies from a bundle. Returns the number loaded.

    Call BEFORE navigating to the target site so cookies apply on the first
    request.
    """
    cookies = load_cookie_bundle(path)
    return await set_cookies_on_page(page, cookies, clear_existing=clear_existing)


# --- attach-by-port convenience -------------------------------------------
#
# A persistent/GUI browser is launched via huligan.launch_persistent and exposes
# only a CDP port — the caller has no Playwright Page. These helpers connect to
# that port (with the post-launch readiness retry a fresh session needs), run the
# page-level export/import above, and **detach without closing** the user's live
# browser. The SDK owns the Playwright import so GUI/CLI callers don't have to.


async def _attach_page_over_cdp(pw, cdp_port: int, *, attempts: int = 30, interval: float = 0.5):
    """Connect to ``127.0.0.1:<cdp_port>`` and return ``(browser, page)``.

    Retries the connect (default ~15s at 0.5s spacing) so a just-launched
    session has time to expose CDP. Reuses ``contexts[0]``/``pages[0]`` when
    present, else opens one. The returned ``browser`` must NOT be ``.close()``-d
    by the caller — that would terminate the user's live Chrome; let the
    Playwright driver context disconnect instead.
    """
    import asyncio

    url = f"http://127.0.0.1:{cdp_port}"
    last = None
    for _ in range(max(1, attempts)):
        try:
            browser = await pw.chromium.connect_over_cdp(url)
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            return browser, page
        except Exception as e:  # noqa: BLE001 — surfaced after retries exhausted
            last = e
            await asyncio.sleep(interval)
    raise last or RuntimeError(f"could not connect to CDP at {url}")


async def export_cookies_to_file(
    cdp_port: int,
    path,
    *,
    domains: Optional[Sequence[str]] = None,
    attempts: int = 30,
    interval: float = 0.5,
) -> int:
    """Export a running session's cookies (by CDP port) to a JSON bundle.

    Connects to ``cdp_port``, exports via :func:`export_cookies_from_page`, and
    detaches without closing the browser. Returns the number written.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        _browser, page = await _attach_page_over_cdp(
            pw, cdp_port, attempts=attempts, interval=interval
        )
        return await export_cookies_from_page(page, path, domains=domains)


async def import_cookies_from_file(
    cdp_port: int,
    path,
    *,
    clear_existing: bool = False,
    attempts: int = 30,
    interval: float = 0.5,
) -> int:
    """Import cookies from a JSON bundle into a running session (by CDP port).

    Connects to ``cdp_port``, imports via :func:`import_cookies_to_page`, and
    detaches without closing the browser. Returns the number loaded.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        _browser, page = await _attach_page_over_cdp(
            pw, cdp_port, attempts=attempts, interval=interval
        )
        return await import_cookies_to_page(page, path, clear_existing=clear_existing)
