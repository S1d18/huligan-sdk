"""Portable profile bundle: fingerprint + login in one file.

Export an identity (its .conf fingerprint AND cookies) to a single .hbundle, then
recreate it elsewhere and land on the site already authenticated.

Run the export once while logged in, copy the .hbundle to the target machine, then
run the import there. Both halves are shown in one file for reference; in practice
they run on different machines.
"""

import asyncio

from huligan import Browser, extract_profile_bundle

PROXY = "socks5://user:pass@ip:port"
BUNDLE = "acc.hbundle"
SITE = "https://www.example.com/account"


async def export_side():
    """Source machine: you are already logged in under this profile."""
    async with Browser(proxy=PROXY, profile_path="acc.conf",
                       user_data_dir="./ud/acc") as b:
        page = await b.new_page()
        await page.goto(SITE)                     # ensure the session is warm
        n = await b.export_profile_bundle(BUNDLE, domains=["example.com"])
        print(f"Exported {n} cookies + fingerprint -> {BUNDLE}")


async def import_side():
    """Target machine: no prior login. Recreate identity + session from the bundle."""
    # 1. Unpack the fingerprint BEFORE launch — Chrome reads it at startup.
    info = extract_profile_bundle(BUNDLE, conf_out="acc.conf")
    print(f"Fingerprint -> {info['conf_path']} (cookies in bundle: {info['cookie_count']})")

    # 2. Launch with that identity, restore cookies, then navigate.
    async with Browser(proxy=PROXY, profile_path="acc.conf") as b:
        page = await b.new_page()
        await b.import_profile_bundle(BUNDLE)      # BEFORE goto
        await page.goto(SITE)
        print("Title after restore:", await page.title())
        await page.wait_for_timeout(15000)


async def main():
    await export_side()
    await import_side()


if __name__ == "__main__":
    asyncio.run(main())
