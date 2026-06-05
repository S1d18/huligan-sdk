# Cookie export / import

> Status: **IMPLEMENTED** (2026-06-05). API: `huligan/cookies.py` +
> `Browser.export_cookies(path, *, domains=None)` / `Browser.import_cookies(path,
> *, clear_existing=False)`. The huligan-app wires these to the right-click
> **Export Cookies** / **Import Cookies** menu (running profile) and to the editor's
> **Upload Cookies** (staged → imported on next launch). This doc is the rationale
> and edge-case reference.

## Why not the obvious approaches

| Approach | Verdict |
|----------|---------|
| `document.cookie` via `page.evaluate()` | ❌ blocked by patch `05_cdp_stealth`, and cannot read `httpOnly` cookies anyway. |
| Copy the whole `user_data_dir` | ❌ Chrome encrypts the on-disk cookie store with OS-bound keys (DPAPI on Windows). Copying it between machines/users does **not** reliably move login state, and it drags along cache/history. Not a clean "hand a file to a teammate" artifact. |
| Read the `Cookies` SQLite directly | ❌ DPAPI-encrypted, machine-bound. Don't. |
| **CDP `Storage.getCookies` / `Network.setCookies`** | ✅ evaluate-free, captures `httpOnly`, round-trips cleanly. **This is the path.** |

## Transport

Open a raw CDP session from the live Playwright page (same pattern as
`huligan/automation/cdp_helpers.py::_get_cdp_session`):

```python
cdp = await page.context.new_cdp_session(page)

# EXPORT — all cookies, all domains, incl. httpOnly/secure/sameSite/expires/partitionKey
cookies = (await cdp.send("Storage.getCookies"))["cookies"]

# IMPORT — restore in bulk BEFORE navigating to the target site
await cdp.send("Network.setCookies", {"cookies": cookies})
```

Prefer `Network.setCookies` over Playwright `context.add_cookies()` for import:
the CDP field shape returned by `Storage.getCookies` round-trips verbatim, while
Playwright's schema differs (expires in seconds, sameSite enum casing) and
introduces translation bugs.

## Public API (to add to `huligan.Browser`)

```python
async def export_cookies(self, path: str | Path, *, domains: list[str] | None = None) -> int
async def import_cookies(self, path: str | Path, *, clear_existing: bool = False) -> int
```

- Return the count written / loaded.
- `domains` filters the export (e.g. only `["x.com"]`).
- `clear_existing` calls `Network.clearBrowserCookies` before import.
- Mirror both on the agents controller (`huligan/agents/`) so pool sessions can
  dump/restore.
- Provide a **transient-headless** helper so export/import works even when no
  window is open: launch Chrome `--headless=new` against the profile + a free
  CDP port just long enough to get/set cookies.
- Once these exist, add thin MCP tools `huligan_export_cookies` /
  `huligan_import_cookies` in `huligan/mcp/server.py` (follow the `_get(session_id)`
  pattern).

## File format

Single JSON file, UTF-8. Body is the well-known Cookie-Editor / EditThisCookie
array shape so cookies from other tools interoperate, wrapped with metadata:

```json
{
  "schema": "huligan-cookies/1",
  "exported_at": "2026-06-04T12:00:00Z",
  "chrome_version": "148.0.7778.97",
  "cookies": [
    {"name": "...", "value": "...", "domain": ".x.com", "path": "/",
     "expires": 1789999999, "httpOnly": true, "secure": true, "sameSite": "Lax"}
  ]
}
```

- Default store: `~/.huligan_profiles/cookies/<profile>.json` (parallels how
  the app saves profiles under `~/.huligan_profiles/profiles/`).
- Explicit `path` arg for a shareable hand-off bundle.
- Keep cookies **separate** from the `.conf` fingerprint — different lifecycle
  (fingerprint = stable identity, cookies = session state).

## Edge cases (handle in code)

- **httpOnly**: only CDP/storage_state captures it — the whole reason to avoid `evaluate`.
- **sameSite**: a `None` cookie MUST also be `secure` or Chrome drops it on import.
- **expires**: epoch seconds (float); session cookies use `-1` — preserve as session.
- **domain scoping**: leading-dot (`.example.com`) vs host-only — preserve exactly.
- **partitionKey / CHIPS**: modern partitioned cookies — pass through verbatim,
  dropping it silently breaks partitioned sessions.
- **Restore order**: set cookies *before* navigating so they apply on first request.

## Security

A cookie bundle is a **bearer credential** — full session hijack. Treat it like
a password: optional symmetric encryption (Fernet + shared passphrase) for the
hand-off file, and never log cookie values.

## App wiring (huligan-app)

Replace the stub menu items (`main_window.py` Export/Import Cookies) and the
no-op Basic-tab "Upload Cookies": call `export_cookies` / `import_cookies` on a
`QThread` (like `ProxyTestThread`), `QFileDialog` save/open, show a count +
domain summary on success. If the profile isn't running, use the transient
headless helper.

## Attach by CDP port (persistent / GUI sessions)

A browser started with `huligan.launch_persistent` (or any externally-launched
Huligan Chrome) exposes only a **remote-debugging port** — the caller has no
Playwright `Page`. Use the attach-by-port helpers; the SDK owns the Playwright
import, connects with a post-launch readiness retry, runs the page-level
export/import, and **detaches without closing** the user's live browser.

```python
import asyncio
from huligan import cookies

# Export the running session's cookies (session.cdp_port from LaunchResult)
asyncio.run(cookies.export_cookies_to_file(cdp_port, "acc1.cookies.json"))

# Import a bundle into a freshly launched session (call before navigating)
asyncio.run(cookies.import_cookies_from_file(cdp_port, "acc1.cookies.json"))
```

| Function | Notes |
|---|---|
| `export_cookies_to_file(cdp_port, path, *, domains=None, attempts=30, interval=0.5)` | Returns count written. `domains` filters by suffix. |
| `import_cookies_from_file(cdp_port, path, *, clear_existing=False, attempts=30, interval=0.5)` | Returns count loaded. |

The default `attempts=30, interval=0.5` gives ~15s of connect retries so a
just-launched session has time to expose CDP. Neither helper ever calls
`browser.close()` — closing would terminate the user's Chrome; the Playwright
driver context just disconnects.
