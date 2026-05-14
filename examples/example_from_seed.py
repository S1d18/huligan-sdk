"""
Quick-start: build a deterministic profile from a single integer seed.

Same seed + same SDK major version → same profile. Useful when you want
a one-line profile factory without managing .conf files manually.

`audio_noise_seed=0` is enforced regardless of seed.
"""
import asyncio
from pathlib import Path

from huligan import Browser, FingerprintProfile


async def main():
    # One integer in, full 50-field profile out.
    profile = FingerprintProfile.from_seed(
        seed=12345,                # any non-negative int
        platform="Win32",          # or "MacIntel", "Linux x86_64"
        gpu_vendor_preference=None # or "nvidia" / "amd" / "intel"
    )

    print(f"GPU:        {profile.webgl_renderer}")
    print(f"Screen:     {profile.screen_width}x{profile.screen_height}")
    print(f"CPU cores:  {profile.cpu_cores}")
    print(f"RAM (GB):   {profile.device_memory}")
    print(f"Audio seed: {profile.audio_noise_seed}  (must be 0)")

    # Persist the profile and launch a browser with it.
    conf_path = Path("seed_12345.conf").resolve()
    conf_path.write_text(profile.to_conf())

    async with Browser(profile_path=str(conf_path)) as browser:
        page = await browser.new_page()
        await page.goto("https://browserscan.net")
        await page.wait_for_timeout(15000)


if __name__ == "__main__":
    asyncio.run(main())
