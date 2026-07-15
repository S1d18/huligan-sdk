"""Detection sweep CLI - AUXILIARY, headed, NOT a CI gate.

Launches ONE headed Huligan Browser, runs the per-site adapters, and prints a normalized
summary. Live verdicts are auxiliary - watch the window; an operator's visual read wins.
The CDP scraper can report a stale "100%", so never trust a green sweep over your own eyes.

    python examples/detection_sweep.py --headed
    python examples/detection_sweep.py --sites creepjs pixelscan --proxy socks5://user:pass@ip:port
"""
import argparse
import asyncio

from huligan import Browser
from huligan.testing import render_summary, run_sweep, to_json


async def _run(args):
    async with Browser(proxy=args.proxy, headless=not args.headed) as browser:
        results = await run_sweep(browser, sites=args.sites)
    print(to_json(results) if args.json else render_summary(results))


def main():
    p = argparse.ArgumentParser(description="Huligan detection sweep (auxiliary, not authoritative)")
    p.add_argument("--headed", action="store_true", default=True,
                   help="show the window (default; the visual read is authoritative)")
    p.add_argument("--headless", dest="headed", action="store_false",
                   help="run headless (discouraged - you cannot visually verify)")
    p.add_argument("--proxy", help="proxy for the browser (needed for pixelscan)")
    p.add_argument("--sites", nargs="*", help="restrict to named sites, e.g. creepjs pixelscan")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    asyncio.run(_run(p.parse_args()))


if __name__ == "__main__":
    main()
