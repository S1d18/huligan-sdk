"""Tests for the transparent humanize dispatch layer (T1.2).

Pure dispatch/proxy logic, driven with fake page/locator objects (no browser).
The isTrusted + real-trajectory guarantees are verified live against a binary separately.
"""
import asyncio

from huligan.automation import humanize as hz


def test_resolve_preset():
    assert hz._resolve_preset("default", None)["typing"] == "medium"
    assert hz._resolve_preset("careful", None)["mouse"] == "slow"
    cfg = hz._resolve_preset({"mouse": "fast"}, None)      # dict preset merges over default
    assert cfg["mouse"] == "fast" and cfg["typing"] == "medium"
    assert hz._resolve_preset("default", "careful")["typing"] == "slow"       # human_config str
    assert hz._resolve_preset("default", {"typing": "fast"})["typing"] == "fast"  # dict merge


def test_apply_call_override_pops_human_config():
    kw = {"human_config": "careful", "timeout": 5000}
    cfg = hz._apply_call_override(hz.HUMAN_PRESETS["default"], kw)
    assert cfg["mouse"] == "slow"                 # careful applied
    assert "human_config" not in kw               # popped -> never leaks to Playwright
    assert kw["timeout"] == 5000


class _FakeLocator:
    def __init__(self, name="root"):
        self.name = name
        self.first = self

    def nth(self, i):
        return _FakeLocator(f"{self.name}[{i}]")

    async def text_content(self):
        return "hello"


def test_human_locator_routes_and_chains(monkeypatch):
    calls = []

    async def fake_click(loc, speed_mode="fast", **k):
        calls.append(("click", loc.name, speed_mode))

    async def fake_type(loc, text, speed_mode="paste", clear_before=True, **k):
        calls.append(("type", loc.name, text, speed_mode, clear_before))

    monkeypatch.setattr(hz, "human_like_mouse_click", fake_click)
    monkeypatch.setattr(hz, "human_like_type", fake_type)

    async def run():
        hl = hz._HumanLocator(_FakeLocator(), hz.HUMAN_PRESETS["default"])
        await hl.click()
        await hl.fill("abc")
        await hl.press_sequentially("xy")
        child = hl.nth(2)                          # chaining stays humanised
        assert isinstance(child, hz._HumanLocator)
        await child.click()
        assert await hl.text_content() == "hello"  # unknown attr forwarded to real locator

    asyncio.run(run())
    assert ("click", "root", "medium") in calls
    assert ("type", "root", "abc", "medium", True) in calls
    assert ("type", "root", "xy", "medium", False) in calls
    assert ("click", "root[2]", "medium") in calls


class _FakePage:
    def __init__(self):
        self.clicked = []

    def locator(self, sel):
        return _FakeLocator(sel)

    async def click(self, sel, **kw):             # stock behaviour
        self.clicked.append(sel)

    async def fill(self, sel, val, **kw):
        pass

    def get_by_role(self, role, **kw):
        return _FakeLocator(f"role={role}")


def test_patch_page_idempotent_and_unpatch(monkeypatch):
    routed = []

    async def fake_click(loc, speed_mode="fast", **k):
        routed.append(loc.name)

    monkeypatch.setattr(hz, "human_like_mouse_click", fake_click)

    async def run():
        page = _FakePage()
        hz.patch_page(page)
        assert getattr(page, hz._MARKER) is not None
        hz.patch_page(page)                        # idempotent (no double-wrap)

        await page.click("#btn")                   # routes to human primitive now
        assert routed == ["#btn"]
        assert page.clicked == []                  # stock click did NOT run
        assert isinstance(page.locator("#x"), hz._HumanLocator)
        assert isinstance(page.get_by_role("button"), hz._HumanLocator)

        hz.unpatch_page(page)                       # restore stock
        assert getattr(page, hz._MARKER, None) is None
        await page.click("#after")
        assert page.clicked == ["#after"]          # stock click ran again
        assert not isinstance(page.locator("#x"), hz._HumanLocator)

    asyncio.run(run())


def test_exports():
    import huligan
    for name in ("patch_page", "patch_context", "unpatch_page", "HUMAN_PRESETS"):
        assert hasattr(huligan, name), name
        assert name in huligan.__all__
