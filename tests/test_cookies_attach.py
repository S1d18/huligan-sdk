"""Tests for the cookies attach-by-port helpers (huligan.cookies).

No real Chrome/Playwright: a fake ``pw`` exercises the retry + context/page
selection logic of ``_attach_page_over_cdp`` and the non-closing-detach contract.
"""

import asyncio

from huligan import cookies


class _FakePage:
    pass


class _FakeCtx:
    def __init__(self, pages):
        self.pages = list(pages)
        self.opened = 0

    async def new_page(self):
        p = _FakePage()
        self.pages.append(p)
        self.opened += 1
        return p


class _FakeBrowser:
    def __init__(self, contexts):
        self.contexts = list(contexts)
        self.closed = False
        self.new_contexts = 0

    async def close(self):  # must never be called by the helpers
        self.closed = True

    async def new_context(self):
        ctx = _FakeCtx([])
        self.contexts = [ctx]
        self.new_contexts += 1
        return ctx


def _pw_returning(browser, *, fail_times=0):
    calls = {"n": 0}

    class _Chromium:
        async def connect_over_cdp(self, url):
            calls["n"] += 1
            if calls["n"] <= fail_times:
                raise ConnectionError("CDP not ready")
            return browser

    class _Pw:
        chromium = _Chromium()

    return _Pw(), calls


def test_attach_retries_until_ready():
    page = _FakePage()
    browser = _FakeBrowser([_FakeCtx([page])])
    pw, calls = _pw_returning(browser, fail_times=2)

    got_browser, got_page = asyncio.run(
        cookies._attach_page_over_cdp(pw, 9222, attempts=5, interval=0)
    )
    assert calls["n"] == 3            # failed twice, succeeded on the third
    assert got_page is page           # reused the existing page
    assert got_browser.closed is False


def test_attach_reuses_existing_context_and_page():
    page = _FakePage()
    ctx = _FakeCtx([page])
    browser = _FakeBrowser([ctx])
    pw, _ = _pw_returning(browser)

    _b, got_page = asyncio.run(cookies._attach_page_over_cdp(pw, 9222, attempts=1, interval=0))
    assert got_page is page
    assert ctx.opened == 0            # did not open a new page
    assert browser.new_contexts == 0  # did not open a new context


def test_attach_opens_page_when_context_has_none():
    ctx = _FakeCtx([])                 # context exists but has no pages
    browser = _FakeBrowser([ctx])
    pw, _ = _pw_returning(browser)

    _b, got_page = asyncio.run(cookies._attach_page_over_cdp(pw, 9222, attempts=1, interval=0))
    assert got_page in ctx.pages
    assert ctx.opened == 1            # opened exactly one page


def test_attach_opens_context_when_none():
    browser = _FakeBrowser([])         # no contexts at all
    pw, _ = _pw_returning(browser)

    _b, got_page = asyncio.run(cookies._attach_page_over_cdp(pw, 9222, attempts=1, interval=0))
    assert browser.new_contexts == 1
    assert got_page in browser.contexts[0].pages


def test_attach_exhausts_and_raises():
    class _Chromium:
        async def connect_over_cdp(self, url):
            raise ConnectionError("never ready")

    class _Pw:
        chromium = _Chromium()

    try:
        asyncio.run(cookies._attach_page_over_cdp(_Pw(), 9222, attempts=2, interval=0))
    except ConnectionError as e:
        assert "never ready" in str(e)
    else:
        raise AssertionError("expected ConnectionError after retries exhausted")
