"""
Huligan SDK — Human-like automation.

Uses automation module for realistic mouse movements and typing.
Requires: pip install huligan[automation]
"""
import asyncio
from huligan import Browser
from huligan.automation import human_like_mouse_click, human_like_type, human_like_hotkey


async def main():
    async with Browser(proxy="socks5://user:pass@ip:port") as browser:
        page = await browser.new_page()
        await page.goto("https://example.com/login")

        # Human-like click on input field (smooth curved mouse movement)
        email_input = page.locator("input[name='email']")
        await human_like_mouse_click(email_input, speed_mode="medium")

        # Human-like typing (random delays, occasional pauses)
        await human_like_type(email_input, "user@example.com", speed_mode="medium")

        # Tab to password field
        await human_like_hotkey(page.keyboard, "Tab")
        password_input = page.locator("input[name='password']")
        await human_like_type(password_input, "mypassword123", speed_mode="slow")

        # Click submit
        submit_btn = page.locator("button[type='submit']")
        await human_like_mouse_click(submit_btn, speed_mode="fast")

        await page.wait_for_timeout(5000)


if __name__ == "__main__":
    asyncio.run(main())
