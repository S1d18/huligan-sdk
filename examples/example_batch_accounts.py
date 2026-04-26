"""
Huligan SDK — Batch account management with ProfilePool.

Pre-generate N profiles, then reuse them across sessions.
Same seed = same profile = consistent fingerprint per account.
"""
import asyncio
from pathlib import Path
from huligan import Browser
from huligan.profile_pool import ProfilePool, ProfilePoolConfig


async def main():
    # Step 1: Generate pool of 10 profiles (only on first run)
    pool = ProfilePool(ProfilePoolConfig(
        pool_size=10,
        pool_dir=Path("./my_profiles_pool"),
        platforms=["Win32"],
    ))
    pool.generate_pool()  # Skips if pool already exists
    print(f"Pool ready: {len(pool)} profiles")

    # Step 2: Launch browser with profile from pool
    # Use get_by_index for consistent mapping: account #3 always gets profile #3
    account_id = 3
    profile_path = pool.get_by_index(account_id)
    print(f"Account #{account_id} → {profile_path.name}")

    async with Browser(
        proxy="socks5://user:pass@ip:port",
        profile_path=str(profile_path),
        user_data_dir=f"./user_data/account_{account_id}",  # Persistent cookies/sessions
    ) as browser:
        page = await browser.new_page()
        await page.goto("https://browserscan.net")
        await page.wait_for_timeout(30000)


if __name__ == "__main__":
    asyncio.run(main())
