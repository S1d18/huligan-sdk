"""
Spin up a realistic identity in one line via named templates.

A template bundles a curated GPU, screen, locale, timezone, and
hardware spec so callers don't have to know which fields look
plausible together. ``audio_noise_seed=0`` is preserved.
"""
import asyncio
from pathlib import Path

from huligan import Browser, FingerprintProfile
from huligan.templates import TEMPLATE_DESCRIPTIONS, list_templates


def print_all_templates() -> None:
    print("Available profile templates:")
    print("-" * 64)
    for name, desc in list_templates():
        print(f"  {name}")
        print(f"    {desc}")
    print()


def inspect(name: str, seed: int) -> FingerprintProfile:
    p = FingerprintProfile.template(name, seed=seed)
    print(f"[{name}] seed={seed}")
    print(f"  platform   : {p.platform}")
    print(f"  screen     : {p.screen_width}x{p.screen_height} @ {p.device_pixel_ratio}x")
    print(f"  cpu/ram    : {p.cpu_cores} cores / {p.device_memory} GB")
    print(f"  webgl      : {p.webgl_renderer}")
    print(f"  timezone   : {p.timezone}")
    print(f"  languages  : {p.languages}")
    print(f"  audio_seed : {p.audio_noise_seed}  (must be 0)")
    print()
    return p


async def main() -> None:
    print_all_templates()

    for name in TEMPLATE_DESCRIPTIONS:
        inspect(name, seed=42)

    # Pick one and launch a browser with it.
    profile = FingerprintProfile.template("usa_verified_facebook", seed=42)
    conf_path = Path("template_usa_verified_facebook.conf").resolve()
    conf_path.write_text(profile.to_conf())

    async with Browser(profile_path=str(conf_path)) as browser:
        page = await browser.new_page()
        await page.goto("https://browserscan.net")
        await page.wait_for_timeout(15000)


if __name__ == "__main__":
    asyncio.run(main())
