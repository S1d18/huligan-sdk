"""
Huligan SDK — Persistent login sessions across browser restarts.

Demonstrates how to use `user_data_dir` to preserve cookies, localStorage,
and other browser state between launches. This is essential for keeping
accounts logged in without re-entering credentials every time.

Key concept:
    The `user_data_dir` parameter tells Chrome where to store its profile
    data (cookies, cache, localStorage, etc.). By reusing the same directory
    across launches, the browser "remembers" previous sessions.
"""
import asyncio
from pathlib import Path
from huligan import Browser


# Persistent session directory — reused across launches.
# Each account should have its own directory.
SESSION_DIR = "./sessions/account_1"

PROXY = "socks5://user:pass@ip:port"

# Replace with your actual login page URL
LOGIN_URL = "https://example.com/login"
DASHBOARD_URL = "https://example.com/dashboard"


async def first_run():
    """
    First run: log in and let cookies be saved to the session directory.
    """
    print("=== First run: logging in ===")

    async with Browser(
        proxy=PROXY,
        user_data_dir=SESSION_DIR,
    ) as browser:
        page = await browser.new_page()

        # Navigate to login page
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        print(f"Opened: {page.url}")

        # Fill in the login form using locator methods.
        # Adjust selectors to match your target site.
        await page.locator('input[name="username"]').fill("my_username")
        await page.locator('input[name="password"]').fill("my_password")

        # Submit the form
        await page.locator('button[type="submit"]').click()

        # Wait for navigation to the logged-in page.
        # Use a URL pattern or a selector that only appears when logged in.
        await page.wait_for_url("**/dashboard**", timeout=15000)
        print(f"Logged in! Redirected to: {page.url}")

        # Verify we are logged in by checking for a user-specific element
        username_el = page.locator(".user-profile-name")
        if await username_el.count() > 0:
            name = await username_el.text_content()
            print(f"Welcome, {name}!")

        # Cookies and session data are automatically saved to SESSION_DIR
        # when the browser closes.
        print(f"Session saved to: {Path(SESSION_DIR).resolve()}")


async def second_run():
    """
    Second run: open the same site — should still be logged in
    because cookies were preserved in user_data_dir.
    """
    print("\n=== Second run: verifying session persists ===")

    async with Browser(
        proxy=PROXY,
        user_data_dir=SESSION_DIR,
    ) as browser:
        page = await browser.new_page()

        # Go directly to a page that requires authentication
        await page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
        print(f"Opened: {page.url}")

        # If session persisted, we should land on the dashboard (not redirected to login)
        if "login" in page.url.lower():
            print("Session expired or not saved — redirected to login page.")
        else:
            print("Session persisted! Still logged in.")
            # Extract some data to confirm
            username_el = page.locator(".user-profile-name")
            if await username_el.count() > 0:
                name = await username_el.text_content()
                print(f"Logged in as: {name}")


async def main():
    # First launch: perform login
    await first_run()

    # Second launch: verify session is preserved
    await second_run()

    print("\n=== Done ===")
    print(f"Session directory: {Path(SESSION_DIR).resolve()}")
    print("Delete this directory to clear the session.")


if __name__ == "__main__":
    asyncio.run(main())
