"""
Huligan SDK — Proxy rotation with a fixed fingerprint profile.

Demonstrates rotating through multiple proxies while keeping the same
browser fingerprint. This is useful when you want:
  - Consistent canvas/WebGL/fonts fingerprint across IPs
  - Different IP addresses for rate-limit evasion
  - Same "device" appearing from different locations

Key: generate one profile .conf file, then reuse it with different proxies.
"""
import asyncio
from pathlib import Path
from huligan import Browser, FingerprintGenerator


# Generate one fingerprint profile with a fixed seed (reproducible)
PROFILE_PATH = Path("./rotation_profile.conf")
SEED = 42

PROXIES = [
    "socks5://user:pass@proxy1.example.com:1080",
    "socks5://user:pass@proxy2.example.com:1080",
    "socks5://user:pass@proxy3.example.com:1080",
    "socks5://user:pass@proxy4.example.com:1080",
    "socks5://user:pass@proxy5.example.com:1080",
]

# IP-checking site — displays visitor's IP address
IP_CHECK_URL = "https://httpbin.org/ip"


def generate_profile():
    """Generate a fingerprint profile and save it to disk (once)."""
    if PROFILE_PATH.exists():
        print(f"Profile already exists: {PROFILE_PATH.resolve()}")
        return

    gen = FingerprintGenerator(seed=SEED)
    profile = gen.generate(platform="Win32")
    PROFILE_PATH.write_text(profile.to_conf(), encoding="utf-8")
    print(f"Generated profile: {PROFILE_PATH.resolve()}")
    print(f"  Screen: {profile.screen_width}x{profile.screen_height}")
    print(f"  GPU: {profile.webgl_renderer[:50]}...")
    print(f"  CPU: {profile.cpu_cores} cores, {profile.device_memory} GB RAM")


async def check_ip_with_proxy(proxy: str, profile_path: str) -> dict:
    """
    Launch browser with given proxy and fixed profile, extract displayed IP.

    Returns a dict with proxy, detected_ip, and status.
    """
    result = {"proxy": proxy, "detected_ip": None, "status": "unknown"}

    try:
        async with Browser(
            proxy=proxy,
            profile_path=profile_path,
        ) as browser:
            page = await browser.new_page()

            # Navigate to IP-check page
            await page.goto(IP_CHECK_URL, wait_until="domcontentloaded", timeout=20000)

            # httpbin.org/ip returns JSON in a <pre> tag: {"origin": "1.2.3.4"}
            # Extract the text using a locator
            pre = page.locator("pre")
            await pre.wait_for(state="visible", timeout=10000)
            ip_text = await pre.text_content()

            # Parse IP from the JSON response text
            # The text looks like: '{\n  "origin": "1.2.3.4"\n}'
            if "origin" in ip_text:
                ip = ip_text.split('"origin"')[1].split('"')[1]
                result["detected_ip"] = ip
                result["status"] = "ok"
            else:
                result["status"] = "parse_error"

    except TimeoutError:
        result["status"] = "timeout"
    except Exception as e:
        result["status"] = f"error: {e}"

    return result


async def main():
    print("Huligan — Proxy rotation with fixed fingerprint")
    print("=" * 55)

    # Step 1: Generate the shared fingerprint profile
    generate_profile()
    profile_abs = str(PROFILE_PATH.resolve())

    # Step 2: Rotate through each proxy sequentially
    results = []
    for i, proxy in enumerate(PROXIES):
        print(f"\n[{i + 1}/{len(PROXIES)}] Testing proxy: {proxy}")
        result = await check_ip_with_proxy(proxy, profile_abs)
        results.append(result)
        print(f"  IP: {result['detected_ip'] or 'N/A'}  Status: {result['status']}")

    # Step 3: Print summary table
    print("\n" + "=" * 55)
    print("RESULTS SUMMARY")
    print("=" * 55)
    print(f"{'#':<4} {'Proxy':<40} {'Detected IP':<18} {'Status'}")
    print("-" * 80)
    for i, r in enumerate(results):
        proxy_short = r["proxy"].split("@")[-1] if "@" in r["proxy"] else r["proxy"]
        ip = r["detected_ip"] or "N/A"
        print(f"{i + 1:<4} {proxy_short:<40} {ip:<18} {r['status']}")

    ok_count = sum(1 for r in results if r["status"] == "ok")
    print(f"\nSuccess: {ok_count}/{len(results)} proxies working")


if __name__ == "__main__":
    asyncio.run(main())
