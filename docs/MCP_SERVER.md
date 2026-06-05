# Huligan MCP Server

Expose the Huligan antidetect browser to an LLM via the Model Context Protocol. Built for hosts that already know MCP (Claude Desktop, Cursor, IDE clients with MCP support).

The server is intentionally minimal — five tools, focused on the things you can't get from the official Playwright MCP: a session that stays antidetect, vision-LLM clicks, and Markdown extraction for context-window-friendly reading.

For low-level locator clicks, fills, screenshots — keep the official `playwright` MCP installed alongside this one. Run both: Huligan opens and stewards the session, Playwright drives the boring parts.

## Install

```bash
pip install "huligan[mcp]"
```

This pulls `mcp>=1.0.0` and `playwright>=1.40.0`. Add `[vision]` and `[markdown]` if you want the corresponding tools:

```bash
pip install "huligan[mcp,vision,markdown]"
```

Make sure Chrome is available (`huligan.installer.ensure_chrome()` runs lazily on first session open if not).

## Run

```bash
python -m huligan.mcp
```

Speaks MCP over stdio — connect from any MCP host.

## Connect from Claude Desktop

Add to `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`, Windows: `%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "huligan": {
      "command": "python",
      "args": ["-m", "huligan.mcp"],
      "env": {
        "HULIGAN_VISION_PROVIDER": "anthropic",
        "HULIGAN_VISION_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

The two `HULIGAN_VISION_*` env vars are only consulted by `huligan_vision_click`. Omit them if you don't need vision-driven clicks.

Restart Claude Desktop. Five tools appear in the tool picker, all prefixed `huligan_`.

## Tools

### `huligan_open_session(session_id, proxy=None, headless=False)`

Launch an antidetect Chrome bound to a caller-chosen `session_id`. State persists across tool calls until you close the session.

```
> open a Huligan session "shop1" through socks5://user:pass@1.2.3.4:1080
huligan_open_session(session_id="shop1", proxy="socks5://user:pass@1.2.3.4:1080")
→ "session shop1 open via 1.2.3.4 (US)"
```

### `huligan_goto(session_id, url, wait_until="domcontentloaded")`

Navigate the session's page. Returns HTTP status + final URL + title so the LLM can detect redirects (e.g. to login).

```
huligan_goto(session_id="shop1", url="https://example.com/products")
→ "status=200 url='https://example.com/products' title='Products – Example'"
```

### `huligan_vision_click(session_id, description)`

Vision-LLM click by natural-language description. Requires the `vision` extra plus `HULIGAN_VISION_API_KEY` env var. The vision model is queried via `aiohttp`, not via the MCP host's own LLM — so it's billed separately.

```
huligan_vision_click(session_id="shop1", description="the blue 'Add to cart' button on the first product card")
→ "clicked"
```

### `huligan_extract_markdown(session_id)`

Pull the current page as Markdown, ready to drop into the LLM's context. Uses `page.content()` under the hood — works under the stealth patch that blocks `page.evaluate()`.

```
huligan_extract_markdown(session_id="shop1")
→ "# Products\n\n- **Widget Pro** — $19.99\n- **Gizmo** — $9.99\n..."
```

### `huligan_close_session(session_id)`

Closes the Browser, the SOCKS5 forwarder, and removes the temp user-data-dir.

```
huligan_close_session(session_id="shop1")
→ "closed"
```

The server also auto-closes any dangling sessions on exit (`atexit`), so a hard restart of the MCP host won't leak Chrome processes — but call `close_session` explicitly for clean teardown.

## What's deliberately NOT in this MCP

- `click(selector)` / `fill(selector, value)` — use the official `playwright` MCP alongside; no point duplicating it.
- `screenshot()` — same; Playwright MCP returns the image as `ImageContent`, we'd just wrap it.
- `evaluate(js)` — blocked by Huligan's stealth patch (`05_cdp_stealth`). Use `huligan_extract_markdown` to read page state, `huligan_vision_click` to act without selectors.
- Parallel `huligan.agents` pool — that's a higher-level batch-scraping pattern that doesn't fit the synchronous request/response shape of MCP tools. Use `huligan.agents` directly from Python for that.

## Troubleshooting

| Symptom | Probable cause |
|---------|---------------|
| `RuntimeError: vision_click requires pip install huligan[vision]` | Missing extra. Reinstall with `huligan[mcp,vision]`. |
| `RuntimeError: HULIGAN_VISION_API_KEY env var not set` | Set it in `claude_desktop_config.json`'s `env` block. |
| `RuntimeError: No open session 'foo'` | LLM passed a stale or wrong `session_id`. Remind it to `huligan_open_session` first. |
| Chrome doesn't appear | First-launch download in progress (~178 MB). Stderr from `python -m huligan.mcp` shows progress; Claude Desktop swallows it. Tail the server log via `MCP_LOG_LEVEL=debug` env. |
| MCP host hangs on tool call | `huligan_goto` is awaiting `wait_until` — try `"commit"` or `"load"` instead of `"networkidle"` for slow pages. |
