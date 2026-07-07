"""
Huligan SDK — Export/import a portable cookie bundle between profiles.

Different problem than `example_persistent_session.py`: that example reuses
the *same* `user_data_dir` so Chrome remembers a session across restarts.
This example hands a login *between two different profiles* (or two
different machines/teammates) as a single portable JSON file — captured over
CDP (evaluate-free, and it catches httpOnly cookies that document.cookie
can't see). See docs/COOKIES.md for the full rationale.

Requires no extra — export_cookies/import_cookies ship in huligan[playwright].
"""
import asyncio
from pathlib import Path
from huligan import Browser

COOKIE_BUNDLE = "./account_1.cookies.json"

PROXY = "socks5://user:pass@ip:port"
LOGIN_URL = "https://example.com/login"
DASHBOARD_URL = "https://example.com/dashboard"


async def export_from_logged_in_profile():
    """Log in once, then dump this session's cookies to a portable file."""
    print("=== Exporting cookies from a fresh login ===")

    async with Browser(proxy=PROXY, user_data_dir="./sessions/account_1") as browser:
        page = await browser.new_page()
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")

        # Adjust selectors to match your target site.
        await page.locator('input[name="username"]').fill("my_username")
        await page.locator('input[name="password"]').fill("my_password")
        await page.locator('button[type="submit"]').click()
        await page.wait_for_url("**/dashboard**", timeout=15000)
        print(f"Logged in: {page.url}")

        count = await browser.export_cookies(COOKIE_BUNDLE)
        print(f"Exported {count} cookies -> {Path(COOKIE_BUNDLE).resolve()}")


async def import_into_fresh_profile():
    """
    Load the bundle into a brand-new profile (no shared user_data_dir with
    the profile that logged in) and land straight on the dashboard —
    demonstrating the login moved with the file, not the profile directory.
    """
    print("\n=== Importing cookies into a different, fresh profile ===")

    async with Browser(proxy=PROXY, user_data_dir="./sessions/account_1_clone") as browser:
        page = await browser.new_page()

        # Import BEFORE navigating so cookies apply on the first request.
        count = await browser.import_cookies(COOKIE_BUNDLE)
        print(f"Imported {count} cookies from {COOKIE_BUNDLE}")

        await page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
        if "login" in page.url.lower():
            print("Redirected to login — bundle didn't carry a valid session.")
        else:
            print(f"Still logged in via imported cookies: {page.url}")


async def main():
    await export_from_logged_in_profile()
    await import_into_fresh_profile()


if __name__ == "__main__":
    asyncio.run(main())


# --- Attaching to an already-running (persistent/GUI) session ---
#
# `Browser.export_cookies`/`.import_cookies` above need an in-process
# Playwright `Page`, which only exists for a `Browser()` you launched
# yourself. A session started via `huligan.launch_persistent` (what the GUI
# uses) only exposes a remote-debugging CDP port to the caller — use the
# attach-by-port helpers instead, which connect, do the export/import, and
# detach WITHOUT closing the user's live browser:
#
#     from huligan import cookies
#
#     await cookies.export_cookies_to_file(cdp_port, "acc1.cookies.json")
#     await cookies.import_cookies_from_file(cdp_port, "acc1.cookies.json")
#
# See docs/COOKIES.md "Attach by CDP port" for the full recipe.
