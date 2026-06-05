# Proxy Launch Guide

## Architecture

```
Chrome → local SOCKS5 no-auth → ProxyForwarder → upstream SOCKS5 with auth
```

Chrome doesn't support SOCKS5 with username/password natively. The SDK runs a local Python SOCKS5 forwarder on a random port — Chrome connects to that, and the forwarder handles auth with the upstream. This is the same approach used by Dolphin Anty and Multilogin.

## Basic Usage (SDK handles everything)

```python
from huligan import Browser

async with Browser(proxy="socks5://user:pass@ip:port") as browser:
    page = await browser.new_page()
    await page.goto("https://browserscan.net")
```

When you pass `proxy=`, the SDK automatically:
1. Parses proxy URL (supports `socks5://`, `http://`, and `ip:port:user:pass` format)
2. Resolves proxy IP via GeoIP → gets timezone, language, coordinates
3. Starts local SOCKS5 forwarder (if proxy has auth)
4. Launches Chrome with correct flags
5. Sets `HULIGAN_CONFIG_PATH` for fingerprint
6. Cleans up on close

## Proxy Formats

```python
# SOCKS5 with auth
Browser(proxy="socks5://user:pass@host:port")

# HTTP with auth
Browser(proxy="http://user:pass@host:port")

# Colon-separated (ip:port:user:pass)
Browser(proxy="94.154.190.106:62677:myuser:mypass")

# No auth (forwarder not needed)
Browser(proxy="socks5://host:port")

# No proxy (local testing)
Browser()
```

## Override GeoIP Results

By default timezone and language come from GeoIP. You can override:

```python
Browser(
    proxy="socks5://user:pass@ip:port",
    timezone="Europe/Helsinki",   # override GeoIP timezone
    language="fi-FI,fi",          # override GeoIP language
)
```

## Without proxy (local testing)

```python
async with Browser() as browser:
    page = await browser.new_page()
    await page.goto("https://browserscan.net")
```

No forwarder, no GeoIP lookup. Timezone and language come from the generated `.conf` profile.

## Chrome Flags Used

The SDK sets these Chrome flags automatically when a proxy is configured:

```
--proxy-server=socks5://127.0.0.1:<RANDOM_PORT>
--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1 , EXCLUDE <proxy_ip>
--force-webrtc-ip-handling-policy=disable_non_proxied_udp
--lang=<language_from_geoip>
```

The `host-resolver-rules` flag routes all DNS through the proxy (prevents DNS leaks). The proxy IP itself is excluded so the forwarder can connect to it directly.

## Timezone

Timezone is applied at **C++ level** by the `16_timezone.py` Chromium patch — it reads the `timezone=` key from the `.conf` file. No CDP override is needed. The SDK writes the GeoIP timezone into the `.conf` before launching Chrome.

## WebRTC Leak Protection

The `--force-webrtc-ip-handling-policy=disable_non_proxied_udp` flag prevents WebRTC from revealing the real IP. Combined with DNS-through-proxy, there are no IP leaks.

## Manual ProxyForwarder (without Browser class)

```python
from huligan.proxy import ProxyForwarder
import asyncio

async def main():
    forwarder = ProxyForwarder(
        upstream_host="94.154.190.106",
        upstream_port=62677,
        upstream_user="myuser",
        upstream_pass="mypass",
        upstream_type="socks5",
    )
    local_port = await forwarder.start()
    print(f"Forwarder running on 127.0.0.1:{local_port}")
    
    # Use local_port with Chrome --proxy-server
    await asyncio.sleep(60)
    await forwarder.stop()

asyncio.run(main())
```

## Troubleshooting

### BrowserScan shows <97%

- Check that proxy IP matches the timezone/language in your profile
- With `Browser(proxy=...)`, GeoIP sets timezone and language automatically
- If you use a manual `.conf` without GeoIP, ensure `timezone=` and `languages=` match the proxy country

### DNS leak detected

Ensure Chrome is launched with `--host-resolver-rules`. The `Browser` class adds this automatically. If using Chrome directly, use:
```
--host-resolver-rules="MAP * ~NOTFOUND , EXCLUDE 127.0.0.1 , EXCLUDE <proxy_ip>"
```

### Proxy connection refused

