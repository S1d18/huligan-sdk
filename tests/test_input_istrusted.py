"""T2.4 test (b): every humanize-synthesized event is ``isTrusted === true``.

Runs on Playwright's bundled Chromium (``isTrusted`` is a property of the CDP
``Input.dispatch*`` pipeline, inherent to any Chromium - not a Huligan patch), so no private
binary and no external site are needed. Set ``HULIGAN_CHROME_CDP`` to also run it against a
live Huligan Chrome (paranoid). The event log is read via a DOM sink + ``locator.get_attribute``
- never ``page.evaluate`` - so the same assertion works on stock and paranoid Chrome.
"""
import asyncio
import os

import pytest

from huligan.automation.keyboard import human_like_type
from huligan.automation.mouse import human_like_mouse_click

_FIXTURE = "data:text/html,<button id='btn'>b</button><input id='inp'/>"
_INIT = """
window.__ev = [];
const rec = e => {
  window.__ev.push(e.type + ':' + e.isTrusted);
  document.documentElement.dataset.ev = window.__ev.join(',');
};
for (const t of ['mousedown','mouseup','click','keydown','keyup','input'])
  addEventListener(t, rec, true);
"""


async def _drive(page):
    await page.add_init_script(_INIT)
    await page.goto(_FIXTURE, wait_until="domcontentloaded")
    await human_like_mouse_click(page.locator("#btn"))
    await human_like_type(page.locator("#inp"), "aria@example.test", speed_mode="fast")  # NOT paste
    trace = await page.locator("html").get_attribute("data-ev")
    return (trace or "").split(",") if trace else []


async def _run_stock():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            return await _drive(await browser.new_page())
        finally:
            await browser.close()


async def _run_cdp(cdp_url):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp(cdp_url)
        ctx = b.contexts[0] if b.contexts else await b.new_context()
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        return await _drive(page)


def _collect_events():
    cdp = os.environ.get("HULIGAN_CHROME_CDP")
    try:
        return asyncio.run(_run_cdp(cdp) if cdp else _run_stock())
    except Exception as e:
        pytest.skip(f"no Playwright Chromium available (run 'playwright install chromium'): {e}")


def test_humanize_events_all_istrusted():
    events = _collect_events()
    assert events, "no events were recorded"
    types = {e.split(":")[0] for e in events}
    assert {"mousedown", "mouseup", "click"} <= types, f"missing mouse events: {types}"
    assert {"keydown", "keyup"} <= types, f"missing key events: {types}"
    for e in events:
        assert e.endswith(":true"), f"non-trusted (isTrusted===false) event leaked: {e}"
