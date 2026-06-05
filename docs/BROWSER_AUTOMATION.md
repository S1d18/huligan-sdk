# Browser Automation Guide

Huligan browser has CDP stealth patches that hide automation artifacts from bot detectors. This means some standard Playwright methods **don't work** or behave differently.

## What Works and What Doesn't

### Works normally

```python
# Navigation
await page.goto("https://example.com")
await page.go_back()
await page.reload()

# Selectors / Locators (PREFERRED way to interact)
await page.locator("input[name='email']").fill("user@example.com")
await page.locator("button[type='submit']").click()
await page.locator("#result").text_content()
await page.locator(".item").count()
await page.locator("a").nth(2).click()

# Waiting
await page.wait_for_selector("#loaded")
await page.wait_for_load_state("networkidle")
await page.wait_for_timeout(3000)
await page.locator("#btn").wait_for(state="visible")

# Keyboard & Mouse (low-level)
await page.keyboard.type("hello world")
await page.keyboard.press("Enter")
await page.mouse.click(100, 200)

# Screenshots
await page.screenshot(path="screenshot.png")
await page.locator("#element").screenshot(path="element.png")

# Page info
title = await page.title()
url = page.url
content = await page.content()

# Multiple pages/tabs
page2 = await browser.new_page()

# File upload
await page.locator("input[type='file']").set_input_files("file.pdf")
```

### BLOCKED — page.evaluate()

```python
# DON'T DO THIS — will hang or timeout:
await page.evaluate("document.title")
await page.evaluate("() => window.innerWidth")
await page.evaluate("el => el.textContent", element)
```

**Why**: The CDP stealth patch isolates `Runtime.enable` from the page context. This prevents bot detectors (Cloudflare Turnstile, DataDome) from seeing `executionContextCreated` events, but it also blocks JS evaluation from automation code.

### WORKAROUNDS for page.evaluate()

**Instead of evaluate, use locator methods:**

```python
# BAD:  await page.evaluate("document.title")
# GOOD:
title = await page.title()

# BAD:  await page.evaluate("document.querySelector('#price').textContent")
# GOOD:
text = await page.locator("#price").text_content()

# BAD:  await page.evaluate("document.querySelectorAll('.item').length")
# GOOD:
count = await page.locator(".item").count()

# BAD:  await page.evaluate("window.innerWidth")
# GOOD:
from huligan.automation import cdp_viewport_size
vp = await cdp_viewport_size(page)
print(vp["width"], vp["height"])

# BAD:  value = await page.evaluate("document.querySelector('input').value")
# GOOD:
value = await page.locator("input").input_value()

# BAD:  await page.evaluate("window.scrollTo(0, 500)")
# GOOD:
await page.mouse.wheel(0, 500)

# BAD:  await page.evaluate("el => el.getBoundingClientRect()", element)
# GOOD:
box = await page.locator("#element").bounding_box()
# If bounding_box() hangs (connect_over_cdp issue), use CDP helper:
from huligan.automation import cdp_bounding_box
box = await cdp_bounding_box(page, "#element")
```

### BROKEN via connect_over_cdp (Playwright bug, not Huligan)

These methods sometimes hang when connected via CDP (not just Huligan — general Playwright limitation):

```python
# May hang:
await locator.bounding_box()     # Use cdp_bounding_box() instead
page.viewport_size               # Returns None; use cdp_viewport_size()
```

**Fix**: Use CDP helpers from `huligan.automation`:

```python
from huligan.automation import (
    cdp_bounding_box,
    cdp_viewport_size,
    cdp_scroll_y,
    cdp_document_height,
    cdp_is_visible,
    cdp_wait_for_visible,
)

# Element position
box = await cdp_bounding_box(page, "button.submit")
# {"x": 100, "y": 200, "width": 80, "height": 40}

# Viewport
vp = await cdp_viewport_size(page)
# {"width": 1920, "height": 1080}

# Scroll position
y = await cdp_scroll_y(page)

# Document height (for scrolling logic)
height = await cdp_document_height(page)

# Wait for element to appear
visible = await cdp_wait_for_visible(page.locator("#result"), timeout=10)
```

## Complete Examples

### Login to a website

```python
import asyncio
from huligan import Browser

async def main():
    async with Browser(proxy="socks5://user:pass@ip:port") as browser:
        page = await browser.new_page()
        await page.goto("https://example.com/login")

        # Fill form using locators (NOT evaluate)
        await page.locator("input[name='email']").fill("user@example.com")
        await page.locator("input[name='password']").fill("password123")
        await page.locator("button[type='submit']").click()

        # Wait for redirect
        await page.wait_for_url("**/dashboard**")
        print(f"Logged in: {page.url}")

asyncio.run(main())
```