Test the upstream proxy directly:
```bash
curl --socks5 user:pass@host:port https://api.ipify.org
```

### GeoIP lookup fails

The SDK falls back to ip-api.com (online). If you're behind a proxy yourself, set it before importing:
```python
import os
os.environ["https_proxy"] = "http://..."
from huligan import Browser
```

Or use a local MaxMind database — see `docs/GEOIP_SETUP.md`.

## Persistent / GUI launch (synchronous, detached)

`Browser` is an **async** context manager for automation — it connects
Playwright over CDP and **terminates Chrome on exit**. A desktop GUI (PySide6)
or any synchronous caller that wants a *persistent, user-driven* browser should
use `launch_persistent` instead.

```python
from huligan import launch_persistent

session = launch_persistent(
    profile_path="~/.huligan_profiles/acc1.conf",
    proxy="socks5://user:pass@1.2.3.4:1080",
    proxy_type="socks5",          # pass explicitly from a GUI profile (see below)
    user_data_dir="~/.huligan_profiles/acc1",  # persistent cookies/storage
    url="https://browserscan.net",
)

print(session.pid, session.cdp_url)   # quacks like subprocess.Popen
# ... user drives the browser by hand ...
session.stop()                        # terminates Chrome + tears down forwarder + loop
```

`launch_persistent` runs the **same launch contract** as `Browser` (it reuses
`build_launch_plan` internally), so the GUI path gets, identically:

- the auth-proxy **SOCKS5 forwarder** (Chrome can't do SOCKS5 auth natively),
- the **WebRTC / DNS leak flags** and `--host-resolver-rules` exclusion,
- **GeoIP** timezone / `--accept-lang` resolution,
- the `HULIGAN_CONFIG_PATH` and `HULIGAN_CDP_MODE` env wiring.

### Why a separate API?

The `ProxyForwarder` is an asyncio TCP server, but a GUI calls from synchronous
code and the forwarder must outlive the call. `launch_persistent` hosts the
forwarder on a private daemon-thread event loop for Chrome's lifetime and tears
it down in `LaunchResult.stop()`. The caller never touches asyncio.

### `LaunchResult`

| Member | Purpose |
|---|---|
| `.pid` / `.poll()` / `.wait()` / `.terminate()` / `.kill()` | Popen-compatible surface for process tracking |
| `.cdp_port` / `.cdp_url` | connect cookie/automation tools to the live session |
| `.profile_path` / `.user_data_dir` | resolved paths |
| `.process` | the underlying `subprocess.Popen` (attach a log handle, etc.) |
| `.stop(timeout=5.0)` | terminate Chrome, then stop forwarder + background loop (idempotent) |

It also works as a context manager (`with LaunchSession(...) as s:`), and you can
attach arbitrary attributes (e.g. a GUI log handle) to it freely.

### `proxy_type` matters from a GUI

`parse_proxy_string` defaults a bare `host:port:user:pass` string to **socks5**.
A GUI typically stores the protocol separately (the desktop app defaults to
`http`). Always pass `proxy_type=` explicitly when the source is a GUI profile so
the proxy scheme isn't silently wrong.

### Key parameters

| Param | Default | Notes |
|---|---|---|
| `conf_geo` | `"copy"` | How resolved timezone/language/geolocation/`webrtc_local_ipv4` reach the binary. The saved profile is a **template, never mutated** by default: `"copy"` launches from a temp copy of the `.conf` (deleted on `stop()`); `"inplace"` writes into the saved file (legacy); `"off"` writes nothing (timezone via `TZ` env, language via `--accept-lang` only — no geolocation/WebRTC conf spoof). |
| `geoip` | `True` | Run GeoIP + exit-IP probes. Set `False` to skip all network probes (offline / fast launch). |
| `wait_for_cdp` | `False` | Fire-and-forget by default (matches a GUI launch). Set `True` to block until the CDP endpoint answers. |
| `popen_kwargs` | `None` | Splatted into `subprocess.Popen` — a GUI passes `creationflags` (e.g. `CREATE_NO_WINDOW`) and `stdout`/`stderr` log handles here. |

### Cookies on a persistent session

The session exposes only a CDP port, not a Playwright `Page`. Use the
attach-by-port cookie helpers — see `docs/COOKIES.md`.
