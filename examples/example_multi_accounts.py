"""
Huligan SDK — Multiple browser instances with different proxies.

Each browser gets a unique fingerprint and GeoIP-matching locale.
"""
import asyncio
from huligan import Browser


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
        print(f"Browser started: PID={b.pid}, CDP={b.cdp_url}")

    # Each browser has a unique fingerprint + matching geolocation
    for i, b in enumerate(browsers):
        page = await b.new_page()
        await page.goto("https://browserscan.net")
        print(f"Browser {i}: {await page.title()}")

    # Clean up
    for b in browsers:
        await b.close()


if __name__ == "__main__":
    asyncio.run(main())
