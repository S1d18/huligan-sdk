"""Transparent humanize dispatch layer.

``patch_page(page)`` (or ``Browser(humanize=True)``) makes ordinary Playwright calls -
``page.click`` / ``fill`` / ``type`` and ``locator.click`` / ``fill`` / ``type`` /
``press_sequentially`` - route through the existing human-like mouse/keyboard primitives,
so a caller writes plain Playwright and gets curved cursor paths + per-character typing
with occasional self-correcting typos.

The primitives synthesise input only via ``page.mouse.*`` / ``page.keyboard.*`` (CDP
``Input.dispatch*``), so every event is ``isTrusted === true`` by construction; this layer
adds NO new event source and never calls ``page.evaluate`` (which hangs under the default
``cdp_mode="paranoid"``). Async ``Browser`` only - the sync detached launch has no Page.

Instance/factory wrapping is used, never class monkey-patching: patched objects are the real
Playwright ones with a few methods shadowed, so the blast radius is one page/context and it is
fully reversible via :func:`unpatch_page`.
"""
from __future__ import annotations

from .keyboard import human_like_type
from .mouse import human_like_mouse_click
from .scroll import human_like_scroll

# A preset bundles one name onto the per-module speed keys. "default" typing == "medium"
# (per-key 30-110 ms), "careful" == "slow" for high-stakes flows (login / checkout / captcha).
HUMAN_PRESETS = {
    "default": {"mouse": "medium", "typing": "medium", "scroll": "medium", "idle": "natural"},
    "careful": {"mouse": "slow", "typing": "slow", "scroll": "slow", "idle": "active"},
}

_MARKER = "_huligan_humanize"
_CTX_MARKER = "_huligan_humanize_ctx"
_LOCATOR_FACTORIES = (
    "get_by_role", "get_by_text", "get_by_label", "get_by_placeholder",
    "get_by_test_id", "get_by_alt_text", "get_by_title",
)


def _resolve_preset(preset, human_config) -> dict:
    if isinstance(preset, dict):
        cfg = dict(HUMAN_PRESETS["default"])
        cfg.update(preset)
    else:
        cfg = dict(HUMAN_PRESETS.get(preset, HUMAN_PRESETS["default"]))
    if isinstance(human_config, str):
        cfg = dict(HUMAN_PRESETS.get(human_config, cfg))
    elif isinstance(human_config, dict):
        cfg.update(human_config)
    return cfg


def _apply_call_override(base_cfg: dict, call_kwargs: dict) -> dict:
    """Pop a per-call ``human_config`` from kwargs (so it never leaks into Playwright)
    and return the effective config for this call."""
    hc = call_kwargs.pop("human_config", None)
    if hc is None:
        return base_cfg
    if isinstance(hc, str):
        return HUMAN_PRESETS.get(hc, base_cfg)
    if isinstance(hc, dict):
        merged = dict(base_cfg)
        merged.update(hc)
        return merged
    return base_cfg


class _HumanLocator:
    """Proxy that forwards everything to a real Locator but humanises the action
    methods and re-wraps chaining methods so chained locators stay humanised."""

    _CHAIN = (
        "nth", "filter", "locator", "get_by_role", "get_by_text", "get_by_label",
        "get_by_placeholder", "get_by_test_id", "get_by_alt_text", "get_by_title",
    )

    def __init__(self, locator, cfg):
        object.__setattr__(self, "_loc", locator)
        object.__setattr__(self, "_cfg", cfg)

    async def click(self, **kw):
        c = _apply_call_override(self._cfg, kw)
        await human_like_mouse_click(self._loc, speed_mode=c["mouse"])

    async def fill(self, value, **kw):
        c = _apply_call_override(self._cfg, kw)
        await human_like_type(self._loc, value, speed_mode=c["typing"], clear_before=True)

    async def type(self, text, **kw):
        c = _apply_call_override(self._cfg, kw)
        await human_like_type(self._loc, text, speed_mode=c["typing"], clear_before=False)

    async def press_sequentially(self, text, **kw):
        c = _apply_call_override(self._cfg, kw)
        await human_like_type(self._loc, text, speed_mode=c["typing"], clear_before=False)

    @property
    def first(self):
        return _HumanLocator(self._loc.first, self._cfg)

    @property
    def last(self):
        return _HumanLocator(self._loc.last, self._cfg)

    def __getattr__(self, name):
        loc = object.__getattribute__(self, "_loc")
        attr = getattr(loc, name)
        if name in _HumanLocator._CHAIN and callable(attr):
            cfg = object.__getattribute__(self, "_cfg")

            def _wrap(*a, **k):
                return _HumanLocator(attr(*a, **k), cfg)

            return _wrap
        return attr

    def __repr__(self):
        return f"_HumanLocator({self._loc!r})"