### Scrape data from a page

```python
async def scrape(browser):
    page = await browser.new_page()
    await page.goto("https://example.com/products")
    await page.wait_for_selector(".product-card")

    # Get all product names using locators
    cards = page.locator(".product-card")
    count = await cards.count()

    products = []
    for i in range(count):
        name = await cards.nth(i).locator(".name").text_content()
        price = await cards.nth(i).locator(".price").text_content()
        products.append({"name": name, "price": price})

    return products
```

### Human-like interaction (bypass bot detection)

```python
from huligan import Browser
from huligan.automation import (
    human_like_mouse_click,
    human_like_type,
    human_like_hotkey,
)

async def main():
    async with Browser(proxy="socks5://user:pass@ip:port") as browser:
        page = await browser.new_page()
        await page.goto("https://example.com/login")

        # Click with curved mouse movement (not instant teleport)
        email_field = page.locator("input[name='email']")
        await human_like_mouse_click(email_field, speed_mode="medium")

        # Type with human-like delays and occasional pauses
        await human_like_type(email_field, "user@example.com", speed_mode="medium")

        # Tab to next field
        await human_like_hotkey(page.keyboard, "Tab")
        password_field = page.locator("input[name='password']")
        await human_like_type(password_field, "password123", speed_mode="slow")

        # Click submit with mouse
        submit = page.locator("button[type='submit']")
        await human_like_mouse_click(submit, speed_mode="fast")

asyncio.run(main())
```

### Speed modes for human_like functions

```python
# Mouse click speeds:
await human_like_mouse_click(locator, speed_mode="fast")    # Quick, less jitter
await human_like_mouse_click(locator, speed_mode="medium")  # Balanced
await human_like_mouse_click(locator, speed_mode="slow")    # Careful, more curves

# Typing speeds:
await human_like_type(locator, text, speed_mode="fast")    # ~50ms between keys
await human_like_type(locator, text, speed_mode="medium")  # ~100ms, occasional pauses
await human_like_type(locator, text, speed_mode="slow")    # ~200ms, word pauses, rare typos
await human_like_type(locator, text, speed_mode="paste")   # Instant (clipboard paste)
```

### Working with iframes

```python
# Access iframe content via locator
frame = page.frame_locator("iframe#captcha")
await frame.locator("button.verify").click()
```

### Handling dialogs (alert, confirm, prompt)

```python
# Set up dialog handler BEFORE triggering
page.on("dialog", lambda dialog: dialog.accept())
await page.locator("#delete-btn").click()
```

### Receiving downloads

Playwright's `accept_downloads=True` flag lives on `browser_context.new_context()`, which Huligan doesn't expose — `Browser` attaches over CDP to an already-running Chrome and the default context is implicit. Two paths work in practice:

**Path A — `page.expect_download()` (preferred).** With `connect_over_cdp`, the existing context already accepts downloads; you just need to capture the `Download` object as it's triggered:

```python
from huligan import Browser

async with Browser(proxy=...) as browser:
    page = await browser.new_page()
    await page.goto("https://file-examples.com/.../sample.pdf")
    async with page.expect_download(timeout=30000) as dl_info:
        await page.locator("a.download-btn").click()
    download = await dl_info.value
    await download.save_as("./downloads/file.pdf")
    print(f"Saved {download.suggested_filename} ({await download.path()})")
```

**Path B — `Page.setDownloadBehavior` via CDP (fallback / batch).** When you can't easily wrap the click in `expect_download` (multi-tab flows, automatic-download pages, headless without a UI hook), tell Chrome up front where to write:

```python
from pathlib import Path

page = await browser.new_page()
client = await page.context.new_cdp_session(page)
download_dir = Path("./downloads").resolve()
download_dir.mkdir(exist_ok=True)
await client.send("Page.setDownloadBehavior", {
    "behavior": "allow",
    "downloadPath": str(download_dir),
})
await page.goto("https://example.com/auto-download")
# Chrome writes the file to ./downloads/ without firing a Download event.
# Poll the directory yourself or wait for a known filename.
```

Path B is also the only way to capture downloads triggered by `target=_blank` links that Playwright doesn't always surface as `Download` events on CDP-connected browsers.

**Full runnable example:** `examples/example_download.py`.

