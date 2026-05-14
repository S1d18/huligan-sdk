"""
Agents pool: round-robin across multiple proxies + fingerprints.

Useful pattern for large scrapes where you want to spread load across
distinct identities. Each plugin config produces an independent
Chrome instance with its own .conf and proxy.

Run:
    pip install huligan[agents]
    python examples/agents/example_pool.py
"""

import asyncio
from huligan.agents import HuliganAgent


PROXIES_AND_SEEDS = [
    # Replace with real proxies before running for real targets.
    {"proxy": None, "fingerprint_seed": 1001},
    {"proxy": None, "fingerprint_seed": 1002},
    {"proxy": None, "fingerprint_seed": 1003},
]


async def main():
    agent = HuliganAgent.from_pool(
        plugin_configs=[
            {**cfg, "headless": True, "max_open_pages_per_browser": 1}
            for cfg in PROXIES_AND_SEEDS
        ],
    )

    @agent.router.default_handler
    async def handler(context):
        await context.push_data({
            "url": context.request.url,
            "title": await context.page.title(),
        })

    await agent.run([
        "https://httpbin.org/anything?account=1",
        "https://httpbin.org/anything?account=2",
        "https://httpbin.org/anything?account=3",
    ])


if __name__ == "__main__":
    asyncio.run(main())
