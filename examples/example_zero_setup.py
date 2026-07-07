"""
Huligan SDK — Zero-setup Chrome install with a visible progress bar.

`Browser()` already auto-installs the patched Chrome binary on first use —
`find_chrome()` falls through to `ensure_chrome()` as a last resort when no
local/cached/PATH Chrome is found. That means a cold first run silently
blocks for as long as the ~180 MB download takes, with nothing printed.

Call `ensure_chrome()` yourself first (e.g. once at app/installer startup)
to front-load that cost with visible progress, instead of it happening
silently inside your first `Browser()` call. Idempotent and safe to call on
every run — a warm cache returns instantly.
"""
import asyncio
from huligan import Browser, ensure_chrome


def _print_progress(downloaded: int, total: int) -> None:
    if total:
        pct = downloaded * 100 // total
        mb_done = downloaded / 1_048_576
        mb_total = total / 1_048_576
        print(f"\rDownloading Chrome... {pct}% ({mb_done:.1f}/{mb_total:.1f} MB)", end="", flush=True)
    else:
        print(f"\rDownloading Chrome... {downloaded / 1_048_576:.1f} MB", end="", flush=True)


async def main():
    print("Ensuring Huligan Chrome is installed (no-op if already cached)...")
    chrome_path = ensure_chrome(progress_callback=_print_progress)
    print(f"\nChrome ready: {chrome_path}")

    # find_chrome() (called internally by Browser()) now hits the cache
    # `ensure_chrome` just populated — the browser opens with no download wait.
    async with Browser(proxy="socks5://user:pass@ip:port") as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        print(f"Opened: {page.url}")


if __name__ == "__main__":
    asyncio.run(main())
