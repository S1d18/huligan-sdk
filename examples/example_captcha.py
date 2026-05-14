"""
Huligan SDK — Solving CAPTCHAs via a third-party solver service.

The CaptchaSolver wrapper only handles the solver-API side: extract
the sitekey from the page, send it to 2Captcha / AntiCaptcha /
CapSolver, poll until the token comes back. Injecting the token
into the page is the caller's job — under paranoid mode
``page.evaluate()`` is blocked, so we put the token into the
response textarea via ``locator.fill()`` instead.

Requires the captcha extra:

    pip install huligan[captcha]

Set credentials via env or pass them explicitly:

    export HULIGAN_CAPTCHA_PROVIDER=2captcha
    export HULIGAN_CAPTCHA_API_KEY=your_api_key_here
"""
import asyncio
import re

from huligan import Browser, CaptchaSolver


TARGET_URL = "https://www.google.com/recaptcha/api2/demo"


async def find_recaptcha_sitekey(page) -> str:
    """Pull the sitekey out of the rendered HTML without evaluate()."""
    html = await page.content()
    m = re.search(r'data-sitekey=["\']([^"\']+)["\']', html)
    if not m:
        raise RuntimeError("No reCAPTCHA sitekey found on page")
    return m.group(1)


async def main():
    # from_env() reads HULIGAN_CAPTCHA_PROVIDER + HULIGAN_CAPTCHA_API_KEY
    solver = CaptchaSolver.from_env()
    print(f"Solver balance: ${await solver.get_balance():.2f}")

    async with Browser(proxy="socks5://user:pass@ip:port") as browser:
        page = await browser.new_page()
        await page.goto(TARGET_URL, wait_until="domcontentloaded")

        sitekey = await find_recaptcha_sitekey(page)
        print(f"Found sitekey: {sitekey}")

        token = await solver.solve_recaptcha_v2(
            sitekey=sitekey,
            page_url=page.url,
            timeout=180,
        )
        print(f"Got token: {token[:40]}...")

        # The response textarea is normally display:none — locator.fill()
        # still writes the value because Playwright does not require
        # visibility for hidden form inputs. Tested against 2captcha's
        # demo page (https://2captcha.com/demo/recaptcha-v2).
        await page.locator("textarea#g-recaptcha-response").fill(token)

        # Submit the form. Use a click on the submit button rather than
        # form.submit() via evaluate, which paranoid mode would block.
        await page.locator("button[type=submit], input[type=submit]").first.click()

        await page.wait_for_load_state("load", timeout=15000)
        print(f"After submit: {page.url}")


if __name__ == "__main__":
    asyncio.run(main())
