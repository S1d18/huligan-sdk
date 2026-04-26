"""
Huligan SDK — Custom fingerprint with pre-generated .conf.

Generate a reproducible fingerprint profile and launch browser with it.
"""
import asyncio
from pathlib import Path
from huligan import Browser, FingerprintGenerator


async def main():
    # Generate a deterministic fingerprint (same seed = same result)
    gen = FingerprintGenerator(seed=12345)
    profile = gen.generate(platform="Win32", gpu_vendor_preference="nvidia")

    # Save to .conf file
    profile_path = Path("my_profile.conf")
    profile_path.write_text(profile.to_conf())
    print(f"Generated profile: {profile_path}")
    print(f"  GPU: {profile.webgl_renderer[:60]}...")
    print(f"  Screen: {profile.screen_width}x{profile.screen_height}")
    print(f"  CPU: {profile.cpu_cores} cores, {profile.device_memory} GB RAM")

    # Launch with the saved profile
    async with Browser(
        proxy="socks5://user:pass@ip:port",
        profile_path=str(profile_path.resolve()),
    ) as browser:
        page = await browser.new_page()
        await page.goto("https://browserscan.net")
        print(f"Title: {await page.title()}")
        await page.wait_for_timeout(30000)


if __name__ == "__main__":
    asyncio.run(main())
