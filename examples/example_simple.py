"""
Huligan SDK — Minimal example.

Launch an antidetect browser with proxy and open a page.
"""
import asyncio
from huligan import Browser


async def main():
    async with Browser(
        proxy="socks5://user:pass@ip:port",
        # chrome_path="C:/huligan-chrome/chrome.exe",  # uncomment if not auto-detected
    ) as browser:
        page = await browser.new_page()
        await page.goto("https://browserscan.net")
        print(f"Title: {await page.title()}")
        await page.wait_for_timeout(30000)


if __name__ == "__main__":
    asyncio.run(main())
