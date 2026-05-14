"""
Huligan SDK — Click an element by natural-language description via a vision LLM.

The VisionAgent screenshots the page, asks a vision-LLM
(OpenAI gpt-4o or Anthropic claude-3.5-sonnet) for pixel coordinates
of the described element, then dispatches a real mouse click at those
coords. Every action routes through low-level Playwright primitives
(``page.mouse.*`` / ``page.keyboard.*``) so it survives huligan's
paranoid CDP stealth, which blocks ``page.evaluate()``.

Requires the vision extra:

    pip install huligan[vision]

Set credentials via env or pass them explicitly:

    export HULIGAN_VISION_PROVIDER=openai          # or anthropic
    export HULIGAN_VISION_API_KEY=sk-...
    export HULIGAN_VISION_MODEL=gpt-4o             # optional override
"""
import asyncio

from huligan import Browser
from huligan.vision import VisionAgent


TARGET_URL = "https://example.com"


async def main():
    # from_env() reads HULIGAN_VISION_{PROVIDER,API_KEY,MODEL}
    agent = VisionAgent.from_env()

    # No proxy here so the example works on a fresh checkout. In real
    # use you'd pass proxy="socks5://user:pass@ip:port" as always.
    async with Browser() as browser:
        page = await browser.new_page()
        await page.goto(TARGET_URL, wait_until="domcontentloaded")

        # 1) Pure locate — get coords, decide what to do next yourself.
        coords = await agent.locate(
            page, "the 'More information...' link near the bottom of the page"
        )
        print(f"Located link at: {coords}")

        # 2) Click by description — agent screenshots, asks LLM, clicks.
        ok = await agent.click(
            page, "the 'More information...' link near the bottom of the page"
        )
        print(f"Click dispatched: {ok}")
        if ok:
            await page.wait_for_load_state("load", timeout=15000)
            print(f"After click: {page.url}")

        # 3) Fill — useful for forms whose inputs don't have stable selectors.
        # (Skipped on example.com which has no form; left here as reference.)
        #
        # await agent.fill(
        #     page,
        #     "the email field at the top of the signup form",
        #     "user@example.com",
        # )

        # 4) Hover — useful for menus that only render on hover.
        #
        # await agent.hover(page, "the 'Account' avatar in the top-right corner")


if __name__ == "__main__":
    asyncio.run(main())
