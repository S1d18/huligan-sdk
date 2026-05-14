# Huligan Antidetect Browser SDK

Python SDK for controlling the Huligan antidetect Chromium browser. The browser spoofs 50+ fingerprint parameters at the C++ level (not JS injection), making it undetectable by BrowserScan, CreepJS, SannySoft, and other detectors.

## Install

```bash
pip install huligan

# With all optional dependencies
pip install huligan[all]

# Individual extras
pip install huligan[playwright]   # Browser automation (required for new_page())
pip install huligan[geoip]        # Local GeoIP database (faster than API fallback)
pip install huligan[automation]   # Human-like mouse/keyboard
```

## How It Works

When you call `Browser(proxy=...)`, the SDK automatically:

1. **Finds Chrome** — checks `HULIGAN_CHROME` env var, current directory, package siblings, the local cache `~/.huligan/chrome/{version}/`, and system `PATH`. If nothing matches, downloads the patched build from [`huligan-releases`](https://github.com/S1d18/huligan-releases) on first run.
2. **Parses proxy** — supports `socks5://user:pass@ip:port`, `http://...`, `ip:port:user:pass`
3. **GeoIP lookup** — determines timezone, language, coordinates from proxy IP
4. **Generates fingerprint** — 50+ parameters (screen, GPU, fonts, canvas noise, WebGL, etc.)
5. **Starts proxy forwarder** — local no-auth SOCKS5 → upstream with-auth (Chrome doesn't support SOCKS5 auth)
6. **Launches Chrome** — with `HULIGAN_CONFIG_PATH` env var pointing to `.conf` profile
7. **Waits for CDP** — browser is ready for automation

All steps happen inside `await browser.start()` (or `async with Browser(...)`).

### First-run download

The patched Chromium binary (~180 MB) is fetched once and cached at
`~/.huligan/chrome/{version}/`. Subsequent runs reuse the cache — no
network access needed. Override the location with `HULIGAN_CHROME_DIR`,
or skip the download entirely by setting `HULIGAN_CHROME` to an existing
`chrome.exe`.

## Quick Start

### Minimal — proxy only (everything auto-generated)

```python
import asyncio
from huligan import Browser

async def main():
    async with Browser(proxy="socks5://user:pass@ip:port") as browser:
        page = await browser.new_page()
        await page.goto("https://browserscan.net")
        print(await page.title())
        await page.wait_for_timeout(30000)

asyncio.run(main())
```

### With custom fingerprint

**Quick path — one integer, full profile** (recommended for most users):

```python
import asyncio
from huligan import Browser, FingerprintProfile
from pathlib import Path

async def main():
    # Single seed in, deterministic 50-field profile out.
    # Same seed + same SDK version = identical fingerprint.
    profile = FingerprintProfile.from_seed(
        seed=12345,
        platform="Win32",                # "MacIntel" / "Linux x86_64"
        gpu_vendor_preference="nvidia",  # "amd" / "intel" / None
    )

    conf_path = Path("my_profile.conf").resolve()
    conf_path.write_text(profile.to_conf())

    async with Browser(
        proxy="socks5://user:pass@ip:port",
        profile_path=str(conf_path),
    ) as browser:
        page = await browser.new_page()
        await page.goto("https://browserscan.net")
        await page.wait_for_timeout(30000)

asyncio.run(main())
```

**Power-user path — explicit Generator** (when you want to override
individual fields before persisting):

```python
from huligan import FingerprintGenerator

gen = FingerprintGenerator(seed=12345)
profile = gen.generate(platform="Win32", gpu_vendor_preference="nvidia")
profile.timezone = "Asia/Tokyo"            # override anything
profile.connection_effective_type = "3g"
Path("my_profile.conf").write_text(profile.to_conf())
```

### Profile templates

For non-power users who want a realistic identity in one line, six
curated presets bundle GPU + screen + locale + timezone + hardware
specs that look plausible together:

```python
from huligan import FingerprintProfile

# Deterministic: same template + same seed → identical profile.
p = FingerprintProfile.template("usa_verified_facebook", seed=42)
# Omit `seed` to draw a fresh random 64-bit seed each call.
p = FingerprintProfile.template("macos_developer")
```

Available templates:

```python
from huligan.templates import list_templates
for name, desc in list_templates():
    print(f"{name}: {desc}")
# usa_verified_facebook: US Windows desktop, NVIDIA RTX 3060, 1920x1080, en-US, ...
# usa_office_chrome:     US office worker, Intel UHD 770, 1920x1080, en-US, ...
# eu_mobile_twitter:     EU mid-range laptop (Win32, Intel Iris Xe), 1536x864, de-DE, ...
# apac_crypto_exchange:  APAC gaming workstation, NVIDIA RTX 3070, 2560x1440, en-US, ...
# latam_casual_browsing: LatAm modest hardware, AMD RX 5600 XT, 1366x768, es-MX, ...
# macos_developer:       macOS dev box, Apple M2, 2560x1440 @2x, en-US, ...
```

Templates preserve `audio_noise_seed=0` and stay internally consistent
(WebGL params/extensions are recomputed from the overridden renderer).

### Without proxy (local testing)

```python
async with Browser() as browser:
    page = await browser.new_page()
    await page.goto("https://browserscan.net")
```

### Multiple browsers with different proxies

```python
async def main():
    proxies = [
        "socks5://user1:pass1@ip1:port1",
        "socks5://user2:pass2@ip2:port2",
    ]

    browsers = []
    for proxy in proxies:
        b = Browser(proxy=proxy)
        await b.start()
        browsers.append(b)
        print(f"Browser: PID={b.pid}, GeoIP={b.geo}")

    # ... do work ...

    for b in browsers:
        await b.close()
```

### Batch accounts with ProfilePool

```python
from huligan.profile_pool import ProfilePool, ProfilePoolConfig
from pathlib import Path

# Generate pool once (reuses on next run)
pool = ProfilePool(ProfilePoolConfig(pool_size=100, pool_dir=Path("./pool")))
pool.generate_pool()

# Account #42 always gets the same profile
profile_path = pool.get_by_index(42)

async with Browser(
    proxy="socks5://...",
    profile_path=str(profile_path),
    user_data_dir="./user_data/account_42",  # persistent cookies
) as browser:
    page = await browser.new_page()
```

### Human-like automation

```python
from huligan.automation import human_like_mouse_click, human_like_type

async with Browser(proxy="socks5://...") as browser:
    page = await browser.new_page()
    await page.goto("https://example.com/login")

    # Smooth curved mouse movement + click
    await human_like_mouse_click(page.locator("input[name='email']"))

    # Realistic typing with random delays
    await human_like_type(page.locator("input[name='email']"), "user@example.com", speed_mode="medium")
```

## API Reference

### `Browser(**kwargs)`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `proxy` | str | None | Proxy string: `socks5://user:pass@ip:port`, `http://...`, or `ip:port:user:pass` |
| `profile_path` | str/Path | None | Path to `.conf` file. If None, generates random profile |
| `fingerprint` | dict | None | Options for `FingerprintGenerator.generate()`: `platform`, `gpu_vendor_preference`, `seed` |
| `chrome_path` | str/Path | None | Path to chrome.exe. If None, auto-detects |
| `timezone` | str | None | Override timezone (e.g. `"Europe/Helsinki"`). If None, uses GeoIP |
| `language` | str | None | Override language (e.g. `"fi-FI,fi"`). If None, uses GeoIP |
| `cdp_port` | int | None | CDP debugging port. If None, assigns random free port |
| `headless` | bool | False | Run in headless mode |
| `user_data_dir` | str/Path | None | Chrome user data dir. If None, uses temp dir (deleted on close) |
| `extra_args` | list | None | Additional Chrome command-line flags |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `await browser.start()` | Browser | Launch browser (called automatically by `async with`) |
| `await browser.new_page()` | Page | Create new page via Playwright CDP |
| `await browser.close()` | None | Close browser, forwarder, clean up temp files |

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `browser.cdp_url` | str | `http://127.0.0.1:{port}` |
| `browser.cdp_port` | int | CDP port number |
| `browser.pid` | int | Chrome process ID |
| `browser.profile_path` | Path | Path to active `.conf` file |
| `browser.fingerprint_profile` | FingerprintProfile | Generated profile (None if using existing .conf) |
| `browser.geo` | GeoIPResult | GeoIP data (None if no proxy) |

### `FingerprintGenerator(seed=None)`

```python
gen = FingerprintGenerator(seed=12345)  # Reproducible
profile = gen.generate(platform="Win32", gpu_vendor_preference="nvidia")
conf_text = profile.to_conf()  # Returns string in key=value format
```

### `ProfilePool(config)`

```python
pool = ProfilePool(ProfilePoolConfig(pool_size=100, pool_dir=Path("./pool")))
pool.generate_pool()           # Generate (skips if exists)
pool.get_random()              # Random profile path
pool.get_by_index(42)          # Deterministic by index
pool.get_next()                # Round-robin
len(pool)                      # Pool size
```

### `GeoIPManager()`

```python
from huligan.geoip import GeoIPManager

manager = GeoIPManager()
result = manager.lookup("1.2.3.4")
print(result.timezone, result.language, result.country_name)
manager.close()
```

### `markdown` — HTML → Markdown for LLM agents

Pulls a page's HTML through `page.content()` (paranoid-mode safe — no
`page.evaluate()` needed) and converts it to clean Markdown using
readability filtering. Primary engine is `trafilatura` (strips
boilerplate like nav/ads/footers); falls back to `markdownify` for SPA
shells or very short documents.

Install:

```bash
pip install huligan[markdown]
```

```python
from huligan import Browser, extract_markdown

async with Browser(proxy="socks5://...") as b:
    page = await b.new_page()
    await page.goto("https://en.wikipedia.org/wiki/Web_scraping")
    md = await extract_markdown(page, include_images=False)
    print(md)
```

Or reuse on raw HTML:

```python
from huligan import MarkdownExtractor

ext = MarkdownExtractor(strategy="trafilatura", include_links=True)
md = ext.from_html(html_string, base_url="https://example.com")
```

### `agents` — high-level scraping pool / LLM-agent runner

Run a high-level scraping framework on top of huligan's patched
Chromium. Same browser as manual antidetect work, but with a built-in
request queue, session pool, proxy rotation, and dataset storage.
Useful for both classical scraping pipelines and LLM browser agents
(Stagehand, browser-use, and similar AI agent frameworks).

Install (two steps — the upstream runtime is fetched dynamically so
it is not part of huligan's dependency graph):

```bash
pip install huligan[agents]
python -c "from huligan.agents._runtime import setup_runtime; setup_runtime()"
```

Single-fingerprint usage:

```python
import asyncio
from huligan.agents import HuliganAgent

async def main():
    agent = HuliganAgent(
        proxy="socks5://user:pass@host:port",
        fingerprint_seed=42,         # deterministic profile from a seed
        headless=True,
    )

    @agent.router.default_handler
    async def handler(context):
        await context.enqueue_links(selector=".titleline > a", limit=5)
        await context.push_data({"url": context.request.url})

    await agent.run(["https://news.ycombinator.com"])
    await agent.export_data("scraped.json")

asyncio.run(main())
```

Pool of distinct identities:

```python
agent = HuliganAgent.from_pool([
    {"proxy": "socks5://p1...", "fingerprint_seed": 1},
    {"proxy": "socks5://p2...", "fingerprint_seed": 2},
    {"proxy": "socks5://p3...", "fingerprint_seed": 3},
])
```

`page.locator()` works as usual; `page.evaluate()` is blocked by
huligan's CDP stealth in paranoid mode (default) — see
`docs/BROWSER_AUTOMATION.md`.

### `automation`

Behavioural helpers split across modules. Mouse/keyboard need the
`[automation]` extra (pytweening + loguru); scroll/idle have no extra
deps beyond playwright.

```python
from huligan.automation import (
    # huligan[automation] — Bezier mouse with sub-step curving, easing,
    # post-click drift; realistic typing with typos, double-presses,
    # chunked rhythm, word/long pauses.
    human_like_mouse_click,
    human_like_type,
    human_like_hotkey,

    # No extra deps — useful for behavioural-biometrics warmup.
    # Untargeted scrolling with chunk jitter and occasional reverse-wheel.
    human_like_scroll,
    human_like_scroll_to_top,
    # Tiny natural cursor jitter during reading pauses. Mitigates the
    # "motionless cursor = bot" signal that reCAPTCHA v3 / Cloudflare
    # Turnstile / FingerprintJS Pro behaviour-signal weight heavily.
    idle_mouse_movement,
    simulated_reading_pause,
)
```

Example — read-and-scroll feed warmup:

```python
async with Browser(proxy="socks5://...") as browser:
    page = await browser.new_page()
    await page.goto("https://news.ycombinator.com")
    await simulated_reading_pause(page, words=80)       # ~22s read
    await human_like_scroll(page, "down", distance=900, speed_mode="medium")
    await simulated_reading_pause(page, words=60, intensity="subtle")
    await human_like_scroll(page, "down", distance=1200)
```

## Examples

See `examples/` directory:

**Getting started:**

| File | Description |
|------|-------------|
| `example_simple.py` | Minimal — 5 lines |
| `example_with_proxy.py` | Full proxy chain with GeoIP info |
| `example_no_proxy.py` | Local testing without proxy |
| `example_from_seed.py` | One-line profile factory: `FingerprintProfile.from_seed(N)` |
| `example_template.py` | Named presets: `FingerprintProfile.template("usa_verified_facebook")` |
| `example_custom_fingerprint.py` | Reproducible seed-based profile (Generator API) |

**Multi-account & scaling:**

| File | Description |
|------|-------------|
| `example_multi_accounts.py` | Multiple browsers simultaneously |
| `example_batch_accounts.py` | ProfilePool for 1000+ accounts |
| `example_parallel_browsers.py` | asyncio concurrency with Semaphore |
| `example_proxy_rotation.py` | Same profile, different proxies |
| `example_persistent_session.py` | Save/restore login sessions (cookies) |

**Automation & scraping:**

| File | Description |
|------|-------------|
| `example_human_like.py` | Human-like mouse/keyboard |
| `example_cloudflare_turnstile.py` | Cloudflare bypass with retry logic |
| `example_fingerprint_check.py` | Verify fingerprint on browserscan.net |
| `example_scraping_pagination.py` | Scrape with pagination and error handling |
| `example_markdown.py` | HTML → Markdown for LLM consumption |
| `agents/example_basic_scrape.py` | High-level scraping pool (single browser) |
| `agents/example_pool.py` | Round-robin across multiple identities |

## Important: Browser Automation Limitations

Huligan has CDP stealth patches that **block `page.evaluate()`**. Use locator methods instead:

```python
# BLOCKED — don't use:
await page.evaluate("document.title")

# WORKS — use this:
title = await page.title()
text = await page.locator("#price").text_content()
count = await page.locator(".item").count()
value = await page.locator("input").input_value()
```

See **[docs/BROWSER_AUTOMATION.md](docs/BROWSER_AUTOMATION.md)** for the full guide with workarounds and cheatsheet.

## Documentation

| File | Description |
|------|-------------|
| `docs/BROWSER_AUTOMATION.md` | **What works, what's blocked, workarounds** |
| `docs/QUICKSTART.md` | Getting started tutorial |
| `docs/PROXY_LAUNCH_GUIDE.md` | Proxy setup, DNS leaks, WebRTC |
| `docs/GEOIP_SETUP.md` | MaxMind GeoLite2 database setup |

## License

The Huligan SDK (this repository) is licensed under the
**[Apache License 2.0](LICENSE)**. Third-party components retain their
own licenses — see [`NOTICE.md`](NOTICE.md) for the full attribution
list, including the optional GeoLite2 database (CC BY-SA 4.0).

The patched Chromium **binary** that this SDK downloads from
[`huligan-releases`](https://github.com/S1d18/huligan-releases) is
**NOT** under Apache 2.0. It is distributed under a custom End-User
License Agreement that prohibits redistribution and SaaS bundling.
See the [binary EULA](https://github.com/S1d18/huligan-releases/blob/main/LICENSE.txt)
before integrating the binary into a product you ship to others.

> "Huligan" is an unregistered trademark of the Huligan Project. The
> Apache 2.0 license does not grant trademark rights (Section 6).
