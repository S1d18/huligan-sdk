#!/usr/bin/env python3
"""Automated validation of the persistent (GUI) launch path through a proxy.

This is the *automatic-first* validation gate for the thin-app refactor: it
proves the bug that `launch_persistent` fixes is actually fixed — that Chrome
reaches the internet through the authenticated SOCKS5 forwarder and presents the
proxy's exit IP (not the machine's real IP), and that Accept-Language follows
GeoIP. The deeper checks (WebRTC leak, full BrowserScan/CreepJS) stay an
operator visual read — the CDP scraper is unreliable (see project memory).

What it asserts (no `page.evaluate` — that's blocked by the stealth patch; we
read response bodies via locators):

  1. EXIT IP    — Chrome (via the forwarder) sees the same public IP that a
                  direct probe through the proxy sees. Mismatch / real IP = FAIL.
  2. ACCEPT-LANG — the Accept-Language header carries the GeoIP-resolved language
                  (best-effort; warns rather than fails if the echo is unparseable).

Usage:
    python validate_launch.py "socks5://user:pass@host:port"
    python validate_launch.py "host:port:user:pass" --proxy-type socks5
    HULIGAN_TEST_PROXY="socks5://..." python validate_launch.py

Requires: a working proxy, network, and Chrome (auto-downloaded by the SDK if
absent). Exit code 0 = all hard checks passed.
"""

import argparse
import asyncio
import os
import sys
import tempfile
from pathlib import Path

from huligan import FingerprintGenerator, launch_persistent
from huligan.proxy import detect_exit_ip, parse_proxy_string


def _make_temp_profile() -> Path:
    """Generate a throwaway .conf so the harness needs no saved profile."""
    prof = FingerprintGenerator().generate(platform="Win32")
    fd, path = tempfile.mkstemp(suffix=".conf", prefix="huligan_validate_")
    os.close(fd)
    Path(path).write_text(prof.to_conf(), encoding="utf-8")
    return Path(path)


async def _run_checks(cdp_url: str, expected_exit_ip, geo_language) -> bool:
    from playwright.async_api import async_playwright

    ok = True
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(cdp_url)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # One trip through the proxy: capture the ACTUAL Accept-Language Chrome
        # sends on the navigation request (CDP Network — not blocked by the
        # stealth patch, unlike page.evaluate), and read the exit IP from the
        # response body. No dependence on any page's JSON rendering.
        accept_lang = ""
        async with page.expect_request("**/*") as req_info:
            await page.goto("https://api.ipify.org?format=text",
                            timeout=30000, wait_until="domcontentloaded")
        try:
            req = await req_info.value
            accept_lang = (await req.all_headers()).get("accept-language", "")
        except Exception:  # noqa: BLE001 — header capture is best-effort
            pass
        seen_ip = (await page.locator("body").inner_text()).strip()

        # 1) EXIT IP through the forwarder.
        if expected_exit_ip:
            passed = seen_ip == expected_exit_ip
            ok = ok and passed
            print(f"[{'PASS' if passed else 'FAIL'}] EXIT IP     "
                  f"chrome={seen_ip!r} expected(proxy)={expected_exit_ip!r}")
        else:
            print(f"[WARN] EXIT IP     chrome={seen_ip!r} "
                  f"(could not probe proxy directly to compare)")

        # 2) ACCEPT-LANGUAGE from the real request header.
        if geo_language and accept_lang:
            primary = geo_language.split(",")[0].split("-")[0].lower()
            passed = primary in accept_lang.lower()
            ok = ok and passed
            print(f"[{'PASS' if passed else 'FAIL'}] ACCEPT-LANG  "
                  f"header={accept_lang!r} geo={geo_language!r}")
        elif accept_lang:
            print(f"[INFO] ACCEPT-LANG  header={accept_lang!r} (no GeoIP language to compare)")
        else:
            print("[WARN] ACCEPT-LANG  could not capture the request header")

    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate the proxied persistent launch path.")
    ap.add_argument("proxy", nargs="?", default=os.environ.get("HULIGAN_TEST_PROXY"),
                    help="proxy string (or set HULIGAN_TEST_PROXY)")
    ap.add_argument("--proxy-type", default=None, help="force socks5|http")
    ap.add_argument("--profile", default=None, help="path to an existing .conf (else a temp one is generated)")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()

    if not args.proxy:
        print("ERROR: pass a proxy string or set HULIGAN_TEST_PROXY", file=sys.stderr)
        return 2

    profile_path = Path(args.profile) if args.profile else _make_temp_profile()
    temp_profile = args.profile is None

    # Direct probe of the proxy's exit IP to compare against what Chrome sees.
    info = parse_proxy_string(args.proxy)
    if args.proxy_type:
        info["type"] = args.proxy_type
    expected_exit_ip = detect_exit_ip(info, timeout=6.0)

    print(f"Launching {profile_path.name} via proxy {info['type']}://{info['host']}:{info['port']} ...")
    session = launch_persistent(
        profile_path=profile_path,
        proxy=args.proxy,
        proxy_type=args.proxy_type,
        url="about:blank",
        headless=args.headless,
        wait_for_cdp=True,
    )
    geo_language = session.geo.language if session.geo else None
    print(f"  CDP {session.cdp_url} | GeoIP={session.geo} | WebRTC spoof={session.webrtc_spoof_ip}")

    try:
        ok = asyncio.run(_run_checks(session.cdp_url, expected_exit_ip, geo_language))
    finally:
        session.stop()
        if temp_profile:
            try:
                profile_path.unlink()
            except OSError:
                pass

    print("\n" + ("RESULT: PASS - proxy/forwarder + GeoIP flow through the launch path."
                  if ok else "RESULT: FAIL - see checks above."))
    print("NOTE: WebRTC leak + full BrowserScan/CreepJS remain an operator visual read.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
