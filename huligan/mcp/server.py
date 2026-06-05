"""
Huligan MCP server — exposes the antidetect Browser as five MCP tools
over stdio. Designed for Claude Desktop / any MCP-compatible host.

State model: one ``Browser`` instance per ``session_id``, holding a
single tracked Page. Sessions persist across tool calls until
``huligan_close_session`` is called or the server exits. On exit
we best-effort close everything.

Vision and markdown tools degrade gracefully — they're always
registered, but raise a clear error if their extras (or required env
vars) are missing, so the LLM sees the failure instead of a missing tool.
"""
from __future__ import annotations

import asyncio
import atexit
import logging
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

from huligan import Browser

log = logging.getLogger("huligan.mcp")

mcp = FastMCP("huligan")


class _Session:
    __slots__ = ("browser", "page")

    def __init__(self, browser: Browser, page) -> None:
        self.browser = browser
        self.page = page


_sessions: dict[str, _Session] = {}
_sessions_lock = asyncio.Lock()


def _get(session_id: str) -> _Session:
    sess = _sessions.get(session_id)
    if sess is None:
        raise RuntimeError(
            f"No open session {session_id!r}. "
            f"Call huligan_open_session first."
        )
    return sess


@mcp.tool()
async def huligan_open_session(
    session_id: str,
    proxy: Optional[str] = None,
    headless: bool = False,
) -> str:
    """
    Launch a Huligan antidetect Browser bound to ``session_id``.

    Args:
        session_id: Caller-chosen handle. Reused on subsequent tool
            calls to address this browser. Must be unique among open
            sessions.
        proxy: Proxy URL (``socks5://user:pass@host:port`` or
            ``http://...``). Omit for direct connection.
        headless: Run Chrome with ``--headless=new``. Default False.

    Returns:
        Plain confirmation string with the session_id and the resolved
        exit-IP (or "direct" when no proxy).
    """
    async with _sessions_lock:
        if session_id in _sessions:
            raise RuntimeError(
                f"Session {session_id!r} already open. "
                f"Close it first or pick a different session_id."
            )
        browser = Browser(proxy=proxy, headless=headless)
        await browser.start()
        page = await browser.new_page()
        _sessions[session_id] = _Session(browser, page)

    exit_ip = "direct"
    if browser.geo is not None:
        exit_ip = f"{browser.geo.ip} ({browser.geo.country_code})"
    return f"session {session_id} open via {exit_ip}"


@mcp.tool()
async def huligan_goto(
    session_id: str,
    url: str,
    wait_until: str = "domcontentloaded",
) -> str:
    """
    Navigate the session's page to ``url``.

    Args:
        session_id: Handle from ``huligan_open_session``.
        url: Absolute URL to navigate to.
        wait_until: Playwright load-state — ``"load"``,
            ``"domcontentloaded"``, ``"networkidle"``, or ``"commit"``.

    Returns:
        Status string with final URL and page title (useful to confirm
        no redirect-to-login etc.).
    """
    sess = _get(session_id)
    response = await sess.page.goto(url, wait_until=wait_until)
    status = response.status if response is not None else "n/a"
    title = await sess.page.title()
    return f"status={status} url={sess.page.url!r} title={title!r}"


@mcp.tool()
async def huligan_vision_click(
    session_id: str,
    description: str,
) -> str:
    """
    Vision-LLM driven click: takes a screenshot, asks the configured
    vision model for pixel coordinates of the described element, then
    dispatches a real mouse click at those coordinates.

    Requires the ``vision`` extra (``pip install huligan[vision]``) and
    the env vars ``HULIGAN_VISION_PROVIDER`` (``"openai"`` or
    ``"anthropic"``) plus ``HULIGAN_VISION_API_KEY``.

    Args:
        session_id: Handle from ``huligan_open_session``.
        description: Natural-language description of the target element
            (e.g. ``"blue Sign in button in the top right"``).

    Returns:
        ``"clicked"`` or a descriptive error string.
    """
    try:
        from huligan.vision import VisionAgent
    except ImportError as e:
        raise RuntimeError(
            "vision_click requires `pip install huligan[vision]`"
        ) from e

    if not os.environ.get("HULIGAN_VISION_API_KEY"):
        raise RuntimeError(
            "HULIGAN_VISION_API_KEY env var not set — vision_click "
            "cannot reach the LLM."
        )

    sess = _get(session_id)
    agent = VisionAgent.from_env()
    ok = await agent.click(sess.page, description)
    return "clicked" if ok else "no-click (low confidence or not found)"


@mcp.tool()
async def huligan_extract_markdown(session_id: str) -> str:
    """
    Return the current page as Markdown, optimized for LLM context.

    Uses ``page.content()`` under the hood (CDP-safe — does not call
    ``page.evaluate()`` which is blocked by stealth patches), then
    extracts main content via trafilatura and converts to MD via
    markdownify.

    Requires the ``markdown`` extra
    (``pip install huligan[markdown]``).

    Args:
        session_id: Handle from ``huligan_open_session``.

    Returns:
        Markdown string of the page's main content.
    """
    try:
        from huligan.markdown import extract_markdown
    except ImportError as e:
        raise RuntimeError(
            "extract_markdown requires `pip install huligan[markdown]`"
        ) from e

    sess = _get(session_id)
    return await extract_markdown(sess.page)


@mcp.tool()
async def huligan_close_session(session_id: str) -> str:
    """
    Close the Browser bound to ``session_id`` and release its proxy
    forwarder + user-data-dir.

    Args:
        session_id: Handle from ``huligan_open_session``.

    Returns:
        ``"closed"``.
    """
    async with _sessions_lock:
        sess = _sessions.pop(session_id, None)
    if sess is None:
        return f"no such session {session_id!r}"
    try:
        await sess.browser.close()
    except Exception as e:  # best-effort
        log.warning("error closing session %s: %s", session_id, e)
    return "closed"


def _drain_on_exit() -> None:
    """Best-effort: close any sessions left dangling at server shutdown."""
    if not _sessions:
        return
    try:
        loop = asyncio.new_event_loop()
        try:
            for sid, sess in list(_sessions.items()):
                try:
                    loop.run_until_complete(sess.browser.close())
                except Exception as e:
                    log.warning("drain: close %s failed: %s", sid, e)
        finally:
            loop.close()
    except Exception as e:
        log.warning("drain failed: %s", e)
    _sessions.clear()


atexit.register(_drain_on_exit)


def run() -> None:
    """Start the FastMCP server over stdio (Claude Desktop default)."""
    mcp.run(transport="stdio")
