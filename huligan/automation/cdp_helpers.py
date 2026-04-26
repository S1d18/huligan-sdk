"""
CDP-compatible replacements for playwright methods that don't work via connect_over_cdp.

Problem: When using playwright.connect_over_cdp(), these methods hang/timeout:
  - locator.bounding_box()
  - locator.wait_for()
  - page.viewport_size (returns None)

Solution: Use CDP session (DOM.getBoxModel, Page.getLayoutMetrics) directly.
These work reliably with Huligan Chrome via CDP connection.
"""
from loguru import logger

# Cache CDP sessions per page to avoid creating new ones
_cdp_sessions = {}


async def _get_cdp_session(page):
    """Get or create a CDP session for the given page."""
    page_id = id(page)
    if page_id not in _cdp_sessions:
        _cdp_sessions[page_id] = await page.context.new_cdp_session(page)
    return _cdp_sessions[page_id]


async def cdp_bounding_box(page, selector: str, timeout: float = 5.0) -> dict | None:
    """
    Get element bounding box via CDP DOM.getBoxModel.
    Returns dict {"x": ..., "y": ..., "width": ..., "height": ...} or None.
    """
    try:
        cdp = await _get_cdp_session(page)
        doc = await cdp.send("DOM.getDocument")
        node = await cdp.send("DOM.querySelector", {
            "nodeId": doc["root"]["nodeId"],
            "selector": selector
        })
        if not node or node.get("nodeId", 0) == 0:
            return None
        box_model = await cdp.send("DOM.getBoxModel", {"nodeId": node["nodeId"]})
        # content quad: [x1,y1, x2,y2, x3,y3, x4,y4]
        c = box_model["model"]["content"]
        return {
            "x": c[0],
            "y": c[1],
            "width": c[2] - c[0],
            "height": c[5] - c[1],
        }
    except Exception as e:
        logger.trace(f"cdp_bounding_box({selector}) failed: {e}")
        return None


async def cdp_viewport_size(page) -> dict:
    """
    Get viewport size via CDP Page.getLayoutMetrics.
    Returns {"width": ..., "height": ...}.
    """
    try:
        cdp = await _get_cdp_session(page)
        metrics = await cdp.send("Page.getLayoutMetrics")
        vp = metrics.get("cssVisualViewport", metrics.get("visualViewport", {}))
        w = vp.get("clientWidth", 1280)
        h = vp.get("clientHeight", 720)
        if w and h:
            return {"width": int(w), "height": int(h)}
    except Exception as e:
        logger.trace(f"cdp_viewport_size failed: {e}")
    return {"width": 1280, "height": 720}


async def cdp_scroll_y(page) -> float:
    """Get current scroll position via CDP."""
    try:
        cdp = await _get_cdp_session(page)
        metrics = await cdp.send("Page.getLayoutMetrics")
        vp = metrics.get("cssVisualViewport", metrics.get("visualViewport", {}))
        return float(vp.get("pageY", 0))
    except Exception:
        return 0.0


async def cdp_document_height(page) -> float:
    """Get document height via CDP."""
    try:
        cdp = await _get_cdp_session(page)
        metrics = await cdp.send("Page.getLayoutMetrics")
        cs = metrics.get("cssContentSize", metrics.get("contentSize", {}))
        return float(cs.get("height", 5000))
    except Exception:
        return 5000.0


async def cdp_is_visible(page, selector: str) -> bool:
    """Check if element exists and has non-zero size via CDP."""
    box = await cdp_bounding_box(page, selector)
    return box is not None and box["width"] > 0 and box["height"] > 0


async def cdp_bounding_box_locator(locator, timeout: float = 1.0) -> dict | None:
    """
    Get bounding box for a playwright Locator.
    Tries locator.bounding_box first (fast), falls back to CDP.
    """
    # Try playwright native first (works when not via connect_over_cdp)
    try:
        box = await locator.bounding_box(timeout=int(timeout * 1000))
        if box:
            return box
    except Exception:
        pass

    page = locator.page

    # Fallback 1: extract CSS selector and use CDP DOM.getBoxModel
    selector = _extract_selector(locator)
    if selector:
        box = await cdp_bounding_box(page, selector)
        if box:
            return box

    # Fallback 2: use CDP Runtime.evaluate with querySelector on cleaned selector
    # Handles complex playwright selectors like "textarea[name='q'] >> nth=0"
    try:
        box = await _cdp_bounding_box_via_evaluate(locator)
        if box:
            return box
    except Exception:
        pass

    return None


