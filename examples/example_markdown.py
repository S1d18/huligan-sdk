"""
Huligan SDK — Extract clean Markdown from a page for LLM consumption.

Opens a page through the antidetect browser, pulls its HTML via
page.content() (paranoid-mode safe — no page.evaluate needed),
and converts it to Markdown using readability filtering.

Requires the markdown extra:

    pip install huligan[markdown]
"""
import asyncio
from huligan import Browser, extract_markdown


async def main():
    async with Browser(
        proxy="socks5://user:pass@ip:port",
    ) as browser:
        page = await browser.new_page()
        await page.goto(
            "https://en.wikipedia.org/wiki/Web_scraping",
            wait_until="domcontentloaded",
        )

        md = await extract_markdown(
            page,
            strategy="auto",          # trafilatura first, markdownify fallback
            include_links=True,
            include_images=False,     # usually noise for LLMs
        )

        print(f"Markdown length: {len(md)} chars")
        print("-" * 60)
        print(md[:2000])              # preview first 2k chars
        print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())
