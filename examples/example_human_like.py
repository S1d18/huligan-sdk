"""
Huligan SDK — Human-like automation: mouse, keyboard, scroll, idle.

Mouse/keyboard need: pip install huligan[automation]  (pytweening, loguru)
Scroll/idle only need playwright — no extra extra.
"""
import asyncio
from huligan import Browser
from huligan.automation import (
    human_like_mouse_click,
    human_like_type,
    human_like_hotkey,
    human_like_scroll,
    human_like_scroll_to_top,
    idle_mouse_movement,
    simulated_reading_pause,
)


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

        await page.wait_for_url("**/dashboard**", timeout=15000)

        # "The user is reading this" — keeps the cursor jittering instead of
        # going motionless, which behavioural antibots (reCAPTCHA v3,
        # Turnstile) treat as a bot signal.
        await simulated_reading_pause(page, words=80, intensity="natural")

        # Untargeted scroll — e.g. skimming a feed before acting further.
        await human_like_scroll(page, direction="down", distance=1200, speed_mode="medium")
        await idle_mouse_movement(page, duration_s=1.5, intensity="subtle")
        await human_like_scroll_to_top(page)

        await page.wait_for_timeout(2000)


if __name__ == "__main__":
    asyncio.run(main())
