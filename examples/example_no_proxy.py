"""
Huligan SDK — Local launch without proxy.

Useful for development and testing.
"""
import asyncio
from huligan import Browser


async def main():
    # No proxy — just launch with a random fingerprint
    async with Browser() as browser:
        page = await browser.new_page()
        await page.goto("https://browserscan.net")
        print(f"Title: {await page.title()}")

        # Take screenshot
        await page.screenshot(path="screenshot.png")
        print("Screenshot saved to screenshot.png")

        await page.wait_for_timeout(10000)


if __name__ == "__main__":
    asyncio.run(main())
