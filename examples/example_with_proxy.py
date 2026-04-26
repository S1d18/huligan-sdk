"""
Huligan SDK — Full proxy workflow.

Shows the complete chain: proxy → GeoIP → fingerprint → browser.
SDK does everything automatically:
  1. Parses proxy string (supports socks5://, http://, ip:port:user:pass)
  2. Looks up GeoIP → gets timezone, language, coordinates
  3. Generates fingerprint matching the proxy location
  4. Starts local SOCKS5 forwarder (if proxy has auth)
  5. Launches Chrome with all settings applied
"""
import asyncio
from huligan import Browser


async def main():
    # All formats work:
    #   "socks5://user:pass@ip:port"
    #   "http://user:pass@ip:port"
    #   "ip:port:user:pass"
    proxy = "socks5://user:pass@ip:port"

    async with Browser(proxy=proxy) as browser:
        # Check what GeoIP detected
        if browser.geo:
            print(f"GeoIP: {browser.geo.country_name}, "
                  f"TZ={browser.geo.timezone}, "
                  f"Lang={browser.geo.language}")

        # Check generated fingerprint
        if browser.fingerprint_profile:
            fp = browser.fingerprint_profile
            print(f"Fingerprint: {fp.screen_width}x{fp.screen_height}, "
                  f"{fp.cpu_cores} cores, {fp.device_memory}GB RAM")

        print(f"Chrome PID: {browser.pid}")
        print(f"CDP URL: {browser.cdp_url}")
        print(f"Profile: {browser.profile_path}")

        # Open page
        page = await browser.new_page()
        await page.goto("https://browserscan.net")
        print(f"Title: {await page.title()}")
        await page.wait_for_timeout(30000)


if __name__ == "__main__":
    asyncio.run(main())
