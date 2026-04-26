"""
Huligan SDK — Handling Cloudflare Turnstile challenges.

Huligan's C++ patches make the browser appear as a genuine Chrome instance,
so Cloudflare Turnstile challenges typically auto-solve without user
interaction. This example shows how to:

  1. Navigate to a Cloudflare-protected page
  2. Detect the Turnstile challenge
  3. Wait for it to auto-solve
  4. Retry if the challenge fails

IMPORTANT: Do NOT use page.evaluate() — it is blocked by CDP stealth patches.
Use locator methods for all DOM interaction.
"""
import asyncio
from huligan import Browser


PROXY = "socks5://user:pass@ip:port"

# Replace with the actual Cloudflare-protected URL
TARGET_URL = "https://example.com/protected-page"

# Maximum number of retry attempts if the challenge fails
MAX_RETRIES = 3

# How long to wait for the challenge to auto-solve (seconds)
CHALLENGE_TIMEOUT_MS = 30000


async def wait_for_turnstile(page, attempt: int) -> bool:
    """
    Wait for Cloudflare Turnstile to appear and auto-solve.

    Returns True if the challenge was solved (page loaded successfully),
    False if it timed out or failed.
    """
    print(f"  Attempt {attempt}: checking for Turnstile challenge...")

    # Turnstile renders inside an iframe with a known selector.
    # The challenge iframe typically has this attribute.
    turnstile_frame = page.locator('iframe[src*="challenges.cloudflare.com"]')

    # Check if a Turnstile challenge is present
    try:
        await turnstile_frame.wait_for(state="attached", timeout=5000)
        print("  Turnstile challenge detected — waiting for auto-solve...")
    except Exception:
        # No challenge iframe found — might already be solved or no challenge needed
        print("  No Turnstile challenge detected.")
        return True

    # Wait for the challenge to resolve. When solved, one of these happens:
    #   a) The page redirects to the actual content
    #   b) The challenge iframe disappears
    #   c) A success callback fires and the page content loads

    # Strategy 1: Wait for the challenge iframe to disappear
    try:
        await turnstile_frame.wait_for(state="detached", timeout=CHALLENGE_TIMEOUT_MS)
        print("  Challenge iframe removed — likely solved!")
        return True
    except Exception:
        pass

    # Strategy 2: Check if we got redirected away from the challenge page
    # Cloudflare often shows a challenge page at a different URL
    if "challenge" not in page.url.lower():
        print(f"  Redirected to: {page.url} — challenge appears solved.")
        return True

    # Strategy 3: Look for content that only appears after the challenge
    # Adjust this selector to match your target site's actual content
    content = page.locator("main, article, .content, #app")
    if await content.count() > 0:
        print("  Main content detected — page loaded successfully.")
        return True

    print("  Challenge did not resolve within timeout.")
    return False


async def navigate_with_cf_bypass(browser, url: str) -> object:
    """
    Navigate to a Cloudflare-protected URL with retry logic.

    Returns the page object if successful, raises RuntimeError if all retries fail.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        page = await browser.new_page()

        try:
            # Navigate to the protected page
            print(f"\nNavigating to {url} (attempt {attempt}/{MAX_RETRIES})...")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Wait for any network activity to settle
            await page.wait_for_load_state("networkidle", timeout=15000)

            # Check if Turnstile challenge appears and wait for it
            solved = await wait_for_turnstile(page, attempt)

            if solved:
                # Final verification: wait for the page to fully load
                await page.wait_for_load_state("load", timeout=10000)
                print(f"  Page loaded: {await page.title()}")
                return page

            # Challenge failed — close page and retry
            print(f"  Retrying in 3 seconds...")
            await page.close()
            await asyncio.sleep(3)

        except Exception as e:
            print(f"  Error on attempt {attempt}: {e}")
            try:
                await page.close()
            except Exception:
                pass
            if attempt < MAX_RETRIES:
                await asyncio.sleep(3)

    raise RuntimeError(f"Failed to bypass Cloudflare after {MAX_RETRIES} attempts")


async def main():
    print("Huligan — Cloudflare Turnstile bypass example")
    print("=" * 50)

    async with Browser(proxy=PROXY) as browser:
        try:
            page = await navigate_with_cf_bypass(browser, TARGET_URL)

            # At this point the page is loaded past Cloudflare.
            # Extract content using locators (NOT page.evaluate).
            title = await page.title()
            print(f"\nSuccessfully loaded: {title}")
            print(f"Final URL: {page.url}")

            # Example: extract the first heading on the page
            h1 = page.locator("h1")
            if await h1.count() > 0:
                heading_text = await h1.first.text_content()
                print(f"Page heading: {heading_text}")

            # Take a screenshot for verification
            await page.screenshot(path="cloudflare_solved.png")
            print("Screenshot saved: cloudflare_solved.png")

        except RuntimeError as e:
            print(f"\nFailed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
