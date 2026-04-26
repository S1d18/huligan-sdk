"""
Huligan SDK — Automated fingerprint verification on browserscan.net.

Launches an antidetect browser, navigates to browserscan.net, waits for
the fingerprint analysis to complete, then extracts and reports key values.

This is useful for verifying that your fingerprint profile is consistent
and not flagged as suspicious.

IMPORTANT: Do NOT use page.evaluate() — it is blocked by CDP stealth patches.
All DOM access uses locator methods.
"""
import asyncio
from huligan import Browser


PROXY = "socks5://user:pass@ip:port"


async def extract_text(page, selector: str, timeout: int = 10000) -> str:
    """
    Safely extract text content from a selector.
    Returns the text or "N/A" if the element is not found.
    """
    loc = page.locator(selector)
    try:
        await loc.first.wait_for(state="visible", timeout=timeout)
        text = await loc.first.text_content()
        return text.strip() if text else "N/A"
    except Exception:
        return "N/A"


async def main():
    print("Huligan — Fingerprint verification on browserscan.net")
    print("=" * 55)

    async with Browser(proxy=PROXY) as browser:
        page = await browser.new_page()

        # Navigate to browserscan.net
        print("Opening browserscan.net...")
        await page.goto("https://www.browserscan.net/", wait_until="domcontentloaded")

        # BrowserScan takes time to analyze the fingerprint.
        # Wait for the results section to appear.
        print("Waiting for fingerprint analysis to complete...")

        # Wait for the main results container to be visible.
        # BrowserScan uses various class names — look for the IP display
        # which is one of the first results to appear.
        try:
            await page.locator(".ip-info, .info-item, [class*='result']").first.wait_for(
                state="visible", timeout=30000
            )
        except Exception:
            print("Warning: results container not detected, proceeding anyway...")

        # Give the page extra time for all checks to finish (canvas, WebGL, etc.)
        await page.wait_for_timeout(8000)

        # Extract key fingerprint values using locators.
        # BrowserScan layout may change — adjust selectors as needed.
        print("\nExtracting results...\n")

        # IP address — usually in a prominent section at the top
        ip_addr = await extract_text(page, ".ip-value, .ip-info .value, [class*='ip'] .value")

        # Browser info
        browser_info = await extract_text(page, "[class*='browser'] .value, .browser-info .value")

        # OS info
        os_info = await extract_text(page, "[class*='os'] .value, .os-info .value")

        # Try to get all info items as a fallback approach:
        # BrowserScan lists results in rows — extract whatever is available
        info_items = page.locator(".info-item, .detect-item, [class*='check-item']")
        item_count = await info_items.count()

        detected_values = {}
        for i in range(min(item_count, 20)):
            item = info_items.nth(i)
            try:
                text = await item.text_content()
                if text:
                    detected_values[f"item_{i}"] = text.strip()[:100]
            except Exception:
                continue

        # Take a screenshot for manual review
        screenshot_path = "browserscan_results.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"Screenshot saved: {screenshot_path}")

        # Print the summary report
        print("\n" + "=" * 55)
        print("FINGERPRINT VERIFICATION REPORT")
        print("=" * 55)
        print(f"  URL:      {page.url}")
        print(f"  Title:    {await page.title()}")
        print(f"  IP:       {ip_addr}")
        print(f"  Browser:  {browser_info}")
        print(f"  OS:       {os_info}")

        if browser.fingerprint_profile:
            fp = browser.fingerprint_profile
            print("\n  --- Expected (from profile) ---")
            print(f"  Screen:   {fp.screen_width}x{fp.screen_height}")
            print(f"  CPU:      {fp.cpu_cores} cores")
            print(f"  RAM:      {fp.device_memory} GB")
            print(f"  GPU:      {fp.webgl_renderer[:60]}...")

        if detected_values:
            print(f"\n  --- Raw detected items ({len(detected_values)}) ---")
            for key, val in detected_values.items():
                # Collapse whitespace for readability
                val_clean = " ".join(val.split())
                print(f"  {val_clean[:80]}")

        if browser.geo:
            print(f"\n  --- GeoIP ---")
            print(f"  Country:  {browser.geo.country_name}")
            print(f"  Timezone: {browser.geo.timezone}")
            print(f"  Language: {browser.geo.language}")

        print("\n" + "=" * 55)
        print("Review the screenshot for detailed results.")


if __name__ == "__main__":
    asyncio.run(main())