async def _cdp_bounding_box_via_evaluate(locator) -> dict | None:
    """
    Get bounding box by evaluating JS via CDP Runtime.evaluate.
    Works for any element that playwright can locate, even with complex selectors.
    Uses locator.evaluate() which works even when bounding_box() hangs.
    """
    try:
        result = await locator.evaluate(
            "el => { const r = el.getBoundingClientRect(); "
            "return {x: r.x, y: r.y, width: r.width, height: r.height}; }"
        )
        if result and result.get("width", 0) > 0 and result.get("height", 0) > 0:
            return result
    except Exception:
        pass

    # If locator.evaluate fails, try CDP Runtime.evaluate with cleaned selector
    page = locator.page
    css = _extract_selector_cleaned(locator)
    if not css:
        return None
    try:
        cdp = await _get_cdp_session(page)
        resp = await cdp.send("Runtime.evaluate", {
            "expression": f"(() => {{ const el = document.querySelector(`{css}`); "
                          f"if (!el) return null; const r = el.getBoundingClientRect(); "
                          f"return {{x: r.x, y: r.y, width: r.width, height: r.height}}; }})()",
            "returnByValue": True,
        })
        val = resp.get("result", {}).get("value")
        if val and val.get("width", 0) > 0:
            return val
    except Exception as e:
        logger.trace(f"_cdp_bounding_box_via_evaluate CDP failed: {e}")

    return None


async def cdp_wait_for_visible(locator, timeout: float = 10.0) -> bool:
    """
    Wait for element to be visible. CDP-compatible replacement for locator.wait_for().
    """
    import asyncio
    page = locator.page

    # Try native first
    try:
        await locator.wait_for(state="visible", timeout=min(int(timeout * 1000), 2000))
        return True
    except Exception:
        pass

    # Fallback: check is_visible in a loop
    end_time = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end_time:
        try:
            if await locator.is_visible():
                return True
        except Exception:
            pass
        await asyncio.sleep(0.3)

    return False


def _extract_selector(locator) -> str | None:
    """
    Try to extract a CSS selector from a Playwright Locator.
    Returns raw selector only if it's a clean CSS selector (no playwright internals).
    """
    try:
        sel = locator._impl_obj._selector
        if not sel:
            return None
        # Skip playwright internal selectors
        if sel.startswith("internal:"):
            return None
        # Skip selectors with playwright-specific operators
        if " >> " in sel:
            return None
        return sel
    except Exception:
        pass
    return None


def _extract_selector_cleaned(locator) -> str | None:
    """
    Extract CSS selector from locator, stripping playwright-specific parts.
    E.g. "textarea[name='q'], input[name='q'] >> nth=0" -> "textarea[name='q'], input[name='q']"
    """
    try:
        sel = locator._impl_obj._selector
        if not sel:
            return None
        if sel.startswith("internal:"):
            return None
        # Strip playwright >> operators (nth, has, visible, etc.)
        if " >> " in sel:
            sel = sel.split(" >> ")[0].strip()
        if sel:
            return sel
    except Exception:
        pass
    return None


def cleanup_cdp_session(page):
    """Remove cached CDP session when page is closed."""
    _cdp_sessions.pop(id(page), None)


# === Sync versions (for sync mode) ===
# Sync mode doesn't use connect_over_cdp typically, so these are thin wrappers.
# If needed, implement via sync CDP client.

def sync_bounding_box(locator, timeout=5000):
    """Sync fallback — use locator.bounding_box with short timeout."""
    try:
        return locator.bounding_box(timeout=timeout)
    except Exception:
        return None


def sync_viewport_size(page) -> dict:
    """Sync fallback."""
    vp = page.viewport_size
    if vp:
        return vp
    return {"width": 1280, "height": 720}