### Network interception

```python
# Block images for faster loading
await page.route("**/*.{png,jpg,jpeg,gif}", lambda route: route.abort())

# Intercept API responses
async def handle_response(response):
    if "/api/data" in response.url:
        data = await response.json()
        print(f"API data: {data}")

page.on("response", handle_response)
```

## Cheatsheet: evaluate() → locator replacement

| page.evaluate() (BLOCKED) | Locator alternative (WORKS) |
|---|---|
| `page.evaluate("document.title")` | `await page.title()` |
| `page.evaluate("document.URL")` | `page.url` |
| `page.evaluate("document.body.innerHTML")` | `await page.content()` |
| `page.evaluate("el.textContent", el)` | `await locator.text_content()` |
| `page.evaluate("el.innerHTML", el)` | `await locator.inner_html()` |
| `page.evaluate("el.value", el)` | `await locator.input_value()` |
| `page.evaluate("el.getAttribute('href')", el)` | `await locator.get_attribute("href")` |
| `page.evaluate("el.classList.contains('active')", el)` | `await locator.evaluate("el => el.classList.contains('active')")` * |
| `page.evaluate("document.querySelectorAll('.x').length")` | `await page.locator(".x").count()` |
| `page.evaluate("window.scrollTo(0, y)")` | `await page.mouse.wheel(0, y)` |
| `page.evaluate("window.innerWidth")` | `await cdp_viewport_size(page)` |
| `page.evaluate("el.click()", el)` | `await locator.click()` |
| `page.evaluate("el.focus()", el)` | `await locator.focus()` |
| `page.evaluate("el.scrollIntoView()", el)` | `await locator.scroll_into_view_if_needed()` |

\* `locator.evaluate()` may work in some cases where `page.evaluate()` doesn't — it uses a different CDP path.

## When you really need to run JS (escape hatches)

The cheatsheet above covers ~90% of cases. For the rest — when you actually need to compute something in JS that has no locator equivalent (canvas fingerprinting, custom DOM walks, math) — two patterns work because they don't go through CDP `Runtime.evaluate`.

### Pattern 1: `page.add_init_script()` for main-world setup

Runs in main world BEFORE any page script on every navigation. Use it to install hooks, stub APIs, or pre-compute values.

```python
await page.add_init_script(
    "window.__marker = 'init_ran_' + navigator.userAgent.length;"
)
await page.goto("https://example.com")
# Read the result via DOM (e.g. the page renders it, or you injected it into the DOM yourself)
```

### Pattern 2: `data:` URL with inline `<script>` writing to the DOM

If you need to run arbitrary JS and read the result, navigate to a `data:` URL whose `<script>` writes the result to `document.title` (or a hidden `<div>`), then read it via `page.title()` / `locator.text_content()`.

```python
import urllib.parse

js_html = """
<!doctype html><title>pending</title>
<script>
  const c = document.createElement('canvas');
  c.width = 280; c.height = 60;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#f60';
  ctx.fillText('test', 4, 35);
  document.title = String(c.toDataURL().length);
</script>
"""
url = "data:text/html;charset=utf-8," + urllib.parse.quote(js_html)
await page.goto(url)
result = await page.title()  # e.g. "182"
```

This works because the `<script>` tag executes inside the page's normal V8 isolate — the stealth patch only blocks **CDP-injected** evaluate, not page-authored JS.

### What still doesn't work

A python-side stress loop that calls `page.evaluate()` per iteration is **fundamentally impossible** with our patched chrome — every iteration goes through `Runtime.evaluate` and hangs to the timeout. If you need to stress-test something (canvas, audio, WebGL stability), do it inside a single page that loops in JS and writes progress to `document.title`, then poll the title from python.

## CDP Helpers Reference

Available from `huligan.automation`:

| Function | Description |
|----------|-------------|
| `cdp_bounding_box(page, selector)` | Element position/size via CDP DOM.getBoxModel |
| `cdp_bounding_box_locator(locator)` | Same but accepts Playwright Locator (tries native first) |
| `cdp_viewport_size(page)` | Viewport width/height via CDP Page.getLayoutMetrics |
| `cdp_scroll_y(page)` | Current scroll Y position |
| `cdp_document_height(page)` | Total document height |
| `cdp_is_visible(page, selector)` | Check if element exists and has non-zero size |
| `cdp_wait_for_visible(locator, timeout)` | Wait for element with fallback polling |
| `cleanup_cdp_session(page)` | Remove cached CDP session (call when page closes) |
