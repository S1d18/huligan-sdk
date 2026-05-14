"""
Agents scrape: stealth-Chromium pool extracting list items.

Run:
    pip install huligan[agents]
    python examples/agents/example_basic_scrape.py

What this does:
    - Boots a single huligan-patched Chrome via HuliganAgent.
    - Visits a few Hacker News pages, extracts title + url, prints.
    - Demonstrates that page.locator() works through huligan's CDP
      stealth (page.evaluate is intentionally blocked in paranoid mode).
"""

import asyncio
from huligan.agents import HuliganAgent


async def main():
    agent = HuliganAgent(
        # Set to your proxy if you have one:
        # proxy="socks5://user:pass@host:port",
        fingerprint_seed=42,
        headless=True,
    )

    @agent.router.default_handler
    async def handler(context):
        await context.enqueue_links(selector=".titleline > a", limit=5)
        title = (await context.page.title()) or ""
        url = context.request.url
        await context.push_data({"url": url, "title": title})

    await agent.run(["https://news.ycombinator.com"])
    await agent.export_data("scraped.json")


if __name__ == "__main__":
    asyncio.run(main())
