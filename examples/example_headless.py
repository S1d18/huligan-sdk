"""
Huligan SDK — Headless mode + headed/headless detection comparison.

Huligan supports headless via `Browser(headless=True)`, which launches the
patched Chrome with `--headless=new` (the new headless mode that shares the
real render stack — not the legacy headless that's trivially detected).

This script launches the same fingerprint twice — once headed, once headless —
against browserscan.net and prints both screenshots so an operator can sanity
check that the headless run scores the same (≥97%) as the headed one.

Run with no proxy by leaving PROXY = None.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from huligan import Browser, FingerprintProfile


PROXY: str | None = None  # e.g. "socks5://user:pass@ip:port"

OUT_DIR = Path("./headless_check").resolve()
PROFILE_PATH = OUT_DIR / "shared_profile.conf"
HEADED_PNG = OUT_DIR / "browserscan_headed.png"
HEADLESS_PNG = OUT_DIR / "browserscan_headless.png"

# Re-use the SAME fingerprint for both runs so any difference in the resulting
# score is attributable to headless mode itself, not to per-launch fingerprint
# randomness. We generate one .conf from a fixed seed and feed it to both.
FINGERPRINT_SEED = 42


async def run(label: str, *, headless: bool, screenshot: Path) -> None:
    print(f"--- {label} (headless={headless}) ---")

    async with Browser(
        proxy=PROXY,
        headless=headless,
        profile_path=PROFILE_PATH,
    ) as browser:
        page = await browser.new_page()
        await page.goto("https://www.browserscan.net/", wait_until="domcontentloaded")

        # browserscan runs canvas/WebGL/audio checks on load — give it room.
        try:
            await page.locator(".ip-info, .info-item, [class*='result']").first.wait_for(
                state="visible", timeout=30000
            )
        except Exception:
            print("  WARNING: results container not detected within 30s")
        await page.wait_for_timeout(8000)

        await page.screenshot(path=str(screenshot), full_page=True)
        print(f"  Title:    {await page.title()}")
        print(f"  URL:      {page.url}")
        print(f"  Saved:    {screenshot}")


async def main():
    OUT_DIR.mkdir(exist_ok=True)
    profile = FingerprintProfile.from_seed(FINGERPRINT_SEED)
    PROFILE_PATH.write_text(profile.to_conf(), encoding="utf-8")
    print(f"Profile written: {PROFILE_PATH}\n")

    await run("Headed baseline", headless=False, screenshot=HEADED_PNG)
    await run("Headless run",    headless=True,  screenshot=HEADLESS_PNG)

    print()
    print("Side-by-side review:")
    print(f"  headed:   {HEADED_PNG}")
    print(f"  headless: {HEADLESS_PNG}")
    print()
    print("Open both screenshots and confirm the BrowserScan score and")
    print("'Robot Detection' / canvas / WebGL panels match. Any drop on the")
    print("headless side means stealth coverage is regressing for --headless=new.")


if __name__ == "__main__":
    asyncio.run(main())