def _make_factory(orig_factory, cfg):
    def _wrapped(*a, **k):
        return _HumanLocator(orig_factory(*a, **k), cfg)
    return _wrapped


def patch_page(page, *, preset="default", human_config=None):
    """Route ordinary ``page``/``locator`` action calls through the human primitives.

    Idempotent (re-patching is a no-op), reversible via :func:`unpatch_page`, and scoped to
    this ``page`` object only. Returns the same page.
    """
    if getattr(page, _MARKER, None) is not None:
        return page
    cfg = _resolve_preset(preset, human_config)
    saved = {
        "click": page.click,
        "fill": page.fill,
        "type": getattr(page, "type", None),
        "locator": page.locator,
        "factories": {},
        "human_scroll": getattr(page, "human_scroll", None),
    }
    orig_locator = page.locator

    async def _click(selector, **kw):
        c = _apply_call_override(cfg, kw)
        await human_like_mouse_click(orig_locator(selector), speed_mode=c["mouse"])

    async def _fill(selector, value, **kw):
        c = _apply_call_override(cfg, kw)
        await human_like_type(orig_locator(selector), value, speed_mode=c["typing"], clear_before=True)

    async def _type(selector, text, **kw):
        c = _apply_call_override(cfg, kw)
        await human_like_type(orig_locator(selector), text, speed_mode=c["typing"], clear_before=False)

    async def _human_scroll(**kw):
        return await human_like_scroll(page, **kw)

    page.click = _click
    page.fill = _fill
    page.type = _type
    page.locator = _make_factory(orig_locator, cfg)
    for fac in _LOCATOR_FACTORIES:
        of = getattr(page, fac, None)
        if callable(of):
            saved["factories"][fac] = of
            setattr(page, fac, _make_factory(of, cfg))
    page.human_scroll = _human_scroll

    setattr(page, _MARKER, {"cfg": cfg, "saved": saved})
    return page


def patch_context(context, *, preset="default", human_config=None):
    """Patch every current page in ``context`` and auto-patch future pages (popups/tabs)."""
    for pg in list(context.pages):
        patch_page(pg, preset=preset, human_config=human_config)
    if not getattr(context, _CTX_MARKER, False):
        context.on("page", lambda pg: patch_page(pg, preset=preset, human_config=human_config))
        setattr(context, _CTX_MARKER, True)
    return context


def unpatch_page(page):
    """Restore a page's stock Playwright methods (reverses :func:`patch_page`)."""
    state = getattr(page, _MARKER, None)
    if state is None:
        return page
    saved = state["saved"]
    for name in ("click", "fill", "type"):
        orig = saved.get(name)
        if orig is not None:
            setattr(page, name, orig)
        else:
            try:
                delattr(page, name)
            except AttributeError:
                pass
    page.locator = saved["locator"]
    for fac, of in saved["factories"].items():
        setattr(page, fac, of)
    if saved.get("human_scroll") is not None:
        page.human_scroll = saved["human_scroll"]
    else:
        try:
            delattr(page, "human_scroll")
        except AttributeError:
            pass
    try:
        delattr(page, _MARKER)
    except AttributeError:
        pass
    return page
