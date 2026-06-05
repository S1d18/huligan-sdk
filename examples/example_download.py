"""
Huligan SDK — Receiving file downloads.

Playwright's `accept_downloads=True` lives on `new_context()`, which Huligan
doesn't expose because Browser attaches to Chrome over CDP and the default
context is implicit. Two paths cover the gap:

  Path A — `page.expect_download()` to capture the Download object.
           Works for the typical "user clicks a link, file arrives" flow.

  Path B — `Page.setDownloadBehavior` via CDP to redirect the download
           directory ahead of time. Use this when the download is triggered
           automatically, comes from `target=_blank`, or you don't want to
           wrap each click in expect_download().

Run with no proxy by leaving PROXY = None.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from huligan import Browser


PROXY: str | None = None  # e.g. "socks5://user:pass@ip:port"

DOWNLOAD_DIR = Path("./downloads").resolve()
DOWNLOAD_URL = "https://file-examples.com/wp-content/storage/2017/10/file_example_JPG_100kB.jpg"


async def path_a_expect_download():
    """
    Capture a click-triggered download via page.expect_download().
    """
    print("=== Path A: page.expect_download() ===")
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    async with Browser(proxy=PROXY) as browser:
        page = await browser.new_page()
        # Use a small known-good test file so the demo finishes quickly.
        await page.goto("https://file-examples.com/index.php/sample-images-download/",
                        wait_until="domcontentloaded")

        # Find any "Download" link on the page and click it inside expect_download.
        link = page.locator("a[href$='.jpg']").first
        await link.wait_for(state="visible", timeout=15000)

        async with page.expect_download(timeout=30000) as dl_info:
            await link.click()
        download = await dl_info.value

        target = DOWNLOAD_DIR / download.suggested_filename
        await download.save_as(target)
        print(f"  Saved: {target} ({target.stat().st_size} bytes)")


async def path_b_cdp_download_behavior():
    """
    Pre-configure Chrome's download directory via CDP, then trigger the
    download by navigating directly to the file URL. Works even when no
    Download event fires (target=_blank, auto-download pages).
    """
    print("\n=== Path B: Page.setDownloadBehavior via CDP ===")
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    async with Browser(proxy=PROXY) as browser:
        page = await browser.new_page()
        client = await page.context.new_cdp_session(page)
        await client.send("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": str(DOWNLOAD_DIR),
        })

        # Directly navigate to a file URL — Chrome streams it to DOWNLOAD_DIR.
        # We don't await the navigation (it cancels with net::ERR_ABORTED once
        # Chrome decides it's a download), we just give it time to land.
        try:
            await page.goto(DOWNLOAD_URL, timeout=15000)
        except Exception:
            pass  # navigation aborted because Chrome treated it as a download

        # Poll DOWNLOAD_DIR for a new file.
        deadline = asyncio.get_event_loop().time() + 20.0
        new_files: "list[Path]" = []
        baseline = {p.name for p in DOWNLOAD_DIR.glob("*") if p.is_file()}
        while asyncio.get_event_loop().time() < deadline:
            files = [
                p for p in DOWNLOAD_DIR.glob("*")
                if p.is_file() and not p.name.endswith(".crdownload") and p.name not in baseline
            ]
            if files:
                new_files = files
                break
            await asyncio.sleep(0.5)

        if not new_files:
            print("  WARNING: no new file detected within 20s.")
            return

        for f in new_files:
            print(f"  Saved: {f} ({f.stat().st_size} bytes)")


async def main():
    await path_a_expect_download()
    await path_b_cdp_download_behavior()
    print(f"\nDone. All files in: {DOWNLOAD_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
